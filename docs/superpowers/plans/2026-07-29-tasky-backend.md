# Tasky Backend & API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested Django REST API for an internal team kanban — auth, boards, cards with drag-ordering, comments, and a "my tasks" view — runnable in Docker against MySQL.

**Architecture:** A single Django project (`config`) with two apps: `accounts` (custom user + session auth endpoints) and `boards` (Board, Card, Comment + their API). Django runs in a Docker container; MySQL runs natively on the Mac in development and on RDS in production, selected purely by environment variables. Session-cookie auth, because the React UI will be served from the same origin — there are no tokens anywhere in this system.

**Tech Stack:** Python 3.12 · Django 5.2 · Django REST Framework · MySQL 8 · mysqlclient · gunicorn · pytest + pytest-django · Docker Compose

## Global Constraints

- **Database is MySQL.** Never SQLite, including in tests — test against the engine you deploy on.
- **All configuration comes from environment variables.** No credential, hostname, or secret key literal in any committed file. `.env` is gitignored; `.env.example` is committed with placeholder values.
- **Auth is Django sessions, same origin.** No JWT, no DRF tokens, no `django-cors-headers`.
- **Every endpoint requires authentication** except `POST /api/auth/login/` and `GET /api/auth/csrf/`.
- **Custom user model from the first migration.** `AUTH_USER_MODEL = "accounts.User"`. Never `django.contrib.auth.models.User`.
- **Every task ends green.** `docker compose run --rm web pytest` passes before the commit.
- **Commit at the end of every task.** Conventional-commit prefixes: `feat:`, `test:`, `chore:`, `fix:`.
- **Status values are exactly** `todo`, `in_progress`, `done` — the React columns key off these strings.
- **Priority is stored as an integer** (`1` low, `2` medium, `3` high) so ordering is semantic, and exposed with a human label alongside.

## Deviations from the spec

Two, both deliberate:

1. **`GET /api/auth/csrf/` is added.** The spec's §7 endpoint list omits it, but session auth requires it — a JavaScript client cannot send Django's CSRF token until Django has set the cookie, so the UI calls this once on load. Added in Task 3; the only addition to the API surface.
2. **`GET /api/me/tasks/` excludes `done` cards.** The spec says "everything assigned to you". A to-do screen that accumulates every finished card becomes useless within a month, so it returns open work only. If you'd rather see completed cards there, it's a one-line change in `boards/views_me.py`.

---

### Task 1: Project skeleton running in Docker against MySQL

**Files:**
- Create: `requirements.txt`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `pytest.ini`
- Create: `manage.py`, `config/__init__.py`, `config/settings.py`, `config/urls.py`, `config/wsgi.py`, `config/asgi.py`
- Create: `conftest.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing — this is the first task
- Produces: a Django project importable as `config.settings`; `docker compose run --rm web pytest` as the test command every later task uses; fixtures `user`, `other_user`, `auth_client` in `conftest.py`

---

- [ ] **Step 1: Install and prepare MySQL on the Mac**

Docker Desktop must be installed and running first — download from docker.com if `docker --version` fails.

```bash
brew install mysql
brew services start mysql
```

The container reaches the Mac through `host.docker.internal`, so MySQL must accept connections from outside localhost. Edit the Homebrew config:

```bash
echo -e "[mysqld]\nbind-address = 0.0.0.0" >> $(brew --prefix)/etc/my.cnf
brew services restart mysql
```

> **Why this step exists:** Homebrew's MySQL binds to `127.0.0.1` only. Left alone, the container gets `Can't connect to MySQL server` and the cause is completely non-obvious. This is the single most likely place to lose an hour.

- [ ] **Step 2: Create the database and user**

The `'tasky'@'%'` host wildcard matters — the container is not localhost. The grant on `test_tasky.*` matters too: pytest-django creates a *separate* test database and will fail without it.

```bash
mysql -u root <<'SQL'
CREATE DATABASE IF NOT EXISTS tasky CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'tasky'@'%' IDENTIFIED BY 'tasky_dev_password';
GRANT ALL PRIVILEGES ON tasky.* TO 'tasky'@'%';
GRANT ALL PRIVILEGES ON `test_tasky`.* TO 'tasky'@'%';
FLUSH PRIVILEGES;
SQL
```

- [ ] **Step 3: Write `requirements.txt`**

Ranges rather than exact pins, so the first install cannot fail on a patch version that does not exist. Step 12 freezes the resolved versions.

```
Django>=5.2,<6.0
djangorestframework>=3.16,<4.0
mysqlclient>=2.2,<3.0
gunicorn>=23.0,<24.0
pytest>=8.3,<9.0
pytest-django>=4.9,<5.0
```

- [ ] **Step 4: Write `Dockerfile`**

`mysqlclient` compiles against MySQL C headers, which is why the apt packages are here. Without them the pip install fails with a `pkg-config` error.

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
```

- [ ] **Step 5: Write `docker-compose.yml`**

Compose overrides the image's gunicorn command with `runserver` for auto-reload. The bind mount means your edits apply without rebuilding.

```yaml
services:
  web:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    env_file: .env
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

- [ ] **Step 6: Write `.env.example` and create your `.env`**

`.env.example` is committed. `.env` is not — `.gitignore` already excludes it.

```
DJANGO_SECRET_KEY=change-me-to-something-random
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
MYSQL_DATABASE=tasky
MYSQL_USER=tasky
MYSQL_PASSWORD=tasky_dev_password
MYSQL_HOST=host.docker.internal
MYSQL_PORT=3306
```

```bash
cp .env.example .env
```

- [ ] **Step 7: Generate the Django project**

```bash
docker compose run --rm web django-admin startproject config .
```

- [ ] **Step 8: Write `pytest.ini`**

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = test_*.py
addopts = -v
```

- [ ] **Step 9: Write the failing test**

Create `tests/__init__.py` (empty), then `tests/test_smoke.py`:

```python
import pytest
from django.db import connection


@pytest.mark.django_db
def test_database_is_mysql():
    assert connection.vendor == "mysql"


@pytest.mark.django_db
def test_database_answers_a_query():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
```

- [ ] **Step 10: Run the test to verify it fails**

Run: `docker compose run --rm web pytest tests/test_smoke.py`
Expected: FAIL — the generated settings still point at SQLite, so `connection.vendor` is `"sqlite"`.

- [ ] **Step 11: Configure settings for env-driven MySQL**

Replace the `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` and `DATABASES` blocks in `config/settings.py`, and add `os` to the imports at the top:

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("MYSQL_DATABASE", "tasky"),
        "USER": os.environ.get("MYSQL_USER", "tasky"),
        "PASSWORD": os.environ.get("MYSQL_PASSWORD", ""),
        "HOST": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "PORT": os.environ.get("MYSQL_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        "TEST": {
            "CHARSET": "utf8mb4",
            "COLLATION": "utf8mb4_unicode_ci",
        },
    }
}
```

Then add DRF to `INSTALLED_APPS` and append the DRF configuration at the end of the file:

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# The React app must read this cookie to send the CSRF header, so it cannot be HttpOnly.
CSRF_COOKIE_HTTPONLY = False
```

> **On `STRICT_TRANS_TABLES`:** without it MySQL silently truncates oversized values instead of erroring. Silent data loss is worse than a failed request.

- [ ] **Step 12: Run the test to verify it passes**

Run: `docker compose run --rm web pytest tests/test_smoke.py`
Expected: PASS — 2 passed.

Now freeze the resolved versions so builds are reproducible:

```bash
docker compose run --rm web pip freeze > requirements.lock
```

- [ ] **Step 13: Write `conftest.py`**

Root-level `conftest.py`. Every later task's tests use these fixtures.

```python
import pytest
from django.contrib.auth import get_user_model


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="alice", password="pw-alice-12345", first_name="Alice"
    )


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(
        username="bob", password="pw-bob-12345", first_name="Bob"
    )


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client
```

- [ ] **Step 14: Commit**

```bash
git add requirements.txt requirements.lock Dockerfile docker-compose.yml .env.example \
        pytest.ini manage.py config/ conftest.py tests/
