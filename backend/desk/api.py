from datetime import datetime
from typing import Optional

from django.http import HttpRequest
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from desk.auth_utils import bearer_auth, create_access_token, verify_password
from desk.models import OffsetHistory, OffsetSubmission, RangeSetting, User
from desk.services import (
    OffsetOutOfRangeError,
    correct_submission,
    create_submission,
    range_rule_message,
)

api = NinjaAPI(title="数控刀补量程台", version="1.1")


class HealthOut(Schema):
    status: str


class LoginIn(Schema):
    username: str
    password: str


class LoginOut(Schema):
    token: str
    username: str
    role: str
    can_write: bool


class SubmissionIn(Schema):
    tool_code: str
    offset_um: int


class CorrectIn(Schema):
    offset_um: int


class SubmissionOut(Schema):
    id: int
    tool_code: str
    offset_um: int
    status: str
    verdict: str
    created_at: datetime
    reviewed_at: Optional[datetime]


class RangeIn(Schema):
    lower_limit: int
    upper_limit: int


class RangeOut(Schema):
    lower_limit: int
    upper_limit: int
    rule: str
    can_set_limits: bool
    updated_by: Optional[str]
    updated_at: Optional[datetime]


class HistoryOut(Schema):
    id: int
    submission_id: int
    seq: int
    action: str
    action_label: str
    tool_code: str
    offset_text: str
    current_offset_um: int
    matches_current: bool
    operator: Optional[str]
    created_at: datetime


def _to_out(row: OffsetSubmission) -> SubmissionOut:
    return SubmissionOut(
        id=row.id,
        tool_code=row.tool_code,
        offset_um=row.offset_um,
        status=row.status,
        verdict=row.verdict or "",
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
    )


def _range_out(user: User, range_setting: RangeSetting) -> RangeOut:
    return RangeOut(
        lower_limit=range_setting.lower_limit,
        upper_limit=range_setting.upper_limit,
        rule=range_rule_message(
            range_setting.lower_limit,
            range_setting.upper_limit,
        ),
        can_set_limits=user.can_write,
        updated_by=range_setting.updated_by.username
        if range_setting.updated_by
        else None,
        updated_at=range_setting.updated_at,
    )


@api.get("/health", response=HealthOut)
def health(request: HttpRequest):
    return {"status": "ok"}


@api.post("/auth/login", response=LoginOut)
def login(request: HttpRequest, body: LoginIn):
    try:
        user = User.objects.get(username=body.username)
    except User.DoesNotExist:
        raise HttpError(401, "用户名或密码错误")
    if not verify_password(body.password, user.password):
        raise HttpError(401, "用户名或密码错误")
    token = create_access_token(user)
    return {
        "token": token,
        "username": user.username,
        "role": user.role,
        "can_write": user.can_write,
    }


@api.get("/range", response=RangeOut, auth=bearer_auth)
def get_range(request: HttpRequest):
    """复核员也能看区间，但 can_set_limits=False。"""
    return _range_out(request.auth, RangeSetting.load())


@api.put("/range", response=RangeOut, auth=bearer_auth)
def set_range(request: HttpRequest, body: RangeIn):
    """只有操作员能在量程台改上下限。"""
    user: User = request.auth
    if not user.can_write:
        raise HttpError(403, "复核员只能查看区间与履历，不能修改上下限")
    if body.lower_limit > body.upper_limit:
        raise HttpError(400, "区间下限不能大于上限")
    range_setting = RangeSetting.load()
    range_setting.lower_limit = body.lower_limit
    range_setting.upper_limit = body.upper_limit
    range_setting.updated_by = user
    range_setting.save()
    return _range_out(user, range_setting)


@api.get("/submissions", response=list[SubmissionOut], auth=bearer_auth)
def list_submissions(request: HttpRequest):
    rows = OffsetSubmission.objects.all()[:200]
    return [_to_out(r) for r in rows]


@api.get("/submissions/{submission_id}", response=SubmissionOut, auth=bearer_auth)
def get_submission(request: HttpRequest, submission_id: int):
    try:
        row = OffsetSubmission.objects.get(pk=submission_id)
    except OffsetSubmission.DoesNotExist:
        raise HttpError(404, "刀补记录不存在")
    return _to_out(row)


@api.post("/submissions", response=SubmissionOut, auth=bearer_auth)
def create_submission_endpoint(request: HttpRequest, body: SubmissionIn):
    """交单入口（表单与直打服务共用）：越界一律退回同一套规则文案。"""
    user: User = request.auth
    if not user.can_write:
        raise HttpError(403, "当前账号只读，不能提交刀补")
    tool_code = body.tool_code.strip()
    if not tool_code:
        raise HttpError(400, "刀具编号不能为空")
    try:
        row = create_submission(
            user=user,
            tool_code=tool_code,
            offset_um=body.offset_um,
        )
    except OffsetOutOfRangeError as exc:
        raise HttpError(400, str(exc))
    return _to_out(row)


@api.patch("/submissions/{submission_id}", response=SubmissionOut, auth=bearer_auth)
def correct_submission_endpoint(
    request: HttpRequest, submission_id: int, body: CorrectIn
):
    """改正单据数字：同样走闭区间校验；越界退回，通过则追加履历、旧履历不动。"""
    user: User = request.auth
    if not user.can_write:
        raise HttpError(403, "当前账号只读，不能改正刀补")
    try:
        submission = OffsetSubmission.objects.get(pk=submission_id)
    except OffsetSubmission.DoesNotExist:
        raise HttpError(404, "刀补记录不存在")
    try:
        submission = correct_submission(
            user=user,
            submission=submission,
            offset_um=body.offset_um,
        )
    except OffsetOutOfRangeError as exc:
        raise HttpError(400, str(exc))
    return _to_out(submission)


@api.get("/history", response=list[HistoryOut], auth=bearer_auth)
def list_history(request: HttpRequest):
    """履历区：复核员可看。offset_text 是交单/改正当时的刀补原文，永不变更；
    current_offset_um 是单据现值，matches_current 供对照验收。"""
    rows = (
        OffsetHistory.objects.select_related("submission", "operator")
        .all()[:300]
    )
    return [
        HistoryOut(
            id=h.id,
            submission_id=h.submission_id,
            seq=h.seq,
            action=h.action,
            action_label=h.get_action_display(),
            tool_code=h.tool_code,
            offset_text=h.offset_text,
            current_offset_um=h.submission.offset_um,
            matches_current=str(h.submission.offset_um) == h.offset_text,
            operator=h.operator.username if h.operator else None,
            created_at=h.created_at,
        )
        for h in rows
    ]
