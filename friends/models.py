from django.conf import settings
from django.db import models
from django.db.models.functions import Greatest, Least


class Friendship(models.Model):
    """A friend request, which becomes a friendship when it's accepted.

    - `pending`: `from_user` asked `to_user`; waiting for an answer.
    - `accepted`: they are friends (who asked first no longer matters).

    A declined or cancelled request, or an unfriend, simply deletes the row, so
    nobody is told (and either person can ask again later).

    There is at most **one row per pair of people**, whatever the direction: the
    database refuses a second one (see `one_friendship_per_pair`).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Friends"

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="friendships_sent"
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="friendships_received"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(from_user=models.F("to_user")),
                name="no_friendship_with_yourself",
            ),
            # Same pair in either direction counts once: (A, B) and (B, A) clash.
            models.UniqueConstraint(
                Least("from_user", "to_user"),
                Greatest("from_user", "to_user"),
                name="one_friendship_per_pair",
            ),
        ]

    def __str__(self) -> str:
        arrow = "↔" if self.status == self.Status.ACCEPTED else "→"
        return f"{self.from_user.username} {arrow} {self.to_user.username}"

    def other(self, user):
        """The other person in this friendship, seen from `user`."""
        return self.to_user if self.from_user_id == user.pk else self.from_user