git commit -m "chore: django project skeleton in docker against mysql"
```

---

### Task 2: Custom user model

**Files:**
- Create: `accounts/__init__.py`, `accounts/apps.py`, `accounts/models.py`, `accounts/admin.py`
- Create: `accounts/migrations/__init__.py`
- Modify: `config/settings.py` — `INSTALLED_APPS`, plus a new `AUTH_USER_MODEL` line
- Test: `accounts/tests/__init__.py`, `accounts/tests/test_models.py`

**Interfaces:**
- Consumes: `config.settings` from Task 1
- Produces: `accounts.models.User` with a `display_name` property returning the full name when set, otherwise the username. Every later task references users via `django.contrib.auth.get_user_model()`.

---

- [ ] **Step 1: Write the failing test**

`accounts/tests/test_models.py`:

```python
import pytest
from django.contrib.auth import get_user_model


def test_user_model_is_the_custom_one():
    assert get_user_model()._meta.label == "accounts.User"


@pytest.mark.django_db
def test_display_name_prefers_full_name():
    user = get_user_model().objects.create_user(
        username="carol", password="pw-carol-12345",
        first_name="Carol", last_name="Danvers",
    )
    assert user.display_name == "Carol Danvers"


@pytest.mark.django_db
def test_display_name_falls_back_to_username():
    user = get_user_model().objects.create_user(
        username="dave", password="pw-dave-12345"
    )
    assert user.display_name == "dave"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker compose run --rm web pytest accounts/tests/test_models.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'accounts'`.

- [ ] **Step 3: Create the app and the model**

```bash
docker compose run --rm web python manage.py startapp accounts
mkdir -p accounts/tests && touch accounts/tests/__init__.py
```

`accounts/models.py`:

```python
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
```

- [ ] **Step 4: Register the app and the user model**

In `config/settings.py`, add to `INSTALLED_APPS`:

```python
    "accounts",
```

and add this line below `INSTALLED_APPS`:

```python
AUTH_USER_MODEL = "accounts.User"
```

- [ ] **Step 5: Register in the admin**

`accounts/admin.py` — this is the entire "admin creates accounts" feature.

```python
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User

admin.site.register(User, UserAdmin)
```

- [ ] **Step 6: Create the migration**

```bash
docker compose run --rm web python manage.py makemigrations accounts
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `docker compose run --rm web pytest accounts/tests/test_models.py`
Expected: PASS — 3 passed.

- [ ] **Step 8: Create your admin account and check the admin loads**

```bash
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
docker compose up
```

Open `http://localhost:8000/admin/`, sign in, confirm you can add a user. Stop with `Ctrl+C`.

- [ ] **Step 9: Commit**

```bash
git add accounts/ config/settings.py
git commit -m "feat: custom user model with admin registration"
```

---

### Task 3: Session auth endpoints

**Files:**
- Create: `accounts/serializers.py`, `accounts/views.py`, `accounts/urls.py`
- Modify: `config/urls.py` — include the API routes
- Test: `accounts/tests/test_auth_api.py`

**Interfaces:**
- Consumes: `accounts.models.User` from Task 2
- Produces: `accounts.serializers.UserSerializer` with fields `id`, `username`, `display_name` — reused by Tasks 7, 9 and 11. Endpoints `POST /api/auth/login/`, `POST /api/auth/logout/`, `GET /api/auth/me/`, `GET /api/auth/csrf/`.

---

- [ ] **Step 1: Write the failing test**

`accounts/tests/test_auth_api.py`:

```python
import pytest


@pytest.mark.django_db
def test_login_succeeds_with_correct_password(client, user):
    response = client.post(
        "/api/auth/login/",
        {"username": "alice", "password": "pw-alice-12345"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    assert response.json()["display_name"] == "Alice"


@pytest.mark.django_db
def test_login_fails_with_wrong_password(client, user):
    response = client.post(
        "/api/auth/login/",
        {"username": "alice", "password": "wrong-password"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "password" in response.json()["detail"].lower()


@pytest.mark.django_db
def test_login_does_not_reveal_whether_the_username_exists(client, user):
    unknown = client.post(
        "/api/auth/login/",
        {"username": "nobody", "password": "wrong-password"},
        content_type="application/json",
    )
    known = client.post(
        "/api/auth/login/",
        {"username": "alice", "password": "wrong-password"},
        content_type="application/json",
    )
    assert unknown.json() == known.json()


@pytest.mark.django_db
def test_me_returns_the_signed_in_user(auth_client):
    response = auth_client.get("/api/auth/me/")
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


@pytest.mark.django_db
def test_me_rejects_anonymous_callers(client):
    response = client.get("/api/auth/me/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_logout_ends_the_session(auth_client):
    assert auth_client.post("/api/auth/logout/").status_code == 204
    assert auth_client.get("/api/auth/me/").status_code == 403


@pytest.mark.django_db
def test_csrf_endpoint_sets_the_cookie(client):
    response = client.get("/api/auth/csrf/")
    assert response.status_code == 204
    assert "csrftoken" in response.cookies
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose run --rm web pytest accounts/tests/test_auth_api.py`
Expected: FAIL — all seven return 404, no such URLs.

- [ ] **Step 3: Write the serializers**

`accounts/serializers.py`:

```python
from django.contrib.auth import get_user_model
from rest_framework import serializers


class UserSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = get_user_model()
        fields = ["id", "username", "display_name"]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(style={"input_type": "password"})
```

- [ ] **Step 4: Write the views**

`accounts/views.py`:

```python
from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginSerializer, UserSerializer


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """The UI calls this once on load so the browser holds a CSRF cookie."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            # Deliberately identical for an unknown username and a wrong password:
            # a different message would let anyone enumerate who works here.
            return Response(
                {"detail": "Incorrect username or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        login(request, user)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)
```

- [ ] **Step 5: Wire the URLs**

`accounts/urls.py`:

```python
from django.urls import path

from .views import CsrfView, LoginView, LogoutView, MeView

urlpatterns = [
    path("auth/csrf/", CsrfView.as_view(), name="csrf"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", MeView.as_view(), name="me"),
]
```

Replace `config/urls.py` entirely:

```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.urls")),
]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `docker compose run --rm web pytest accounts/tests/test_auth_api.py`
Expected: PASS — 7 passed.

- [ ] **Step 7: Commit**

```bash
git add accounts/ config/urls.py
git commit -m "feat: session login, logout, me and csrf endpoints"
```

---

### Task 4: Board model

**Files:**
- Create: `boards/__init__.py`, `boards/apps.py`, `boards/models.py`, `boards/admin.py`
- Create: `boards/migrations/__init__.py`
- Modify: `config/settings.py` — add `"boards"` to `INSTALLED_APPS`
- Test: `boards/tests/__init__.py`, `boards/tests/test_board_model.py`

**Interfaces:**
- Consumes: `accounts.models.User` from Task 2
- Produces: `boards.models.Board` with fields `name`, `description`, `created_by`, `created_at`, `updated_at`; default ordering newest first. Tasks 5, 6 and 10 depend on it.

---

- [ ] **Step 1: Write the failing test**

`boards/tests/test_board_model.py`:

```python
import pytest

