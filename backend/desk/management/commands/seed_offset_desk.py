from django.core.management.base import BaseCommand
from django.utils import timezone

from desk.auth_utils import hash_password
from desk.models import (
    DEFAULT_RANGE_LOWER,
    DEFAULT_RANGE_UPPER,
    OffsetHistory,
    OffsetSubmission,
    RangeSetting,
    User,
)
from desk.services import get_range


class Command(BaseCommand):
    help = "创建默认账号、量程区间与种子刀补记录及履历"

    def handle(self, *args, **options):
        machinist, _ = User.objects.update_or_create(
            username="machinist",
            defaults={
                "role": User.Role.MACHINIST,
                "password": hash_password("machine123456"),
                "is_active": True,
            },
        )
        User.objects.update_or_create(
            username="auditor",
            defaults={
                "role": User.Role.AUDITOR,
                "password": hash_password("audit123456"),
                "is_active": True,
            },
        )

        # 量程台区间：负二十到二十（已被操作员调整过时保留现状，不覆盖）
        setting = get_range()
        if (
            setting.lower_limit != DEFAULT_RANGE_LOWER
            or setting.upper_limit != DEFAULT_RANGE_UPPER
        ):
            self.stdout.write(
                f"保留现有量程区间 [{setting.lower_limit}, {setting.upper_limit}]，不覆盖"
            )

        now = timezone.now()
        seeds = [
            ("T01", 5, OffsetSubmission.Verdict.PASS),
            ("T09", 20, OffsetSubmission.Verdict.FAIL),
        ]
        for tool_code, offset_um, verdict in seeds:
            raw = str(offset_um)
            # 同刀具已有单（含被改正过的种子单）则跳过，保证重启重跑不复活旧值
            submission = (
                OffsetSubmission.objects.filter(tool_code=tool_code)
                .order_by("id")
                .first()
            )
            if submission is None:
                submission = OffsetSubmission.objects.create(
                    tool_code=tool_code,
                    offset_um=offset_um,
                    offset_raw=raw,
                    status=OffsetSubmission.Status.DONE,
                    verdict=verdict,
                    submitted_by=machinist,
                    reviewed_at=now,
                )
            # 履历为追加式：只在缺失时补建快照，已存在则绝不改动
            if not OffsetHistory.objects.filter(submission=submission).exists():
                OffsetHistory.objects.create(
                    submission=submission,
                    tool_code=submission.tool_code,
                    offset_raw=submission.offset_raw or raw,
                    offset_um=submission.offset_um,
                    submitted_by=machinist,
                )

        self.stdout.write(self.style.SUCCESS("seed_offset_desk 完成"))
