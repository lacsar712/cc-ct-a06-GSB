from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        MACHINIST = "machinist", "操作员"
        AUDITOR = "auditor", "复核员"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MACHINIST,
    )

    @property
    def can_write(self) -> bool:
        return self.role == self.Role.MACHINIST


class RangeSetting(models.Model):
    """量程台区间设置，全台单例（pk=1）。只有操作员可改。"""

    SINGLETON_ID = 1

    lower_limit = models.IntegerField(default=settings.DEFAULT_RANGE_LOWER)
    upper_limit = models.IntegerField(default=settings.DEFAULT_RANGE_UPPER)
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="range_changes",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "量程区间"

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_ID
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "RangeSetting":
        obj, _ = cls.objects.get_or_create(
            pk=cls.SINGLETON_ID,
            defaults={
                "lower_limit": settings.DEFAULT_RANGE_LOWER,
                "upper_limit": settings.DEFAULT_RANGE_UPPER,
            },
        )
        return obj

    def __str__(self) -> str:
        return f"量程区间 [{self.lower_limit}, {self.upper_limit}]"


class OffsetSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "待复核"
        PROCESSING = "processing", "复核中"
        DONE = "done", "已完成"

    class Verdict(models.TextChoices):
        PASS = "合格", "合格"
        FAIL = "超差", "超差"

    tool_code = models.CharField(max_length=32, db_index=True)
    offset_um = models.IntegerField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    verdict = models.CharField(
        max_length=8,
        choices=Verdict.choices,
        blank=True,
        default="",
    )
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.tool_code} {self.offset_um}µm"


class OffsetHistory(models.Model):
    """刀补履历：只追加、不修改、不删除。

    每次成功交单/改正都把当时刀补原文（offset_text）原样快照进来；
    单据上的数字事后被改正时，旧履历记录保持不动，可与单据现值对照验收。
    """

    class Action(models.TextChoices):
        SUBMIT = "submit", "交单"
        CORRECT = "correct", "改正"

    submission = models.ForeignKey(
        OffsetSubmission,
        on_delete=models.CASCADE,
        related_name="history",
    )
    seq = models.PositiveIntegerField()
    action = models.CharField(max_length=8, choices=Action.choices)
    offset_text = models.CharField(max_length=32)
    tool_code = models.CharField(max_length=32)
    operator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="offset_histories",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "seq"],
                name="uniq_history_seq_per_submission",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} {self.tool_code} 刀补原文 {self.offset_text}"
