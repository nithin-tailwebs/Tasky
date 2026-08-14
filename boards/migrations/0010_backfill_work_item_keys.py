from django.db import migrations


def backfill_keys(apps, schema_editor):
    WorkItem = apps.get_model("boards", "WorkItem")
    Project = apps.get_model("projects", "Project")

    for project in Project.objects.all():
        items = list(
            WorkItem.objects.filter(board__project=project, key__isnull=True)
            .order_by("created_at", "id")
        )
        if not items:
            continue

        counter = project.next_item_number
        for item in items:
            item.key = f"{project.key}-{counter}"
            counter += 1
        WorkItem.objects.bulk_update(items, ["key"])

        project.next_item_number = counter
        project.save(update_fields=["next_item_number"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("boards", "0009_workitem_key_nullable"),
        ("projects", "0002_project_next_item_number"),
    ]
    operations = [
        migrations.RunPython(backfill_keys, noop_reverse),
    ]
