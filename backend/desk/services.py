"""量程台领域服务：闭区间校验是表单入口与直打服务入口共用的唯一规则来源。"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from desk.models import OffsetHistory, OffsetSubmission, RangeSetting, User


class OffsetOutOfRangeError(ValueError):
    """刀补值越出量程闭区间。message 即两个入口共用的退回规则文案。"""

    def __init__(self, offset_um: int, lower: int, upper: int):
        self.offset_um = offset_um
        self.lower = lower
        self.upper = upper
        super().__init__(range_rule_message(lower, upper))


def range_rule_message(lower: int, upper: int) -> str:
    """两个入口（表单交单 / 直打服务）越界退回时必须说明的同一套规则。"""
    return (
        f"刀补数值只能落在闭区间 [{lower}, {upper}] 内（含端点，单位微米）；"
        f"越界交单一律退回，请由操作员在量程台调整上下限后再交。"
    )


def ensure_within_range(offset_um: int, range_setting: RangeSetting) -> None:
    if not (range_setting.lower_limit <= offset_um <= range_setting.upper_limit):
        raise OffsetOutOfRangeError(
            offset_um,
            range_setting.lower_limit,
            range_setting.upper_limit,
        )


def evaluate_verdict(offset_um: int) -> str:
    if abs(offset_um) <= settings.OFFSET_TOLERANCE_UM:
        return OffsetSubmission.Verdict.PASS
    return OffsetSubmission.Verdict.FAIL


def apply_verdict(submission: OffsetSubmission) -> None:
    submission.verdict = evaluate_verdict(submission.offset_um)
    submission.status = OffsetSubmission.Status.DONE
    submission.reviewed_at = timezone.now()
    submission.save(
        update_fields=["verdict", "status", "reviewed_at"],
    )


def _append_history(
    submission: OffsetSubmission,
    action: str,
    offset_text: str,
    operator: User | None,
) -> OffsetHistory:
    """追加一条履历。调用方必须已开启事务（锁由外层 select_for_update 持有）。"""
    last = (
        OffsetHistory.objects.filter(submission=submission)
        .order_by("-seq")
        .first()
    )
    seq = (last.seq + 1) if last else 1
    return OffsetHistory.objects.create(
        submission=submission,
        seq=seq,
        action=action,
        offset_text=offset_text,
        tool_code=submission.tool_code,
        operator=operator,
    )


@transaction.atomic
def create_submission(
    *,
    user: User,
    tool_code: str,
    offset_um: int,
) -> OffsetSubmission:
    """成功交单：区间校验通过才建单，并把当时刀补原文记进履历。

    表单入口与直打服务入口都走这一个函数，保证同一套规则。
    """
    range_setting = RangeSetting.load()
    ensure_within_range(offset_um, range_setting)

    submission = OffsetSubmission.objects.create(
        tool_code=tool_code,
        offset_um=offset_um,
        submitted_by=user,
        status=OffsetSubmission.Status.PENDING,
    )
    _append_history(
        submission,
        OffsetHistory.Action.SUBMIT,
        str(offset_um),
        user,
    )
    return submission


@transaction.atomic
def correct_submission(
    *,
    user: User,
    submission: OffsetSubmission,
    offset_um: int,
) -> OffsetSubmission:
    """改正单据上的数字：同样过闭区间校验，追加新履历，旧履历一律不动。"""
    submission = (
        OffsetSubmission.objects.select_for_update()
        .select_related("submitted_by")
        .get(pk=submission.pk)
    )
    range_setting = RangeSetting.load()
    ensure_within_range(offset_um, range_setting)

    submission.offset_um = offset_um
    submission.status = OffsetSubmission.Status.PENDING
    submission.verdict = ""
    submission.reviewed_at = None
    submission.save(
        update_fields=["offset_um", "status", "verdict", "reviewed_at"],
    )
    _append_history(
        submission,
        OffsetHistory.Action.CORRECT,
        str(offset_um),
        user,
    )
    return submission
