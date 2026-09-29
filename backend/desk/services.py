"""刀补交单业务规则。

表单入口（HTTP API）与直打服务入口（直接调用本模块）共用同一套区间规则，
越界文案也只在此处定义一份，避免两个入口说法不一。
"""

import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from desk.models import (
    DEFAULT_RANGE_LOWER,
    DEFAULT_RANGE_UPPER,
    OffsetHistory,
    OffsetSubmission,
    RangeSetting,
)

_INT_RE = re.compile(r"^[+-]?\d+$")

OFFSET_PARSE_ERROR = "刀补数值必须是整数（微米）"
TOOL_CODE_EMPTY_ERROR = "刀具编号不能为空"
RANGE_ORDER_ERROR = "量程下限不能大于上限"


class OffsetOutOfRange(ValueError):
    """刀补数值落在量程闭区间之外。"""


def range_rule_text(lower: int, upper: int, value: int | None = None) -> str:
    """区间规则的唯一文案来源，两个入口退回时都返回这句话。"""
    rule = f"刀补数值只能落在闭区间 [{lower}, {upper}] 微米内（含上下限边界）"
    if value is None:
        return rule
    return f"{rule}；本次数值 {value} 已越界，请退回重填"


def get_range() -> RangeSetting:
    setting, _ = RangeSetting.objects.get_or_create(
        pk=1,
        defaults={
            "lower_limit": DEFAULT_RANGE_LOWER,
            "upper_limit": DEFAULT_RANGE_UPPER,
        },
    )
    return setting


def parse_offset(raw: str | int) -> tuple[str, int]:
    """解析刀补原文，返回（去空格原文, 整数微米值）。"""
    text = str(raw).strip()
    if not _INT_RE.match(text):
        raise ValueError(OFFSET_PARSE_ERROR)
    return text, int(text)


def ensure_in_range(value: int, lower: int, upper: int) -> None:
    """闭区间校验：lower <= value <= upper，越界抛 OffsetOutOfRange。"""
    if value < lower or value > upper:
        raise OffsetOutOfRange(range_rule_text(lower, upper, value))


@transaction.atomic
def create_submission(user, tool_code: str, offset_raw: str | int) -> OffsetSubmission:
    """成功交单：单据与履历快照在同一事务内落库；越界整体退回。"""
    code = (tool_code or "").strip()
    if not code:
        raise ValueError(TOOL_CODE_EMPTY_ERROR)

    raw_text, value = parse_offset(offset_raw)
    setting = get_range()
    ensure_in_range(value, setting.lower_limit, setting.upper_limit)

    submission = OffsetSubmission.objects.create(
        tool_code=code,
        offset_um=value,
        offset_raw=raw_text,
        submitted_by=user,
        status=OffsetSubmission.Status.PENDING,
    )
    # 履历记下交单当时的原文；此后单据再改正，这行也不动
    OffsetHistory.objects.create(
        submission=submission,
        tool_code=code,
        offset_raw=raw_text,
        offset_um=value,
        submitted_by=user,
    )
    return submission


@transaction.atomic
def correct_submission(
    submission: OffsetSubmission, offset_raw: str | int
) -> OffsetSubmission:
    """事后改正单据上的数字：过同一套区间校验并重置回待复核。

    只改单据本身，交单履历一行都不碰。
    """
    raw_text, value = parse_offset(offset_raw)
    setting = get_range()
    ensure_in_range(value, setting.lower_limit, setting.upper_limit)

    submission.offset_um = value
    submission.offset_raw = raw_text
    submission.status = OffsetSubmission.Status.PENDING
    submission.verdict = ""
    submission.reviewed_at = None
    submission.save(
        update_fields=[
            "offset_um",
            "offset_raw",
            "status",
            "verdict",
            "reviewed_at",
        ]
    )
    return submission


@transaction.atomic
def update_range(user, lower: int, upper: int) -> RangeSetting:
    if lower > upper:
        raise ValueError(RANGE_ORDER_ERROR)
    setting = get_range()
    setting.lower_limit = lower
    setting.upper_limit = upper
    setting.updated_by = user
    setting.save(update_fields=["lower_limit", "upper_limit", "updated_by", "updated_at"])
    return setting


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
