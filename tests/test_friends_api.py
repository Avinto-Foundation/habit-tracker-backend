"""Friends: search, friend requests (send / accept / decline / cancel), friends list, unfriend."""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from friends import services
from friends.models import Friendship

User = get_user_model()
SEARCH = reverse("user-search")
REQUESTS = reverse("friend-requests")
FRIENDS = reverse("friend-list")


def make_user(username, full_name=None, **fields):
    return User.objects.create_user(
        email=f"{username}@example.com",
        username=username,
        full_name=full_name or username.title(),
        password="x-Strong-pass-1",
        **fields,
    )


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def sam(db):
    return make_user("sam", "Sam Adhikari", bio="Reading daily")


@pytest.fixture
def aarav(db):
    return make_user("aarav", "Aarav Shrestha", bio="Running every morning")


@pytest.fixture
def maya(db):
    return make_user("maya", "Maya Gurung")


@pytest.fixture
def as_sam(sam):
    return client_for(sam)


@pytest.fixture
def as_aarav(aarav):
    return client_for(aarav)


def send(client, username):
    return client.post(REQUESTS, {"username": username}, format="json")


def accept_url(pk):
    return reverse("friend-request-accept", args=[pk])


def decline_url(pk):
    return reverse("friend-request-decline", args=[pk])


def make_friends(a, b):
    return Friendship.objects.create(
        from_user=a, to_user=b, status=Friendship.Status.ACCEPTED, accepted_at=timezone.now()
    )


# --- Model rules ------------------------------------------------------------------


def test_only_one_friendship_per_pair_in_either_direction(sam, aarav):
    Friendship.objects.create(from_user=sam, to_user=aarav)

    with pytest.raises(IntegrityError):
        Friendship.objects.create(from_user=aarav, to_user=sam)


def test_cannot_be_friends_with_yourself(sam):
    with pytest.raises(IntegrityError):
        Friendship.objects.create(from_user=sam, to_user=sam)


def test_friends_of_works_in_both_directions(sam, aarav, maya):
    make_friends(sam, aarav)
    make_friends(maya, sam)
    Friendship.objects.create(from_user=sam, to_user=make_user("pending_person"))

    assert set(services.friends_of(sam)) == {aarav, maya}
    assert services.are_friends(aarav, sam)
    assert not services.are_friends(aarav, maya)


# --- Search -----------------------------------------------------------------------


def test_search_finds_by_username_or_name_and_never_shows_email(as_sam, aarav):
    by_username = as_sam.get(SEARCH, {"q": "aar"}).json()
    by_name = as_sam.get(SEARCH, {"q": "shrestha"}).json()

    assert by_username == by_name == [
        {
            "username": "aarav",
            "full_name": "Aarav Shrestha",
            "bio": "Running every morning",
            "avatar": None,
            "friendship_status": "none",
            "friendship_id": None,
        }
    ]
    assert "email" not in by_username[0]


def test_search_ignores_a_leading_at_sign_and_case(as_sam, aarav):
    assert [u["username"] for u in as_sam.get(SEARCH, {"q": "@AARAV"}).json()] == ["aarav"]


def test_search_never_includes_yourself(as_sam, sam):
    assert as_sam.get(SEARCH, {"q": "sam"}).json() == []


def test_search_does_not_search_emails(as_sam, aarav):
    assert as_sam.get(SEARCH, {"q": "example.com"}).json() == []


def test_search_hides_deactivated_users(as_sam):
    make_user("gone_user", is_active=False)

    assert as_sam.get(SEARCH, {"q": "gone"}).json() == []


def test_search_puts_best_matches_first(as_sam):
    make_user("zen_maria", "Anna Maria")
    make_user("maria_k", "Zoe Lane")
    make_user("maria", "Bob Smith")

    names = [u["username"] for u in as_sam.get(SEARCH, {"q": "maria"}).json()]

    assert names == ["maria", "maria_k", "zen_maria"]  # exact, then starts with, then contains


def test_search_returns_at_most_20(as_sam):
    for i in range(25):
        make_user(f"runner{i}")

    assert len(as_sam.get(SEARCH, {"q": "runner"}).json()) == 20


@pytest.mark.parametrize("query", ["", "a", "  b ", "@"])
def test_search_needs_at_least_2_characters(as_sam, query):
    response = as_sam.get(SEARCH, {"q": query})

    assert response.status_code == 400
    assert response.json() == {"q": ["Type at least 2 characters."]}


