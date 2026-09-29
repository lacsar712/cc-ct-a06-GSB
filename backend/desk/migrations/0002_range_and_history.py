import django.db.models.deletion
from django.db import migrations, models


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
                ("lower_limit", models.IntegerField(default=-20)),
                ("upper_limit", models.IntegerField(default=20)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="range_changes",
                        to="desk.user",
                    ),
                ),
            ],
            options={
                "verbose_name": "量程区间",
            },
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
                ("seq", models.PositiveIntegerField()),
                (
                    "action",
                    models.CharField(
                        choices=[("submit", "交单"), ("correct", "改正")],
                        max_length=8,
                    ),
                ),
                ("offset_text", models.CharField(max_length=32)),
                ("tool_code", models.CharField(max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "operator",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="offset_histories",
                        to="desk.user",
                    ),
                ),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="history",
                        to="desk.offsetsubmission",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="offsethistory",
            constraint=models.UniqueConstraint(
                fields=("submission", "seq"),
                name="uniq_history_seq_per_submission",
            ),
        ),
    ]
