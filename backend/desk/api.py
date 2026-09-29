from datetime import datetime
from typing import Optional

from django.http import HttpRequest
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from desk.auth_utils import bearer_auth, create_access_token, verify_password
from desk.models import OffsetHistory, OffsetSubmission, RangeSetting, User
from desk.services import (
    OffsetOutOfRange,
    correct_submission,
    create_submission,
    get_range,
    range_rule_text,
    update_range,
)

api = NinjaAPI(title="数控刀补复核台", version="1.1")


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
    offset_raw: str


class SubmissionOut(Schema):
    id: int
    tool_code: str
    offset_um: int
    offset_raw: str
    status: str
    verdict: str
    created_at: datetime
    reviewed_at: Optional[datetime]


class CorrectIn(Schema):
    offset_raw: str


class RangeOut(Schema):
    lower_limit: int
    upper_limit: int
    rule_text: str
    updated_by: Optional[str]
    updated_at: Optional[datetime]


class RangeIn(Schema):
    lower_limit: int
    upper_limit: int


class HistoryOut(Schema):
    id: int
    submission_id: int
    tool_code: str
    offset_raw: str
    offset_um: int
    current_offset_raw: str
    current_offset_um: int
    amended: bool
    submitted_by: Optional[str]
    created_at: datetime


def _to_out(row: OffsetSubmission) -> SubmissionOut:
    return SubmissionOut(
        id=row.id,
        tool_code=row.tool_code,
        offset_um=row.offset_um,
        offset_raw=row.offset_raw,
        status=row.status,
        verdict=row.verdict or "",
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
    )


def _range_out(setting: RangeSetting) -> RangeOut:
    return RangeOut(
        lower_limit=setting.lower_limit,
        upper_limit=setting.upper_limit,
        rule_text=range_rule_text(setting.lower_limit, setting.upper_limit),
        updated_by=setting.updated_by.username if setting.updated_by else None,
        updated_at=setting.updated_at,
    )


def _reject_business_error(exc: Exception) -> HttpError:
    """表单入口与直打服务共用 services 的同一套规则文案。"""
    return HttpError(400, str(exc))


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
def retrieve_range(request: HttpRequest):
    # 复核员也能看区间，只是不能改
    return _range_out(get_range())


@api.put("/range", response=RangeOut, auth=bearer_auth)
def change_range(request: HttpRequest, body: RangeIn):
    user: User = request.auth
    if not user.can_write:
        raise HttpError(403, "复核员只能查看量程区间，不能修改上下限")
    try:
        setting = update_range(user, body.lower_limit, body.upper_limit)
    except ValueError as exc:
        raise _reject_business_error(exc)
    return _range_out(setting)


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
def create_submission_view(request: HttpRequest, body: SubmissionIn):
    user: User = request.auth
    if not user.can_write:
        raise HttpError(403, "当前账号只读，不能提交刀补")
    try:
        row = create_submission(user, body.tool_code, body.offset_raw)
    except (OffsetOutOfRange, ValueError) as exc:
        raise _reject_business_error(exc)
    return _to_out(row)


@api.patch("/submissions/{submission_id}", response=SubmissionOut, auth=bearer_auth)
def correct_submission_view(request: HttpRequest, submission_id: int, body: CorrectIn):
    user: User = request.auth
    if not user.can_write:
        raise HttpError(403, "当前账号只读，不能改正刀补")
    try:
        row = OffsetSubmission.objects.get(pk=submission_id)
    except OffsetSubmission.DoesNotExist:
        raise HttpError(404, "刀补记录不存在")
    try:
        row = correct_submission(row, body.offset_raw)
    except (OffsetOutOfRange, ValueError) as exc:
        raise _reject_business_error(exc)
    return _to_out(row)


@api.get("/history", response=list[HistoryOut], auth=bearer_auth)
def list_history(request: HttpRequest):
    """履历原文与单据当前值并排，供事后对照验收。"""
    rows = OffsetHistory.objects.select_related("submission", "submitted_by")[:200]
    result = []
    for h in rows:
        doc = h.submission
        result.append(
            HistoryOut(
                id=h.id,
                submission_id=h.submission_id,
                tool_code=h.tool_code,
                offset_raw=h.offset_raw,
                offset_um=h.offset_um,
                current_offset_raw=doc.offset_raw,
                current_offset_um=doc.offset_um,
                amended=(h.offset_um != doc.offset_um or h.offset_raw != doc.offset_raw),
                submitted_by=h.submitted_by.username if h.submitted_by else None,
                created_at=h.created_at,
            )
        )
    return result
