import io

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection

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


@pytest.mark.django_db
def test_seed_warns_which_database_it_is_about_to_write_to():
    out = io.StringIO()
    call_command("seed_demo", stdout=out)

    output = out.getvalue()
    assert connection.settings_dict["NAME"] in output
    assert "NEVER" in output
    assert "production" in output.lower()