from boards.models import Board


@pytest.mark.django_db
def test_board_stringifies_to_its_name(user):
    board = Board.objects.create(name="Website Redesign", created_by=user)
    assert str(board) == "Website Redesign"


@pytest.mark.django_db
def test_description_is_optional(user):
    board = Board.objects.create(name="Ops", created_by=user)
    assert board.description == ""


@pytest.mark.django_db
def test_boards_are_ordered_newest_first(user):
    first = Board.objects.create(name="First", created_by=user)
    second = Board.objects.create(name="Second", created_by=user)
    assert list(Board.objects.all()) == [second, first]


@pytest.mark.django_db
def test_board_survives_its_creator_being_deleted(user):
    board = Board.objects.create(name="Orphan", created_by=user)
    user.delete()
    board.refresh_from_db()
    assert board.created_by is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose run --rm web pytest boards/tests/test_board_model.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'boards'`.

- [ ] **Step 3: Create the app and the model**

```bash
docker compose run --rm web python manage.py startapp boards
mkdir -p boards/tests && touch boards/tests/__init__.py
```

`boards/models.py`:

```python
from django.conf import settings
from django.db import models


class Board(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="boards_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name
```

> **On `SET_NULL`:** deleting a person must not delete the team's boards. Losing a project because someone left is not acceptable behaviour.

- [ ] **Step 4: Register the app and the admin**

Add `"boards"` to `INSTALLED_APPS` in `config/settings.py`.

`boards/admin.py`:

```python
from django.contrib import admin

from .models import Board


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at"]
    search_fields = ["name"]
```

- [ ] **Step 5: Create and run the migration**

```bash
docker compose run --rm web python manage.py makemigrations boards
docker compose run --rm web python manage.py migrate
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `docker compose run --rm web pytest boards/tests/test_board_model.py`
Expected: PASS — 4 passed.

- [ ] **Step 7: Commit**

```bash
git add boards/ config/settings.py
git commit -m "feat: board model"
```

---

### Task 5: Board API

**Files:**
- Create: `boards/serializers.py`, `boards/views.py`, `boards/urls.py`
- Modify: `config/urls.py` — include `boards.urls`
- Test: `boards/tests/test_board_api.py`

**Interfaces:**
- Consumes: `boards.models.Board` (Task 4), `accounts.serializers.UserSerializer` (Task 3)
- Produces: `boards.serializers.BoardSerializer`; endpoints `GET|POST /api/boards/` and `GET|PATCH|DELETE /api/boards/{id}/`. `boards/urls.py` exposes a DRF `router` that Tasks 7 and 9 register more viewsets on.

---

- [ ] **Step 1: Write the failing test**

`boards/tests/test_board_api.py`:

```python
import pytest

from boards.models import Board


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client):
    assert client.get("/api/boards/").status_code == 403


@pytest.mark.django_db
def test_listing_returns_every_board(auth_client, user, other_user):
    Board.objects.create(name="Mine", created_by=user)
    Board.objects.create(name="Theirs", created_by=other_user)

    response = auth_client.get("/api/boards/")

    assert response.status_code == 200
    names = {board["name"] for board in response.json()}
    assert names == {"Mine", "Theirs"}


@pytest.mark.django_db
def test_creating_a_board_records_the_creator(auth_client, user):
    response = auth_client.post(
        "/api/boards/",
        {"name": "Q3 Launch", "description": "Everything for the launch"},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["created_by"]["username"] == "alice"
    assert Board.objects.get(name="Q3 Launch").created_by == user


@pytest.mark.django_db
def test_created_by_cannot_be_forged(auth_client, other_user):
    response = auth_client.post(
        "/api/boards/",
        {"name": "Spoofed", "created_by": other_user.id},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert Board.objects.get(name="Spoofed").created_by.username == "alice"


@pytest.mark.django_db
def test_a_board_can_be_renamed(auth_client, user):
    board = Board.objects.create(name="Old Name", created_by=user)

    response = auth_client.patch(
        f"/api/boards/{board.id}/",
        {"name": "New Name"},
        content_type="application/json",
    )

    assert response.status_code == 200
    board.refresh_from_db()
    assert board.name == "New Name"


@pytest.mark.django_db
def test_a_board_can_be_deleted(auth_client, user):
    board = Board.objects.create(name="Doomed", created_by=user)

    assert auth_client.delete(f"/api/boards/{board.id}/").status_code == 204
    assert not Board.objects.filter(id=board.id).exists()


@pytest.mark.django_db
def test_name_is_required(auth_client):
    response = auth_client.post(
        "/api/boards/", {"description": "no name"}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "name" in response.json()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose run --rm web pytest boards/tests/test_board_api.py`
Expected: FAIL — 404s, no such URLs.

- [ ] **Step 3: Write the serializer**

`boards/serializers.py`:

```python
from rest_framework import serializers

from accounts.serializers import UserSerializer

from .models import Board


class BoardSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = Board
        fields = ["id", "name", "description", "created_by", "created_at", "updated_at"]
```

- [ ] **Step 4: Write the viewset**

`boards/views.py`:

```python
from rest_framework import viewsets

from .models import Board
from .serializers import BoardSerializer


class BoardViewSet(viewsets.ModelViewSet):
    """Every signed-in person sees every board — the team is small and shares its work."""

    queryset = Board.objects.select_related("created_by")
    serializer_class = BoardSerializer
    pagination_class = None

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
```

- [ ] **Step 5: Wire the URLs**

`boards/urls.py`:

```python
from rest_framework.routers import DefaultRouter

from .views import BoardViewSet

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")

urlpatterns = router.urls
```

In `config/urls.py`, add below the existing `accounts.urls` include:

```python
    path("api/", include("boards.urls")),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `docker compose run --rm web pytest boards/tests/test_board_api.py`
Expected: PASS — 7 passed.

- [ ] **Step 7: Commit**

```bash
git add boards/ config/urls.py
git commit -m "feat: board crud api"
```

---

### Task 6: Card model with priority, due date and column position

**Files:**
- Modify: `boards/models.py` — add `Card`
- Modify: `boards/admin.py` — register `Card`
- Create: `boards/services.py`
- Test: `boards/tests/test_card_model.py`

**Interfaces:**
- Consumes: `boards.models.Board` (Task 4)
- Produces:
  - `boards.models.Card` with `Card.Status` (`TODO="todo"`, `IN_PROGRESS="in_progress"`, `DONE="done"`) and `Card.Priority` (`LOW=1`, `MEDIUM=2`, `HIGH=3`)
  - `boards.services.next_position(board_id: int, status: str) -> int`
  - Both used by Tasks 7, 8 and 10.

---

- [ ] **Step 1: Write the failing test**

`boards/tests/test_card_model.py`:

```python
import datetime

import pytest

from boards.models import Board, Card
from boards.services import next_position


@pytest.fixture
def board(user):
    return Board.objects.create(name="Test Board", created_by=user)


@pytest.mark.django_db
def test_card_defaults(board):
    card = Card.objects.create(board=board, title="Write the spec")

    assert card.status == Card.Status.TODO
    assert card.priority == Card.Priority.MEDIUM
    assert card.due_date is None
    assert card.assignee is None
    assert card.description == ""


@pytest.mark.django_db
def test_card_stringifies_to_its_title(board):
    assert str(Card.objects.create(board=board, title="Ship it")) == "Ship it"


@pytest.mark.django_db
def test_next_position_starts_at_zero(board):
    assert next_position(board.id, Card.Status.TODO) == 0


@pytest.mark.django_db
def test_next_position_appends_to_the_end_of_its_column(board):
    Card.objects.create(board=board, title="A", status=Card.Status.TODO, position=0)
    Card.objects.create(board=board, title="B", status=Card.Status.TODO, position=1)

    assert next_position(board.id, Card.Status.TODO) == 2


@pytest.mark.django_db
def test_next_position_counts_each_column_separately(board):
    Card.objects.create(board=board, title="A", status=Card.Status.TODO, position=0)
    Card.objects.create(board=board, title="B", status=Card.Status.TODO, position=1)

    assert next_position(board.id, Card.Status.DONE) == 0


@pytest.mark.django_db
def test_cards_are_ordered_by_position_within_a_column(board):
    second = Card.objects.create(board=board, title="Second", position=1)
    first = Card.objects.create(board=board, title="First", position=0)

    assert list(Card.objects.filter(status=Card.Status.TODO)) == [first, second]


@pytest.mark.django_db
def test_deleting_a_board_deletes_its_cards(board):
    Card.objects.create(board=board, title="Doomed")
    board.delete()
    assert Card.objects.count() == 0


@pytest.mark.django_db
def test_unassigning_happens_when_the_assignee_is_deleted(board, other_user):
    card = Card.objects.create(board=board, title="Orphan", assignee=other_user)
    other_user.delete()
    card.refresh_from_db()
    assert card.assignee is None


@pytest.mark.django_db
def test_due_date_can_be_set(board):
    card = Card.objects.create(
        board=board, title="Dated", due_date=datetime.date(2026, 8, 15)
    )
    assert card.due_date == datetime.date(2026, 8, 15)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose run --rm web pytest boards/tests/test_card_model.py`
Expected: FAIL — `ImportError: cannot import name 'Card' from 'boards.models'`.

- [ ] **Step 3: Add the Card model**

Append to `boards/models.py`:

```python
class Card(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To Do"
        IN_PROGRESS = "in_progress", "In Progress"
        DONE = "done", "Done"

    class Priority(models.IntegerChoices):
        LOW = 1, "Low"
        MEDIUM = 2, "Medium"
        HIGH = 3, "High"

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="cards")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TODO
    )
    priority = models.IntegerField(
        choices=Priority.choices, default=Priority.MEDIUM
    )
    due_date = models.DateField(null=True, blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_cards",
    )
    position = models.IntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="cards_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]
        indexes = [models.Index(fields=["board", "status", "position"])]

    def __str__(self) -> str:
        return self.title
