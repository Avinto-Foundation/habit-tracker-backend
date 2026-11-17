from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """App user. Email is unique because people log in with it."""

    email = models.EmailField("email address", unique=True)

    def __str__(self) -> str:
        return self.email or self.username
