from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from desk.auth_utils import hash_password
from desk.models import OffsetHistory, OffsetSubmission, RangeSetting, User


class Command(BaseCommand):
    help = "创建默认账号、量程区间与种子刀补记录（含交单履历）"

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

        # 只在首次播种时建立默认区间 [-20, 20]，不覆盖操作员事后改的上下限
        RangeSetting.load()

        now = timezone.now()
        seeds = [
            ("T01", 5, OffsetSubmission.Verdict.PASS),
            ("T09", 20, OffsetSubmission.Verdict.FAIL),
        ]
        for tool_code, offset_um, verdict in seeds:
            with transaction.atomic():
                submission, created = OffsetSubmission.objects.get_or_create(
                    tool_code=tool_code,
                    offset_um=offset_um,
                    defaults={
                        "status": OffsetSubmission.Status.DONE,
                        "verdict": verdict,
                        "submitted_by": machinist,
                        "reviewed_at": now,
                    },
                )
                if created and not OffsetHistory.objects.filter(
                    submission=submission
                ).exists():
                    OffsetHistory.objects.create(
                        submission=submission,
                        seq=1,
                        action=OffsetHistory.Action.SUBMIT,
                        offset_text=str(offset_um),
                        tool_code=tool_code,
                        operator=machinist,
                    )

        self.stdout.write(self.style.SUCCESS("seed_offset_desk 完成"))
