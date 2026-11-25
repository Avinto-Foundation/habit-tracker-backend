"""Profile photos: check an upload, shrink it and save it safely.

Every photo is opened and saved again as a new image instead of being stored as
uploaded. That:
- proves it really is an image (a renamed .exe or script can't get through),
- shrinks it to at most 512 x 512 px, so pages load fast and storage stays small,
- removes hidden data (EXIF), such as the GPS location phones add to photos,
  so a profile photo never reveals where it was taken.
"""

from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_SIDE = 512  # pixels
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

TOO_BIG = "The photo is too big. Choose one under 2 MB."
NOT_AN_IMAGE = "This file isn't a photo. Choose a JPG, PNG or WebP image."
WRONG_FORMAT = "Use a JPG, PNG or WebP photo."


class AvatarError(ValueError):
    """The upload can't be used as a profile photo. The message is safe to show."""


def process_avatar(upload) -> ContentFile:
    """Check `upload` (an uploaded file) and return it as a small, clean WebP image.

    Raises AvatarError with a friendly message if it's too big, not an image or an
    unsupported format.
    """
    if upload.size > MAX_UPLOAD_BYTES:
        raise AvatarError(TOO_BIG)

    try:
        image = Image.open(upload)
        image_format = image.format
        image.load()  # read the whole file now, so broken images fail here
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise AvatarError(NOT_AN_IMAGE) from error

    if image_format not in ALLOWED_FORMATS:
        raise AvatarError(WRONG_FORMAT)

    # Turn the picture the right way up (phones store rotation in EXIF), then
    # shrink it, keeping its shape. Saving without EXIF drops the hidden data.
    image = ImageOps.exif_transpose(image)
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")

    output = BytesIO()
    image.save(output, format="WEBP", quality=85)
    return ContentFile(output.getvalue(), name="avatar.webp")