def test_search_shows_how_you_relate_to_each_person(as_sam, sam, aarav, maya):
    friend = make_friends(sam, aarav)
    sent = Friendship.objects.create(from_user=sam, to_user=maya)
    asker = make_user("mayank")
    received = Friendship.objects.create(from_user=asker, to_user=sam)

    results = {u["username"]: u for u in as_sam.get(SEARCH, {"q": "ma"}).json()}
    aarav_result = as_sam.get(SEARCH, {"q": "aarav"}).json()[0]

    assert (aarav_result["friendship_status"], aarav_result["friendship_id"]) == (
        "friends",
        friend.pk,
    )
    assert (results["maya"]["friendship_status"], results["maya"]["friendship_id"]) == (
        "request_sent",
        sent.pk,
    )
    assert (results["mayank"]["friendship_status"], results["mayank"]["friendship_id"]) == (
        "request_received",
        received.pk,
    )


def test_search_needs_a_login(db):
    assert APIClient().get(SEARCH, {"q": "sam"}).status_code == 401


# --- Sending requests -------------------------------------------------------------


def test_send_a_request(as_sam, sam, aarav):
    response = send(as_sam, "aarav")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["direction"] == "outgoing"
    assert body["user"]["username"] == "aarav"
    assert body["accepted_at"] is None
    assert Friendship.objects.get(pk=body["id"]).from_user == sam


def test_send_accepts_at_sign_and_any_case(as_sam, aarav):
    assert send(as_sam, " @Aarav ").status_code == 201


def test_sending_back_to_someone_who_asked_you_makes_you_friends(as_sam, sam, aarav):
    theirs = Friendship.objects.create(from_user=aarav, to_user=sam)

    response = send(as_sam, "aarav")

    assert response.status_code == 200
    assert response.json()["id"] == theirs.pk
    assert response.json()["status"] == "accepted"
    assert services.are_friends(sam, aarav)
    assert Friendship.objects.count() == 1


@pytest.mark.parametrize(
    ("setup", "username", "message"),
    [
        (None, "nobody_here", "We couldn't find anyone with that username."),
        (None, "sam", "You can't send a friend request to yourself."),
        ("friends", "aarav", "You're already friends."),
        ("sent", "aarav", "You've already sent them a request."),
    ],
)
def test_send_is_refused(as_sam, sam, aarav, setup, username, message):
    if setup == "friends":
        make_friends(aarav, sam)
    elif setup == "sent":
        Friendship.objects.create(from_user=sam, to_user=aarav)

    response = send(as_sam, username)

    assert response.status_code == 400
    assert response.json() == {"username": [message]}


def test_cannot_send_to_a_deactivated_user(as_sam):
    make_user("gone_user", is_active=False)

    assert send(as_sam, "gone_user").status_code == 400


def test_sending_is_limited_to_20_an_hour(as_sam):
    for i in range(20):
        make_user(f"person{i}")
        assert send(as_sam, f"person{i}").status_code == 201
    make_user("one_more")

    assert send(as_sam, "one_more").status_code == 429


def test_looking_at_requests_is_not_limited(as_sam):
    for _ in range(25):
        assert as_sam.get(REQUESTS).status_code == 200


# --- Listing requests -------------------------------------------------------------


def test_lists_incoming_and_outgoing_requests(as_sam, sam, aarav, maya):
    incoming = Friendship.objects.create(from_user=aarav, to_user=sam)
    outgoing = Friendship.objects.create(from_user=sam, to_user=maya)
    make_friends(sam, make_user("old_friend"))  # friends aren't requests

    body = as_sam.get(REQUESTS).json()

    assert [(r["id"], r["user"]["username"], r["direction"]) for r in body["incoming"]] == [
        (incoming.pk, "aarav", "incoming")
    ]
    assert [(r["id"], r["user"]["username"], r["direction"]) for r in body["outgoing"]] == [
        (outgoing.pk, "maya", "outgoing")
    ]


def test_other_peoples_requests_are_not_listed(as_sam, aarav, maya):
    Friendship.objects.create(from_user=aarav, to_user=maya)

    assert as_sam.get(REQUESTS).json() == {"incoming": [], "outgoing": []}


# --- Accept / decline / cancel ----------------------------------------------------


def test_accept_a_request(as_sam, sam, aarav):
    request = Friendship.objects.create(from_user=aarav, to_user=sam)

    response = as_sam.post(accept_url(request.pk))

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["accepted_at"] is not None
    assert response.json()["user"]["username"] == "aarav"
    assert services.are_friends(sam, aarav)


def test_cannot_accept_your_own_request(as_sam, sam, aarav):
    mine = Friendship.objects.create(from_user=sam, to_user=aarav)

    assert as_sam.post(accept_url(mine.pk)).status_code == 404
    assert not services.are_friends(sam, aarav)


