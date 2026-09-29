import django.db.models.deletion
from django.db import migrations, models

import desk.models


def init_range_setting(apps, schema_editor):
    RangeSetting = apps.get_model("desk", "RangeSetting")
    RangeSetting.objects.create(
        pk=1,
        lower_limit=desk.models.DEFAULT_RANGE_LOWER,
        upper_limit=desk.models.DEFAULT_RANGE_UPPER,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("desk", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RangeSetting",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("lower_limit", models.IntegerField(default=-20, verbose_name="下限")),
                ("upper_limit", models.IntegerField(default=20, verbose_name="上限")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="range_updates",
                        to="desk.user",
                    ),
                ),
            ],
            options={
                "verbose_name": "量程上下限",
                "verbose_name_plural": "量程上下限",
            },
        ),
        migrations.AddField(
            model_name="offsetsubmission",
            name="offset_raw",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.CreateModel(
            name="OffsetHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("tool_code", models.CharField(max_length=32)),
                ("offset_raw", models.CharField(max_length=32)),
                ("offset_um", models.IntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="histories",
                        to="desk.offsetsubmission",
                    ),
                ),
                (
                    "submitted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="histories",
                        to="desk.user",
                    ),
                ),
            ],
            options={
                "verbose_name": "交单履历",
                "verbose_name_plural": "交单履历",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.RunPython(init_range_setting, migrations.RunPython.noop),
    ]