```

> **Why priority is an integer:** ordering by the strings `"high"`, `"low"`, `"medium"` sorts alphabetically, which is nonsense. `3 > 2 > 1` sorts correctly with no special-casing anywhere.

> **Why `id` is in `ordering`:** two cards can briefly share a position during a move. Without the tiebreak, their order is whatever MySQL feels like, and the board visibly shuffles on refresh.

- [ ] **Step 4: Write the position helper**

`boards/services.py`:

```python
from django.db.models import Max

from .models import Card


def next_position(board_id: int, status: str) -> int:
    """The position a new card takes: the end of its column."""
    highest = Card.objects.filter(board_id=board_id, status=status).aggregate(
        highest=Max("position")
    )["highest"]
    return 0 if highest is None else highest + 1
```

- [ ] **Step 5: Register in the admin**

Append to `boards/admin.py`:

```python
from .models import Card


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ["title", "board", "status", "priority", "assignee", "due_date"]
    list_filter = ["status", "priority", "board"]
    search_fields = ["title", "description"]
```

- [ ] **Step 6: Create and run the migration**

```bash
docker compose run --rm web python manage.py makemigrations boards
docker compose run --rm web python manage.py migrate
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `docker compose run --rm web pytest boards/tests/test_card_model.py`
Expected: PASS — 9 passed.

- [ ] **Step 8: Commit**

```bash
git add boards/
git commit -m "feat: card model with priority, due date and column position"
```

---

### Task 7: Card API

**Files:**
- Modify: `boards/serializers.py` — add `CardSerializer`
- Modify: `boards/views.py` — add `CardViewSet`, add `cards` action to `BoardViewSet`
- Modify: `boards/urls.py` — register the card routes
- Test: `boards/tests/test_card_api.py`

**Interfaces:**
- Consumes: `Card`, `next_position` (Task 6), `UserSerializer` (Task 3)
- Produces: `boards.serializers.CardSerializer` exposing `priority_label` and `assignee_detail` as read-only extras; endpoints `GET /api/boards/{id}/cards/`, `POST /api/cards/`, `GET|PATCH|DELETE /api/cards/{id}/`. Task 8 adds an action to the same `CardViewSet`.

---

- [ ] **Step 1: Write the failing test**

`boards/tests/test_card_api.py`:

```python
import pytest

from boards.models import Board, Card


@pytest.fixture
def board(user):
    return Board.objects.create(name="Test Board", created_by=user)


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, board):
    assert client.get(f"/api/boards/{board.id}/cards/").status_code == 403


@pytest.mark.django_db
def test_listing_a_boards_cards(auth_client, board, user):
    Card.objects.create(board=board, title="First", position=0)
    Card.objects.create(board=board, title="Second", position=1)
    other_board = Board.objects.create(name="Elsewhere", created_by=user)
    Card.objects.create(board=other_board, title="Not mine")

    response = auth_client.get(f"/api/boards/{board.id}/cards/")

    assert response.status_code == 200
    assert [card["title"] for card in response.json()] == ["First", "Second"]


@pytest.mark.django_db
def test_creating_a_card_sets_creator_and_appends_it(auth_client, board, user):
    Card.objects.create(board=board, title="Existing", status="todo", position=0)

    response = auth_client.post(
        "/api/cards/",
        {"board": board.id, "title": "New card"},
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["position"] == 1
    assert body["status"] == "todo"
    assert body["priority"] == 2
    assert body["priority_label"] == "Medium"
    assert Card.objects.get(title="New card").created_by == user


@pytest.mark.django_db
def test_creating_a_card_with_an_assignee_and_a_due_date(auth_client, board, other_user):
    response = auth_client.post(
        "/api/cards/",
        {
            "board": board.id,
            "title": "Assigned",
            "assignee": other_user.id,
            "due_date": "2026-08-15",
            "priority": 3,
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["assignee_detail"]["username"] == "bob"
    assert body["due_date"] == "2026-08-15"
    assert body["priority_label"] == "High"


@pytest.mark.django_db
def test_editing_a_card(auth_client, board):
    card = Card.objects.create(board=board, title="Before")

    response = auth_client.patch(
        f"/api/cards/{card.id}/",
        {"title": "After", "description": "Now with detail"},
        content_type="application/json",
    )

    assert response.status_code == 200
    card.refresh_from_db()
    assert card.title == "After"
    assert card.description == "Now with detail"


@pytest.mark.django_db
def test_unassigning_a_card(auth_client, board, other_user):
    card = Card.objects.create(board=board, title="Assigned", assignee=other_user)

    response = auth_client.patch(
        f"/api/cards/{card.id}/",
        {"assignee": None},
        content_type="application/json",
    )

    assert response.status_code == 200
    card.refresh_from_db()
    assert card.assignee is None


@pytest.mark.django_db
def test_deleting_a_card(auth_client, board):
    card = Card.objects.create(board=board, title="Doomed")
    assert auth_client.delete(f"/api/cards/{card.id}/").status_code == 204
    assert not Card.objects.filter(id=card.id).exists()


@pytest.mark.django_db
def test_position_cannot_be_set_directly(auth_client, board):
    response = auth_client.post(
        "/api/cards/",
        {"board": board.id, "title": "Sneaky", "position": 99},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["position"] == 0


@pytest.mark.django_db
def test_title_is_required(auth_client, board):
    response = auth_client.post(
        "/api/cards/", {"board": board.id}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "title" in response.json()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose run --rm web pytest boards/tests/test_card_api.py`