def test_cannot_accept_someone_elses_request(as_sam, aarav, maya):
    theirs = Friendship.objects.create(from_user=aarav, to_user=maya)

    assert as_sam.post(accept_url(theirs.pk)).status_code == 404


def test_decline_deletes_the_request(as_sam, sam, aarav):
    request = Friendship.objects.create(from_user=aarav, to_user=sam)

    response = as_sam.post(decline_url(request.pk))

    assert response.status_code == 204
    assert not Friendship.objects.exists()


def test_after_declining_they_can_ask_again(as_sam, as_aarav, sam, aarav):
    request = Friendship.objects.create(from_user=aarav, to_user=sam)
    as_sam.post(decline_url(request.pk))

    assert send(as_aarav, "sam").status_code == 201


def test_cancel_your_own_request(as_sam, sam, aarav):
    mine = Friendship.objects.create(from_user=sam, to_user=aarav)

    response = as_sam.delete(reverse("friend-request", args=[mine.pk]))

    assert response.status_code == 204
    assert not Friendship.objects.exists()


def test_cannot_cancel_a_request_sent_to_you(as_sam, sam, aarav):
    theirs = Friendship.objects.create(from_user=aarav, to_user=sam)

    assert as_sam.delete(reverse("friend-request", args=[theirs.pk])).status_code == 404
    assert Friendship.objects.exists()


def test_accepted_friendships_are_not_requests_any_more(as_sam, sam, aarav):
    friendship = make_friends(aarav, sam)

    assert as_sam.post(accept_url(friendship.pk)).status_code == 404
    assert as_sam.post(decline_url(friendship.pk)).status_code == 404


# --- Friends list and unfriend ----------------------------------------------------


def test_friends_list_is_sorted_by_name_and_shows_the_other_person(as_sam, sam, aarav, maya):
    make_friends(sam, maya)
    make_friends(aarav, sam)
    Friendship.objects.create(from_user=sam, to_user=make_user("not_yet"))

    body = as_sam.get(FRIENDS).json()

    assert [f["user"]["full_name"] for f in body] == ["Aarav Shrestha", "Maya Gurung"]
    assert all(f["status"] == "accepted" for f in body)


def test_unfriend_works_from_either_side(as_aarav, sam, aarav):
    friendship = make_friends(sam, aarav)

    response = as_aarav.delete(reverse("friend-detail", args=[friendship.pk]))

    assert response.status_code == 204
    assert not services.are_friends(sam, aarav)


def test_cannot_unfriend_other_peoples_friendships(as_sam, aarav, maya):
    theirs = make_friends(aarav, maya)

    assert as_sam.delete(reverse("friend-detail", args=[theirs.pk])).status_code == 404
    assert Friendship.objects.exists()


def test_unfriend_does_not_delete_a_pending_request(as_sam, sam, aarav):
    pending = Friendship.objects.create(from_user=aarav, to_user=sam)

    assert as_sam.delete(reverse("friend-detail", args=[pending.pk])).status_code == 404


def test_deleting_a_user_removes_their_friendships(sam, aarav):
    make_friends(sam, aarav)

    aarav.delete()

    assert not Friendship.objects.exists()


# --- Login and docs ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "name", "args"),
    [
        ("get", "friend-list", []),
        ("get", "friend-requests", []),
        ("post", "friend-requests", []),
        ("delete", "friend-request", [1]),
        ("post", "friend-request-accept", [1]),
        ("post", "friend-request-decline", [1]),
        ("delete", "friend-detail", [1]),
    ],
)
def test_everything_needs_a_login(db, method, name, args):
    assert getattr(APIClient(), method)(reverse(name, args=args)).status_code == 401


def test_friends_endpoints_are_documented(db):
    paths = APIClient().get(reverse("schema"), {"format": "json"}).json()["paths"]

    assert "get" in paths["/api/users/search/"]
    assert {"get", "post"} <= set(paths["/api/friends/requests/"])
    assert "post" in paths["/api/friends/requests/{id}/accept/"]
    assert "delete" in paths["/api/friends/{id}/"]


def test_friendships_show_in_django_admin(client, sam, aarav):
    admin = User.objects.create_superuser(
        email="admin@example.com", username="admin", full_name="Admin", password="x-Strong-pass-1"
    )
    client.force_login(admin)
    make_friends(sam, aarav)

    response = client.get(reverse("admin:friends_friendship_changelist"))

    assert response.status_code == 200
    assert "sam ↔ aarav" in response.content.decode()
