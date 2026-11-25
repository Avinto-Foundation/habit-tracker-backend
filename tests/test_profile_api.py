"""Profile: bio, profile photo upload and change password."""

from io import BytesIO
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from accounts import avatars

User = get_user_model()
ME = reverse("me")
AVATAR = reverse("me-avatar")
PASSWORD_URL = reverse("me-password")
PASSWORD = "my-Strong-pass-1"
NEW_PASSWORD = "new-Better-pass-2"


@pytest.fixture(autouse=True)
def media_in_tmp(settings, tmp_path):
    """Save uploaded photos in a temporary folder, never in the project."""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="sam@example.com",
        username="sam",
        full_name="Sam Adhikari",
        password=PASSWORD,
        timezone="Asia/Kathmandu",
    )


@pytest.fixture
def logged_in(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    return client


def image_file(fmt="JPEG", size=(100, 80), mode="RGB", name=None, **save_options):
    """An image file made in memory, like one chosen in the browser."""
    buffer = BytesIO()
    color = (200, 50, 50, 128) if mode == "RGBA" else (200, 50, 50)  # half see-through for RGBA
    Image.new(mode, size, color=color).save(buffer, format=fmt, **save_options)
    extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}[fmt]
    return SimpleUploadedFile(name or f"photo.{extension}", buffer.getvalue())


def upload(client, file):
    return client.put(AVATAR, {"avatar": file}, format="multipart")


def saved_photo(user) -> Path:
    user.refresh_from_db()
    return Path(user.avatar.path)


# --- Bio --------------------------------------------------------------------------


def test_me_includes_bio_avatar_and_date_joined(user, logged_in):
    body = logged_in.get(ME).json()

    assert body["bio"] == ""
    assert body["avatar"] is None
    assert body["date_joined"].startswith(str(user.date_joined.date()))


def test_bio_can_be_set_and_is_kept_on_one_line(user, logged_in):
    response = logged_in.patch(ME, {"bio": "  Reading 20 pages\n a day.  "}, format="json")

    assert response.status_code == 200
    assert response.json()["bio"] == "Reading 20 pages a day."
    user.refresh_from_db()
    assert user.bio == "Reading 20 pages a day."


def test_bio_can_be_cleared(user, logged_in):
    user.bio = "Old bio"
    user.save()

    response = logged_in.patch(ME, {"bio": ""}, format="json")

    assert response.status_code == 200
    assert response.json()["bio"] == ""


def test_bio_longer_than_160_characters_is_rejected(logged_in):
    response = logged_in.patch(ME, {"bio": "x" * 161}, format="json")

    assert response.status_code == 400
    assert "bio" in response.json()


def test_date_joined_and_avatar_cannot_be_changed_through_me(user, logged_in):
    joined = user.date_joined

    logged_in.patch(
        ME, {"date_joined": "2000-01-01T00:00:00Z", "avatar": "http://evil.example/x.png"},
        format="json",
    )

    user.refresh_from_db()
    assert user.date_joined == joined
    assert not user.avatar


# --- Uploading a photo --------------------------------------------------------------


def test_upload_saves_a_small_webp_and_returns_its_full_url(user, logged_in):
    response = upload(logged_in, image_file("JPEG", size=(100, 80)))

    assert response.status_code == 200
    url = response.json()["avatar"]
    assert url.startswith(f"http://testserver/media/avatars/{user.id}/")
    assert url.endswith(".webp")
    path = saved_photo(user)
    with Image.open(path) as saved:
        assert saved.format == "WEBP"
        assert saved.size == (100, 80)  # small photos aren't made bigger


def test_big_photos_are_shrunk_to_512_px_keeping_their_shape(user, logged_in):
    upload(logged_in, image_file("PNG", size=(2000, 1000)))

    with Image.open(saved_photo(user)) as saved:
        assert saved.size == (512, 256)


def test_png_with_transparency_keeps_it(user, logged_in):
    upload(logged_in, image_file("PNG", mode="RGBA"))

    with Image.open(saved_photo(user)) as saved:
        assert saved.mode == "RGBA"


def test_webp_upload_works(user, logged_in):
    assert upload(logged_in, image_file("WEBP")).status_code == 200


def test_hidden_photo_data_such_as_gps_location_is_removed(user, logged_in):
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (27.0, 42.0, 0.0)}  # GPS info: somewhere in Kathmandu
    exif[0x010F] = "PhoneMaker"  # camera make
    upload(logged_in, image_file("JPEG", exif=exif.tobytes()))

    with Image.open(saved_photo(user)) as saved:
        assert not saved.getexif()
        assert "exif" not in saved.info


def test_a_new_photo_replaces_and_deletes_the_old_one(user, logged_in):
    upload(logged_in, image_file("JPEG"))
    old = saved_photo(user)

    upload(logged_in, image_file("PNG"))
    new = saved_photo(user)

    assert new != old
    assert new.exists()
    assert not old.exists()