Expected: FAIL — 404s, no card routes.

- [ ] **Step 3: Add the card serializer**

Append to `boards/serializers.py`, and extend the import at the top to `from .models import Board, Card`:

```python
class CardSerializer(serializers.ModelSerializer):
    assignee_detail = UserSerializer(source="assignee", read_only=True)
    created_by = UserSerializer(read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = Card
        fields = [
            "id", "board", "title", "description",
            "status", "priority", "priority_label", "due_date",
            "assignee", "assignee_detail",
            "position", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["position"]
```

> **Why `position` is read-only:** ordering is owned by the move endpoint in Task 8. Letting a plain edit set it would give two code paths writing the same field, which is how boards end up with three cards all claiming position 0.

- [ ] **Step 4: Add the card viewset and the board's cards action**

Replace `boards/views.py` entirely:

```python
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Board, Card
from .serializers import BoardSerializer, CardSerializer
from .services import next_position


class BoardViewSet(viewsets.ModelViewSet):
    """Every signed-in person sees every board — the team is small and shares its work."""

    queryset = Board.objects.select_related("created_by")
    serializer_class = BoardSerializer
    pagination_class = None

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["get"])
    def cards(self, request, pk=None):
        board = self.get_object()
        cards = board.cards.select_related("assignee", "created_by")
        return Response(CardSerializer(cards, many=True).data)


class CardViewSet(viewsets.ModelViewSet):
    queryset = Card.objects.select_related("board", "assignee", "created_by")
    serializer_class = CardSerializer
    pagination_class = None

    def perform_create(self, serializer):
        board = serializer.validated_data["board"]
        status = serializer.validated_data.get("status", Card.Status.TODO)
        serializer.save(
            created_by=self.request.user,
            position=next_position(board.id, status),
        )
```

- [ ] **Step 5: Register the card routes**

Replace `boards/urls.py`:

```python
from rest_framework.routers import DefaultRouter

from .views import BoardViewSet, CardViewSet

router = DefaultRouter()
router.register("boards", BoardViewSet, basename="board")
router.register("cards", CardViewSet, basename="card")

urlpatterns = router.urls
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `docker compose run --rm web pytest boards/tests/test_card_api.py`
Expected: PASS — 9 passed.

- [ ] **Step 7: Commit**

```bash
git add boards/
git commit -m "feat: card crud api"
```

---

### Task 8: The move endpoint

**Files:**
- Modify: `boards/services.py` — add `move_card`
- Modify: `boards/serializers.py` — add `MoveCardSerializer`
- Modify: `boards/views.py` — add the `move` action to `CardViewSet`
- Test: `boards/tests/test_card_move.py`

**Interfaces:**
- Consumes: `Card` (Task 6), `CardViewSet` (Task 7)
- Produces: `boards.services.move_card(card: Card, new_status: str, new_position: int) -> Card`; endpoint `POST /api/cards/{id}/move/` taking `{"status": str, "position": int}`

---

- [ ] **Step 1: Write the failing test**

`boards/tests/test_card_move.py`:

```python
import pytest

from boards.models import Board, Card


@pytest.fixture
def board(user):
    return Board.objects.create(name="Test Board", created_by=user)


@pytest.fixture
def todo_cards(board):
    return [
        Card.objects.create(board=board, title=title, status="todo", position=index)
        for index, title in enumerate(["A", "B", "C"])
    ]


def titles_in(board, status):
    return [
        card.title
        for card in Card.objects.filter(board=board, status=status).order_by(
            "position", "id"
        )
    ]


@pytest.mark.django_db
def test_moving_a_card_up_within_its_column(auth_client, board, todo_cards):
    card_c = todo_cards[2]

    response = auth_client.post(
        f"/api/cards/{card_c.id}/move/",
        {"status": "todo", "position": 0},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert titles_in(board, "todo") == ["C", "A", "B"]


@pytest.mark.django_db
def test_moving_a_card_down_within_its_column(auth_client, board, todo_cards):
    card_a = todo_cards[0]

    auth_client.post(
        f"/api/cards/{card_a.id}/move/",
        {"status": "todo", "position": 2},
        content_type="application/json",
    )

    assert titles_in(board, "todo") == ["B", "C", "A"]


@pytest.mark.django_db
def test_moving_a_card_to_another_column(auth_client, board, todo_cards):
    card_b = todo_cards[1]

    response = auth_client.post(
        f"/api/cards/{card_b.id}/move/",
        {"status": "in_progress", "position": 0},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert titles_in(board, "todo") == ["A", "C"]
    assert titles_in(board, "in_progress") == ["B"]


@pytest.mark.django_db
def test_the_source_column_closes_its_gap(auth_client, board, todo_cards):
    auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "done", "position": 0},
        content_type="application/json",
    )

    remaining = Card.objects.filter(board=board, status="todo").order_by("position")
    assert [card.position for card in remaining] == [0, 1]


@pytest.mark.django_db
def test_dropping_into_the_middle_of_a_populated_column(auth_client, board, todo_cards):
    Card.objects.create(board=board, title="X", status="done", position=0)
    Card.objects.create(board=board, title="Y", status="done", position=1)

    auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "done", "position": 1},
        content_type="application/json",
    )

    assert titles_in(board, "done") == ["X", "A", "Y"]


@pytest.mark.django_db
def test_an_oversized_position_lands_at_the_end(auth_client, board, todo_cards):
    auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "todo", "position": 999},
        content_type="application/json",
    )

    assert titles_in(board, "todo") == ["B", "C", "A"]


@pytest.mark.django_db
def test_positions_stay_contiguous_from_zero(auth_client, board, todo_cards):
    auth_client.post(
        f"/api/cards/{todo_cards[1].id}/move/",
        {"status": "todo", "position": 0},
        content_type="application/json",
    )

    positions = list(
        Card.objects.filter(board=board, status="todo")
        .order_by("position")
        .values_list("position", flat=True)
    )
    assert positions == [0, 1, 2]


@pytest.mark.django_db
def test_a_move_never_touches_another_board(auth_client, board, todo_cards, user):
    other_board = Board.objects.create(name="Elsewhere", created_by=user)
    untouched = Card.objects.create(
        board=other_board, title="Untouched", status="todo", position=7
    )

    auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "todo", "position": 2},
        content_type="application/json",
    )

    untouched.refresh_from_db()
    assert untouched.position == 7


@pytest.mark.django_db
def test_an_unknown_status_is_rejected(auth_client, todo_cards):
    response = auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "archived", "position": 0},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_a_negative_position_is_rejected(auth_client, todo_cards):
    response = auth_client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "todo", "position": -1},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, todo_cards):
    response = client.post(
        f"/api/cards/{todo_cards[0].id}/move/",
        {"status": "done", "position": 0},
        content_type="application/json",
    )
    assert response.status_code == 403
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose run --rm web pytest boards/tests/test_card_move.py`
Expected: FAIL — 404, no `move` route.

- [ ] **Step 3: Write the move service**

Append to `boards/services.py`, and extend the imports at the top to:

```python
from django.db import transaction
from django.db.models import Max
```

```python
@transaction.atomic
def move_card(card: Card, new_status: str, new_position: int) -> Card:
    """Drop a card into a column at a position, then renumber the affected columns.

    Every card on the board is locked, in a stable id order. That is heavier than
    locking two columns, but a board holds tens of rows, and a consistent lock order
    is what stops two simultaneous drags deadlocking each other.
    """
    locked = list(
        Card.objects.select_for_update()
        .filter(board_id=card.board_id)
        .order_by("id")
    )

    old_status = card.status
    card.status = new_status

    def renumber(status: str) -> list[Card]:
        column = [c for c in locked if c.status == status and c.pk != card.pk]
        column.sort(key=lambda c: (c.position, c.pk))

        if status == new_status:
            index = max(0, min(new_position, len(column)))
            column.insert(index, card)

        for index, member in enumerate(column):
            member.position = index
        return column

    touched = renumber(new_status)
    if old_status != new_status:
        touched += renumber(old_status)

    Card.objects.bulk_update(touched, ["position", "status"])
    return card
