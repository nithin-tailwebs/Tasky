from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Identical to Django's default user today.

    It exists so that adding a field later is a migration rather than a rewrite —
    swapping AUTH_USER_MODEL after the fact is one of Django's genuinely painful jobs.
    """

    @property
    def display_name(self) -> str:
        full_name = self.get_full_name().strip()
        return full_name or self.username

    def __str__(self) -> str:
        return self.display_name
