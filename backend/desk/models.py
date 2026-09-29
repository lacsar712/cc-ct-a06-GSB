from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


DEFAULT_RANGE_LOWER = -20
DEFAULT_RANGE_UPPER = 20


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
    """量程台上下限。全台只有一行（固定 pk=1），仅操作员可改。"""

    lower_limit = models.IntegerField(default=DEFAULT_RANGE_LOWER, verbose_name="下限")
    upper_limit = models.IntegerField(default=DEFAULT_RANGE_UPPER, verbose_name="上限")
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="range_updates",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "量程上下限"
        verbose_name_plural = verbose_name

    def save(self, *args, **kwargs):
        if self.lower_limit > self.upper_limit:
            raise ValidationError("量程下限不能大于上限")
        if self.pk is None:
            self.pk = 1  # 单行表：新实例固定落到 pk=1
        elif self.pk != 1:
            raise ValidationError("量程上下限只允许存在一行配置")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("量程上下限不允许删除")

    def __str__(self) -> str:
        return f"[{self.lower_limit}, {self.upper_limit}]"


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
    # 单据上当前刀补原文；交单时写入，改正后随之更新（履历里的旧原文不受影响）
    offset_raw = models.CharField(max_length=32, blank=True, default="")
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


class AppendOnlyQuerySet(models.QuerySet):
    """履历只许插入：任何批量改/删路径一律拒绝。"""

    def update(self, *args, **kwargs):
        raise ValidationError("交单履历为追加式记录，旧值不得修改")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("交单履历为追加式记录，旧值不得修改")

    def delete(self):
        raise ValidationError("交单履历为追加式记录，不得删除")


class OffsetHistory(models.Model):
    """交单履历：每次成功交单追加一条当时刀补原文快照，永不修改。"""

    submission = models.ForeignKey(
        OffsetSubmission,
        on_delete=models.PROTECT,
        related_name="histories",
    )
    tool_code = models.CharField(max_length=32)
    # 交单当时的刀补原文与解析值，事后改正单据也保持不动，用于与单据对照验收
    offset_raw = models.CharField(max_length=32)
    offset_um = models.IntegerField()
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="histories",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "交单履历"
        verbose_name_plural = verbose_name

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("交单履历为追加式记录，旧值不得修改")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("交单履历为追加式记录，不得删除")

    def __str__(self) -> str:
        return f"{self.tool_code} {self.offset_raw} @ {self.created_at:%Y-%m-%d %H:%M}"