```

> **Why renumber instead of shifting neighbours:** shifting is fewer writes but leaves the column's numbering dependent on its history. Renumbering makes the invariant "positions are `0..n-1`, always" — trivially checkable, and it self-heals any drift a bug introduced earlier.

- [ ] **Step 4: Write the move serializer**

Append to `boards/serializers.py`:

```python
class MoveCardSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Card.Status.choices)
    position = serializers.IntegerField(min_value=0)
```

- [ ] **Step 5: Add the move action**

In `boards/views.py`, extend the imports:

```python
from .serializers import BoardSerializer, CardSerializer, MoveCardSerializer
from .services import move_card, next_position
```

and add this method to `CardViewSet`:

```python
    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        card = self.get_object()

        serializer = MoveCardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        move_card(
            card,
            serializer.validated_data["status"],
            serializer.validated_data["position"],
        )
        card.refresh_from_db()
        return Response(CardSerializer(card).data)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `docker compose run --rm web pytest boards/tests/test_card_move.py`
Expected: PASS — 11 passed.

- [ ] **Step 7: Run the whole suite**

Run: `docker compose run --rm web pytest`
Expected: PASS — everything from Tasks 1–8 green.

- [ ] **Step 8: Commit**

```bash
git add boards/
git commit -m "feat: card move endpoint with column renumbering"
```

---

### Task 9: Comments

**Files:**
- Modify: `boards/models.py` — add `Comment`
- Modify: `boards/admin.py` — register `Comment`
- Modify: `boards/serializers.py` — add `CommentSerializer`
- Modify: `boards/views.py` — add `comments` action to `CardViewSet`, add `CommentViewSet`
- Modify: `boards/urls.py` — register the comment routes
- Test: `boards/tests/test_comments.py`

**Interfaces:**
- Consumes: `Card` (Task 6), `CardViewSet` (Task 7), `UserSerializer` (Task 3)
- Produces: `boards.models.Comment`; endpoints `GET|POST /api/cards/{id}/comments/` and `DELETE /api/comments/{id}/`

---

- [ ] **Step 1: Write the failing test**

`boards/tests/test_comments.py`:

```python
import pytest

from boards.models import Board, Card, Comment


@pytest.fixture
def board(user):
    return Board.objects.create(name="Test Board", created_by=user)


@pytest.fixture
def card(board):
    return Card.objects.create(board=board, title="Discuss me")


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client, card):
    assert client.get(f"/api/cards/{card.id}/comments/").status_code == 403


@pytest.mark.django_db
def test_posting_a_comment_records_the_author(auth_client, card, user):
    response = auth_client.post(
        f"/api/cards/{card.id}/comments/",
        {"body": "Started on this"},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["author"]["username"] == "alice"
    assert Comment.objects.get(card=card).author == user


@pytest.mark.django_db
def test_comments_come_back_oldest_first(auth_client, card, user):
    Comment.objects.create(card=card, author=user, body="First")
    Comment.objects.create(card=card, author=user, body="Second")

    response = auth_client.get(f"/api/cards/{card.id}/comments/")

    assert [comment["body"] for comment in response.json()] == ["First", "Second"]


@pytest.mark.django_db
def test_comments_are_scoped_to_their_card(auth_client, board, card, user):
    other_card = Card.objects.create(board=board, title="Elsewhere")
    Comment.objects.create(card=card, author=user, body="Mine")
    Comment.objects.create(card=other_card, author=user, body="Not mine")

    response = auth_client.get(f"/api/cards/{card.id}/comments/")

    assert [comment["body"] for comment in response.json()] == ["Mine"]


@pytest.mark.django_db
def test_an_author_can_delete_their_own_comment(auth_client, card, user):
    comment = Comment.objects.create(card=card, author=user, body="Mine to delete")

    assert auth_client.delete(f"/api/comments/{comment.id}/").status_code == 204
    assert not Comment.objects.filter(id=comment.id).exists()


@pytest.mark.django_db
def test_nobody_can_delete_someone_elses_comment(auth_client, card, other_user):
    comment = Comment.objects.create(card=card, author=other_user, body="Not yours")

    assert auth_client.delete(f"/api/comments/{comment.id}/").status_code == 403
    assert Comment.objects.filter(id=comment.id).exists()


@pytest.mark.django_db
def test_an_empty_comment_is_rejected(auth_client, card):
    response = auth_client.post(
        f"/api/cards/{card.id}/comments/",
        {"body": "   "},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_deleting_a_card_deletes_its_comments(auth_client, card, user):
    Comment.objects.create(card=card, author=user, body="Goes with the card")
    card.delete()
    assert Comment.objects.count() == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose run --rm web pytest boards/tests/test_comments.py`
Expected: FAIL — `ImportError: cannot import name 'Comment' from 'boards.models'`.

- [ ] **Step 3: Add the Comment model**

Append to `boards/models.py`:

```python
class Comment(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="comments",
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.author} on {self.card}"
```

- [ ] **Step 4: Register in the admin**

Append to `boards/admin.py`:

```python
from .models import Comment


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["card", "author", "created_at"]
    search_fields = ["body"]
```

- [ ] **Step 5: Add the serializer**

Append to `boards/serializers.py`, and extend the model import to `from .models import Board, Card, Comment`:

```python
class CommentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "card", "author", "body", "created_at"]
        read_only_fields = ["card"]

    def validate_body(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("A comment cannot be empty.")
        return value
```

- [ ] **Step 6: Add the views**

In `boards/views.py`, extend the imports:

```python
from rest_framework import mixins, viewsets
from rest_framework.exceptions import PermissionDenied

from .models import Board, Card, Comment
from .serializers import (
    BoardSerializer,
    CardSerializer,
    CommentSerializer,
    MoveCardSerializer,
)
```

Add this method to `CardViewSet`:

```python
    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        card = self.get_object()

        if request.method == "POST":
            serializer = CommentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save(card=card, author=request.user)
            return Response(serializer.data, status=201)

        thread = card.comments.select_related("author")
        return Response(CommentSerializer(thread, many=True).data)
```

And add this viewset at the end of the file:

```python
class CommentViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Deletion only — comments are created through the card's own endpoint."""

    queryset = Comment.objects.select_related("author")
    serializer_class = CommentSerializer

    def perform_destroy(self, instance):
        if instance.author != self.request.user:
            raise PermissionDenied("You can only delete your own comments.")
        instance.delete()
```

- [ ] **Step 7: Register the comment routes**

In `boards/urls.py`, extend the import to include `CommentViewSet` and add:

```python
router.register("comments", CommentViewSet, basename="comment")
```

- [ ] **Step 8: Create and run the migration**

