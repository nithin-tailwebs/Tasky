from django.db import migrations


def backfill_legacy_project(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    ProjectMembership = apps.get_model("projects", "ProjectMembership")
    Board = apps.get_model("boards", "Board")
    Card = apps.get_model("boards", "Card")
    User = apps.get_model("accounts", "User")

    orphan_boards = Board.objects.filter(project__isnull=True)
    if not orphan_boards.exists():
        return  # Fresh database (e.g. every test run) — nothing to backfill.

    owner = (
        User.objects.filter(is_superuser=True).order_by("date_joined", "id").first()
        or User.objects.order_by("date_joined", "id").first()
    )
    if owner is None:
        return  # No users exist yet either — nothing to assign ownership to.

    project = Project.objects.create(
        key="LEGACY",
        name="Legacy Boards",
        description="Boards that existed before projects were introduced.",
    )
    ProjectMembership.objects.create(project=project, user_id=owner.id, role="owner")

    board_ids = list(orphan_boards.values_list("id", flat=True))
    referenced_user_ids = (
        set(orphan_boards.exclude(created_by__isnull=True).values_list("created_by_id", flat=True))
        | set(
            Card.objects.filter(board_id__in=board_ids, created_by__isnull=False)
            .values_list("created_by_id", flat=True)
        )
        | set(
            Card.objects.filter(board_id__in=board_ids, assignee__isnull=False)
            .values_list("assignee_id", flat=True)
        )
    )
    referenced_user_ids.discard(owner.id)

    ProjectMembership.objects.bulk_create(
        ProjectMembership(project=project, user_id=uid, role="member")
        for uid in referenced_user_ids
    )

    orphan_boards.update(project=project)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("boards", "0004_board_project_nullable"),
        ("projects", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(backfill_legacy_project, noop_reverse),
    ]