def test_photo_over_2_mb_is_rejected(user, logged_in):
    too_big = SimpleUploadedFile("big.jpg", b"0" * (avatars.MAX_UPLOAD_BYTES + 1))

    response = upload(logged_in, too_big)

    assert response.status_code == 400
    assert response.json() == {"avatar": [avatars.TOO_BIG]}
    user.refresh_from_db()
    assert not user.avatar


def test_a_file_that_isnt_an_image_is_rejected(logged_in):
    fake = SimpleUploadedFile("photo.jpg", b"<script>alert('hi')</script>")

    response = upload(logged_in, fake)

    assert response.status_code == 400
    assert response.json() == {"avatar": [avatars.NOT_AN_IMAGE]}


def test_gif_is_not_accepted(logged_in):
    response = upload(logged_in, image_file("GIF", mode="P"))

    assert response.status_code == 400
    assert response.json() == {"avatar": [avatars.WRONG_FORMAT]}


def test_upload_without_a_file_is_rejected(logged_in):
    response = logged_in.put(AVATAR, {}, format="multipart")

    assert response.status_code == 400
    assert "avatar" in response.json()


def test_upload_must_be_multipart(logged_in):
    response = logged_in.put(AVATAR, {"avatar": "not a file"}, format="json")

    assert response.status_code == 415


def test_photo_url_is_in_the_login_response(user):
    client = APIClient()
    client.force_authenticate(user)
    upload(client, image_file("JPEG"))

    response = APIClient().post(
        reverse("login"), {"email": "sam@example.com", "password": PASSWORD}, format="json"
    )

    assert response.json()["user"]["avatar"].startswith("http://testserver/media/avatars/")


# --- Removing a photo ---------------------------------------------------------------


def test_delete_removes_the_photo_and_its_file(user, logged_in):
    upload(logged_in, image_file("JPEG"))
    path = saved_photo(user)

    response = logged_in.delete(AVATAR)

    assert response.status_code == 200
    assert response.json()["avatar"] is None
    assert not path.exists()
    user.refresh_from_db()
    assert not user.avatar


def test_delete_without_a_photo_is_fine(logged_in):
    response = logged_in.delete(AVATAR)

    assert response.status_code == 200
    assert response.json()["avatar"] is None


@pytest.mark.parametrize("method", ["put", "delete"])
def test_photo_endpoints_need_a_login(db, method):
    assert getattr(APIClient(), method)(AVATAR).status_code == 401


# --- Changing the password ----------------------------------------------------------


def change(client, current=PASSWORD, new=NEW_PASSWORD, confirm=None, **extra):
    data = {
        "current_password": current,
        "new_password": new,
        "new_password_confirm": new if confirm is None else confirm,
        **extra,
    }
    return client.post(PASSWORD_URL, data, format="json")


def login(password):
    return APIClient().post(
        reverse("login"), {"email": "sam@example.com", "password": password}, format="json"
    )


def test_change_password_works_and_returns_new_tokens(user, logged_in):
    response = change(logged_in)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access", "refresh"}
    assert AccessToken(body["access"])["user_id"] == str(user.id)
    assert login(NEW_PASSWORD).status_code == 200
    assert login(PASSWORD).status_code == 401


def test_change_password_logs_out_every_other_device(user, logged_in):
    other_device = login(PASSWORD).json()["refresh"]

    new_refresh = change(logged_in).json()["refresh"]

    refresh_url = reverse("token-refresh")
    assert APIClient().post(refresh_url, {"refresh": other_device}).status_code == 401
    assert APIClient().post(refresh_url, {"refresh": new_refresh}).status_code == 200


def test_remember_me_gives_the_new_refresh_token_7_days(logged_in):
    body = change(logged_in, remember_me=True).json()

    assert RefreshToken(body["refresh"])["remember_me"] is True


def test_wrong_current_password_is_rejected(user, logged_in):
    response = change(logged_in, current="not-my-password")

    assert response.status_code == 400
    assert response.json() == {"current_password": ["Your current password is incorrect."]}
    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_new_passwords_must_match(logged_in):
    response = change(logged_in, confirm="something-else-3")

    assert response.status_code == 400
    assert response.json() == {"new_password_confirm": ["Passwords don't match."]}


def test_new_password_must_differ_from_the_current_one(logged_in):
    response = change(logged_in, new=PASSWORD)

    assert response.status_code == 400
    assert "new_password" in response.json()


@pytest.mark.parametrize("weak", ["short1", "password123", "12345678901", "SamAdhikari1"])
def test_weak_new_passwords_are_rejected(logged_in, weak):
    response = change(logged_in, new=weak)

    assert response.status_code == 400
    assert "new_password" in response.json()


def test_change_password_needs_a_login(db):
    assert APIClient().post(PASSWORD_URL, {}, format="json").status_code == 401


def test_change_password_is_limited_to_10_tries_an_hour(logged_in):
    for _ in range(10):
        change(logged_in, current="wrong-guess")

    assert change(logged_in, current="wrong-guess").status_code == 429


def test_profile_endpoints_are_documented(db):
    schema = APIClient().get(reverse("schema"), {"format": "json"}).json()

    assert set(schema["paths"]["/api/auth/me/avatar/"]) >= {"put", "delete"}
    assert "post" in schema["paths"]["/api/auth/me/password/"]