```bash
docker compose run --rm web python manage.py makemigrations boards
docker compose run --rm web python manage.py migrate
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `docker compose run --rm web pytest boards/tests/test_comments.py`
Expected: PASS — 8 passed.

- [ ] **Step 10: Commit**

```bash
git add boards/
git commit -m "feat: card comments with author-only deletion"
```

---

### Task 10: My tasks and the users list

**Files:**
- Create: `boards/views_me.py`
- Modify: `accounts/views.py` — add `UserListView`
- Modify: `accounts/urls.py` — add the users route
- Modify: `config/urls.py` — include the me route
- Test: `boards/tests/test_my_tasks.py`, `accounts/tests/test_users_api.py`

**Interfaces:**
- Consumes: `Card` (Task 6), `CardSerializer` (Task 7), `UserSerializer` (Task 3)
- Produces: endpoints `GET /api/me/tasks/` and `GET /api/users/`. These are the last two endpoints in the spec's §7.

---

- [ ] **Step 1: Write the failing tests**

`boards/tests/test_my_tasks.py`:

```python
import datetime

import pytest

from boards.models import Board, Card


@pytest.fixture
def board(user):
    return Board.objects.create(name="Test Board", created_by=user)


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client):
    assert client.get("/api/me/tasks/").status_code == 403


@pytest.mark.django_db
def test_only_my_cards_come_back(auth_client, board, user, other_user):
    Card.objects.create(board=board, title="Mine", assignee=user)
    Card.objects.create(board=board, title="Theirs", assignee=other_user)
    Card.objects.create(board=board, title="Nobody's")

    response = auth_client.get("/api/me/tasks/")

    assert response.status_code == 200
    assert [card["title"] for card in response.json()] == ["Mine"]


@pytest.mark.django_db
def test_my_cards_span_every_board(auth_client, board, user):
    second_board = Board.objects.create(name="Second", created_by=user)
    Card.objects.create(board=board, title="From board one", assignee=user)
    Card.objects.create(board=second_board, title="From board two", assignee=user)

    response = auth_client.get("/api/me/tasks/")

    assert {card["title"] for card in response.json()} == {
        "From board one",
        "From board two",
    }


@pytest.mark.django_db
def test_soonest_due_first_with_undated_cards_last(auth_client, board, user):
    Card.objects.create(board=board, title="No date", assignee=user)
    Card.objects.create(
        board=board, title="Later", assignee=user, due_date=datetime.date(2026, 9, 1)
    )
    Card.objects.create(
        board=board, title="Sooner", assignee=user, due_date=datetime.date(2026, 8, 1)
    )

    response = auth_client.get("/api/me/tasks/")

    assert [card["title"] for card in response.json()] == ["Sooner", "Later", "No date"]


@pytest.mark.django_db
def test_undated_cards_break_ties_on_priority(auth_client, board, user):
    Card.objects.create(board=board, title="Low", assignee=user, priority=1)
    Card.objects.create(board=board, title="High", assignee=user, priority=3)

    response = auth_client.get("/api/me/tasks/")

    assert [card["title"] for card in response.json()] == ["High", "Low"]


@pytest.mark.django_db
def test_finished_cards_are_excluded(auth_client, board, user):
    Card.objects.create(board=board, title="Still going", assignee=user, status="todo")
    Card.objects.create(board=board, title="Finished", assignee=user, status="done")

    response = auth_client.get("/api/me/tasks/")

    assert [card["title"] for card in response.json()] == ["Still going"]
```

`accounts/tests/test_users_api.py`:

```python
import pytest


@pytest.mark.django_db
def test_anonymous_callers_are_rejected(client):
    assert client.get("/api/users/").status_code == 403


@pytest.mark.django_db
def test_listing_users_for_the_assignee_dropdown(auth_client, user, other_user):
    response = auth_client.get("/api/users/")

    assert response.status_code == 200
    assert {row["username"] for row in response.json()} == {"alice", "bob"}
    assert set(response.json()[0]) == {"id", "username", "display_name"}


@pytest.mark.django_db
def test_deactivated_users_are_hidden(auth_client, user, other_user):
    other_user.is_active = False
    other_user.save()

    response = auth_client.get("/api/users/")

    assert [row["username"] for row in response.json()] == ["alice"]


@pytest.mark.django_db
def test_no_password_hash_is_ever_exposed(auth_client, user):
    body = auth_client.get("/api/users/").json()
    assert "password" not in body[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose run --rm web pytest boards/tests/test_my_tasks.py accounts/tests/test_users_api.py`
Expected: FAIL — 404s, neither route exists.

- [ ] **Step 3: Write the my-tasks view**

`boards/views_me.py`:

```python
from django.db.models import F
from rest_framework.generics import ListAPIView

from .models import Card
from .serializers import CardSerializer


class MyTasksView(ListAPIView):
    """Everything assigned to me that is still open, soonest deadline first."""

    serializer_class = CardSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            Card.objects.filter(assignee=self.request.user)
            .exclude(status=Card.Status.DONE)
            .select_related("board", "assignee", "created_by")
            .order_by(F("due_date").asc(nulls_last=True), "-priority", "id")
        )
```

> **On `nulls_last`:** MySQL sorts `NULL` first by default, which would put every undated card above genuinely urgent work — the exact opposite of what this screen is for.

- [ ] **Step 4: Write the users view**

Append to `accounts/views.py`, extending the imports with:

```python
from django.contrib.auth import get_user_model
from rest_framework.generics import ListAPIView
```

```python
class UserListView(ListAPIView):
    """Names for the assignee dropdown. Never more than id, username and display name."""

    serializer_class = UserSerializer
    pagination_class = None
    queryset = get_user_model().objects.filter(is_active=True).order_by("username")
```

- [ ] **Step 5: Wire both routes**

In `accounts/urls.py`, extend the import to include `UserListView` and add to `urlpatterns`:

```python
    path("users/", UserListView.as_view(), name="user-list"),
```

In `config/urls.py`, add:

```python
    path("api/me/tasks/", MyTasksView.as_view(), name="my-tasks"),
```

with the import:

```python
from boards.views_me import MyTasksView
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `docker compose run --rm web pytest boards/tests/test_my_tasks.py accounts/tests/test_users_api.py`
Expected: PASS — 10 passed.

- [ ] **Step 7: Run the whole suite**

Run: `docker compose run --rm web pytest`
Expected: PASS — every test from Tasks 1–10 green.

- [ ] **Step 8: Commit**

```bash
git add boards/ accounts/ config/urls.py
git commit -m "feat: my tasks and users list endpoints"
```

---

### Task 11: Seed command and a walk through the whole API

**Files:**
- Create: `boards/management/__init__.py`, `boards/management/commands/__init__.py`, `boards/management/commands/seed_demo.py`
- Create: `docs/api.md`
- Test: `boards/tests/test_seed_demo.py`

**Interfaces:**
- Consumes: everything from Tasks 2–10
- Produces: `python manage.py seed_demo` — realistic data for building the UI against in Plan 2

---

- [ ] **Step 1: Write the failing test**

`boards/tests/test_seed_demo.py`:

