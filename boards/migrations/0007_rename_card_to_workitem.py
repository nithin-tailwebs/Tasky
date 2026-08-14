from django.conf import settings
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("boards", "0006_board_project_required"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(old_name="Card", new_name="WorkItem"),
        migrations.AlterField(
            model_name="workitem",
            name="board",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="work_items",
                to="boards.board",
            ),
        ),
        migrations.AlterField(
            model_name="workitem",
            name="assignee",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_work_items",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="workitem",
            name="created_by",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="work_items_created",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RenameIndex(
            model_name="workitem",
            old_name="boards_card_board_i_5b59c2_idx",
            new_name="boards_work_board_i_eecf60_idx",
        ),
    ]