```python
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from boards.models import Board, Card


@pytest.mark.django_db
def test_seed_creates_boards_users_and_cards():
    call_command("seed_demo")

    assert Board.objects.count() == 2
    assert Card.objects.count() >= 8
    assert get_user_model().objects.filter(is_active=True).count() >= 3


@pytest.mark.django_db
def test_seed_fills_every_column():
    call_command("seed_demo")

    for status in ["todo", "in_progress", "done"]:
        assert Card.objects.filter(status=status).exists()


@pytest.mark.django_db
def test_seed_is_safe_to_run_twice():
    call_command("seed_demo")
    call_command("seed_demo")

    assert Board.objects.count() == 2


@pytest.mark.django_db
def test_seeded_positions_are_contiguous_within_each_column():
    call_command("seed_demo")

    for board in Board.objects.all():
        for status in ["todo", "in_progress", "done"]:
            positions = list(
                Card.objects.filter(board=board, status=status)
                .order_by("position")
                .values_list("position", flat=True)
            )
            assert positions == list(range(len(positions)))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `docker compose run --rm web pytest boards/tests/test_seed_demo.py`
Expected: FAIL — `CommandError: Unknown command: 'seed_demo'`.

- [ ] **Step 3: Write the seed command**

```bash
mkdir -p boards/management/commands
touch boards/management/__init__.py boards/management/commands/__init__.py
```

`boards/management/commands/seed_demo.py`:

```python
import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from boards.models import Board, Card

DEMO_PASSWORD = "demo-password-12345"

PEOPLE = [
    ("asha", "Asha", "Rao"),
    ("kabir", "Kabir", "Menon"),
    ("lena", "Lena", "Fischer"),
]

BOARDS = {
    "Website Redesign": [
        ("Audit the current pages", "todo", 2, None),
        ("Wireframe the new homepage", "todo", 3, 7),
        ("Pick a typeface", "todo", 1, None),
        ("Write the copy deck", "in_progress", 2, 3),
        ("Build the component library", "in_progress", 3, 14),
        ("Ship the staging build", "done", 2, None),
    ],
    "Internal Tools": [
        ("Replace the spreadsheet", "todo", 3, 10),
        ("Document the deploy steps", "todo", 1, None),
        ("Move CI to the new runner", "in_progress", 2, 5),
        ("Retire the old dashboard", "done", 1, None),
    ],
}


class Command(BaseCommand):
    help = "Create demo boards, people and cards for developing the UI against."

    def handle(self, *args, **options):
        User = get_user_model()
        today = datetime.date.today()

        people = []
        for username, first_name, last_name in PEOPLE:
            person, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first_name, "last_name": last_name},
            )
            if created:
                person.set_password(DEMO_PASSWORD)
                person.save()
            people.append(person)

        for index, (board_name, cards) in enumerate(BOARDS.items()):
            board, created = Board.objects.get_or_create(
                name=board_name,
                defaults={
                    "description": f"Demo board: {board_name}",
                    "created_by": people[0],
                },
            )
            if not created:
                continue

            counters = {"todo": 0, "in_progress": 0, "done": 0}
            for card_index, (title, status, priority, due_in_days) in enumerate(cards):
                Card.objects.create(
                    board=board,
                    title=title,
                    description=f"Seeded card for {board_name}.",
                    status=status,
                    priority=priority,
                    due_date=None if due_in_days is None
                    else today + datetime.timedelta(days=due_in_days),
                    assignee=people[card_index % len(people)],
                    position=counters[status],
                    created_by=people[index % len(people)],
                )
                counters[status] += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Board.objects.count()} boards, "
                f"{Card.objects.count()} cards. "
                f"Demo logins use the password: {DEMO_PASSWORD}"
            )
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `docker compose run --rm web pytest boards/tests/test_seed_demo.py`
Expected: PASS — 4 passed.

- [ ] **Step 5: Seed your development database**

```bash
docker compose run --rm web python manage.py seed_demo
```

- [ ] **Step 6: Walk the API by hand**

This is the acceptance test for the whole plan. Start the server with `docker compose up`, then in another terminal:

```bash
# Get a CSRF cookie and keep a cookie jar
curl -s -c jar.txt http://localhost:8000/api/auth/csrf/ -o /dev/null

# Log in as a seeded user
curl -s -b jar.txt -c jar.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $(grep csrftoken jar.txt | awk '{print $7}')" \
  -d '{"username":"asha","password":"demo-password-12345"}' \
  http://localhost:8000/api/auth/login/

# Who am I, what boards exist, what is on the first one
curl -s -b jar.txt http://localhost:8000/api/auth/me/
curl -s -b jar.txt http://localhost:8000/api/boards/
curl -s -b jar.txt http://localhost:8000/api/boards/1/cards/

# What is assigned to me
curl -s -b jar.txt http://localhost:8000/api/me/tasks/
```

Confirm each returns JSON and no request 500s. Then `rm jar.txt` and stop the server.

- [ ] **Step 7: Write `docs/api.md`**

```markdown
# Tasky API

Session-cookie auth, same origin. Every endpoint needs a signed-in session except
`GET /api/auth/csrf/` and `POST /api/auth/login/`.

Any unsafe request (POST, PATCH, DELETE) must carry an `X-CSRFToken` header whose value
is the `csrftoken` cookie. Call `GET /api/auth/csrf/` once on app load to be handed one.

## Auth
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/auth/csrf/` | — | 204, sets the `csrftoken` cookie |
| POST | `/api/auth/login/` | `{username, password}` | the user, or 400 |
| POST | `/api/auth/logout/` | — | 204 |
| GET | `/api/auth/me/` | — | the signed-in user |

## Boards
| Method | Path | Notes |
|---|---|---|
| GET | `/api/boards/` | every board; unpaginated |
| POST | `/api/boards/` | `{name, description}`; creator is taken from the session |
| GET/PATCH/DELETE | `/api/boards/{id}/` | |
| GET | `/api/boards/{id}/cards/` | every card on the board, ordered by column position |

## Cards
| Method | Path | Notes |
|---|---|---|
| POST | `/api/cards/` | `{board, title, description?, status?, priority?, due_date?, assignee?}` |
| GET/PATCH/DELETE | `/api/cards/{id}/` | `position` is read-only here |
| POST | `/api/cards/{id}/move/` | `{status, position}` — the drag-and-drop endpoint |

`status` is one of `todo`, `in_progress`, `done`.
`priority` is `1` low, `2` medium, `3` high; responses also carry `priority_label`.

## Comments
| Method | Path | Notes |
|---|---|---|
| GET/POST | `/api/cards/{id}/comments/` | POST takes `{body}`; author comes from the session |
| DELETE | `/api/comments/{id}/` | author only, otherwise 403 |

## Me
| Method | Path | Notes |
|---|---|---|
| GET | `/api/me/tasks/` | my open cards across every board, soonest due first |
| GET | `/api/users/` | `id`, `username`, `display_name` for the assignee dropdown |
```

- [ ] **Step 8: Run the whole suite one last time**

Run: `docker compose run --rm web pytest`
Expected: PASS — every test in the project green.

- [ ] **Step 9: Commit**

```bash
git add boards/ docs/api.md
git commit -m "feat: demo seed command and api documentation"
```

---

## Done when

- `docker compose run --rm web pytest` is green across all eleven tasks
- `/admin/` lets you create a teammate who can then log in through `POST /api/auth/login/`
- A card can be created, assigned, given a priority and due date, dragged between all three columns via `POST /api/cards/{id}/move/`, and commented on
- `GET /api/me/tasks/` returns that person's open cards across every board, soonest deadline first
- Column positions are contiguous from zero after any sequence of moves

## What this plan does NOT cover

Deliberately out of scope, handled in the two plans that follow:

- **The React UI** — Plan 2. The `seed_demo` command exists so Plan 2 has realistic data to build against on day one.
- **Serving the built React files from Django** — Plan 2, where `STATICFILES_DIRS` and the catch-all route get added.
- **Deployment** — Plan 3: production settings split, gunicorn tuning, `collectstatic`, the Apache reverse-proxy config, RDS connection and security groups, and `DEBUG=0` hardening.
