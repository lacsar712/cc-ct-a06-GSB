from django.core.exceptions import ValidationError
from django.test import TestCase

from desk.auth_utils import create_access_token
from desk.models import (
    DEFAULT_RANGE_LOWER,
    DEFAULT_RANGE_UPPER,
    OffsetHistory,
    OffsetSubmission,
    RangeSetting,
    User,
)
from desk.services import (
    OffsetOutOfRange,
    correct_submission,
    create_submission,
    get_range,
    range_rule_text,
    update_range,
)


class ServiceRuleTests(TestCase):
    """直打服务入口：services 直接调用。"""

    @classmethod
    def setUpTestData(cls):
        cls.machinist = User.objects.create_user(
            username="m", password="x", role=User.Role.MACHINIST
        )
        cls.auditor = User.objects.create_user(
            username="a", password="x", role=User.Role.AUDITOR
        )

    def test_default_range_is_minus_twenty_to_twenty(self):
        # 迁移初始化的单行区间
        setting = RangeSetting.objects.get(pk=1)
        self.assertEqual(setting.lower_limit, -20)
        self.assertEqual(setting.upper_limit, 20)
        self.assertEqual((DEFAULT_RANGE_LOWER, DEFAULT_RANGE_UPPER), (-20, 20))

    def test_submit_five_is_accepted_and_history_snapshotted(self):
        row = create_submission(self.machinist, "T01", "5")
        self.assertEqual(row.offset_um, 5)
        self.assertEqual(row.offset_raw, "5")
        self.assertEqual(row.status, OffsetSubmission.Status.PENDING)
        hist = OffsetHistory.objects.get(submission=row)
        self.assertEqual(hist.offset_raw, "5")
        self.assertEqual(hist.offset_um, 5)
        self.assertEqual(hist.tool_code, "T01")

    def test_closed_range_boundaries_are_accepted(self):
        # 闭区间：上下限边界都应收下
        row_hi = create_submission(self.machinist, "TH", "20")
        row_lo = create_submission(self.machinist, "TL", "-20")
        self.assertEqual(row_hi.offset_um, 20)
        self.assertEqual(row_lo.offset_um, -20)

    def test_submit_thirty_is_rejected_by_service(self):
        with self.assertRaises(OffsetOutOfRange) as ctx:
            create_submission(self.machinist, "T09", "30")
        self.assertIn("[-20, 20]", str(ctx.exception))
        self.assertIn("30", str(ctx.exception))
        # 越界不留单据、不留履历
        self.assertFalse(OffsetSubmission.objects.filter(tool_code="T09").exists())
        self.assertEqual(OffsetHistory.objects.count(), 0)

    def test_non_integer_input_rejected(self):
        with self.assertRaises(ValueError):
            create_submission(self.machinist, "T01", "abc")

    def test_correcting_document_keeps_history_old_value(self):
        row = create_submission(self.machinist, "T01", "5")
        correct_submission(row, "8")
        row.refresh_from_db()
        self.assertEqual(row.offset_um, 8)
        self.assertEqual(row.offset_raw, "8")
        self.assertEqual(row.status, OffsetSubmission.Status.PENDING)
        self.assertEqual(row.verdict, "")
        # 履历旧值原封不动，可与单据当前值对照
        hist = OffsetHistory.objects.get(submission=row)
        self.assertEqual(hist.offset_raw, "5")
        self.assertEqual(hist.offset_um, 5)
        self.assertEqual(OffsetHistory.objects.count(), 1)

    def test_correcting_to_out_of_range_rejected(self):
        row = create_submission(self.machinist, "T01", "5")
        with self.assertRaises(OffsetOutOfRange):
            correct_submission(row, "30")
        row.refresh_from_db()
        self.assertEqual(row.offset_um, 5)  # 单据未被改

    def test_history_is_append_only(self):
        row = create_submission(self.machinist, "T01", "5")
        hist = OffsetHistory.objects.get(submission=row)
        hist.offset_um = 9
        with self.assertRaises(ValidationError):
            hist.save()
        with self.assertRaises(ValidationError):
            hist.delete()
        with self.assertRaises(ValidationError):
            OffsetHistory.objects.all().update(offset_um=9)
        with self.assertRaises(ValidationError):
            OffsetHistory.objects.all().delete()
        # 数据确实没变
        hist.refresh_from_db()
        self.assertEqual(hist.offset_um, 5)

    def test_range_update_and_order_validation(self):
        update_range(self.machinist, -10, 10)
        setting = get_range()
        self.assertEqual((setting.lower_limit, setting.upper_limit), (-10, 10))
        self.assertEqual(setting.updated_by, self.machinist)
        with self.assertRaises(ValueError):
            update_range(self.machinist, 10, -10)
        # 调整后的区间立即生效：15 退回
        with self.assertRaises(OffsetOutOfRange):
            create_submission(self.machinist, "T02", "15")

    def test_range_single_row_cannot_be_deleted_or_duplicated(self):
        update_range(self.machinist, -1, 1)
        self.assertEqual(RangeSetting.objects.count(), 1)
        with self.assertRaises(ValidationError):
            RangeSetting.objects.get(pk=1).delete()
        with self.assertRaises(ValidationError):
            RangeSetting(pk=2, lower_limit=0, upper_limit=1).save()
        self.assertEqual(RangeSetting.objects.count(), 1)
        self.assertEqual(RangeSetting.objects.get(pk=1).lower_limit, -1)


class ApiRuleTests(TestCase):
    """表单入口：HTTP API。文案与直打服务同一来源。"""

    @classmethod
    def setUpTestData(cls):
        cls.machinist = User.objects.create_user(
            username="machinist", password="x", role=User.Role.MACHINIST
        )
        cls.auditor = User.objects.create_user(
            username="auditor", password="x", role=User.Role.AUDITOR
        )

    def auth(self, user):
        return f"Bearer {create_access_token(user)}"

    def test_submit_five_accepted_over_http(self):
        resp = self.client.post(
            "/api/submissions",
            data={"tool_code": "T01", "offset_raw": "5"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth(self.machinist),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["offset_um"], 5)
        self.assertEqual(OffsetHistory.objects.count(), 1)

    def test_submit_thirty_rejected_over_http_with_same_rule_text(self):
        resp = self.client.post(
            "/api/submissions",
            data={"tool_code": "T09", "offset_raw": "30"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth(self.machinist),
        )
        self.assertEqual(resp.status_code, 400)
        message = resp.json()["detail"]
        self.assertEqual(message, range_rule_text(-20, 20, 30))
        self.assertFalse(OffsetSubmission.objects.exists())

    def test_auditor_can_read_range_and_history_but_not_change_limit(self):
        create_submission(self.machinist, "T01", "5")
        token = self.auth(self.auditor)
        resp = self.client.get("/api/range", HTTP_AUTHORIZATION=token)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["lower_limit"], -20)
        resp = self.client.get("/api/history", HTTP_AUTHORIZATION=token)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        resp = self.client.put(
            "/api/range",
            data={"lower_limit": -1, "upper_limit": 1},
            content_type="application/json",
            HTTP_AUTHORIZATION=token,
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(RangeSetting.objects.get(pk=1).lower_limit, -20)

    def test_auditor_cannot_submit_or_correct(self):
        row = create_submission(self.machinist, "T01", "5")
        token = self.auth(self.auditor)
        resp = self.client.post(
            "/api/submissions",
            data={"tool_code": "T02", "offset_raw": "1"},
            content_type="application/json",
            HTTP_AUTHORIZATION=token,
        )
        self.assertEqual(resp.status_code, 403)
        resp = self.client.patch(
            f"/api/submissions/{row.id}",
            data={"offset_raw": "9"},
            content_type="application/json",
            HTTP_AUTHORIZATION=token,
        )
        self.assertEqual(resp.status_code, 403)

    def test_correct_over_http_then_history_comparison(self):
        token = self.auth(self.machinist)
        resp = self.client.post(
            "/api/submissions",
            data={"tool_code": "T01", "offset_raw": "5"},
            content_type="application/json",
            HTTP_AUTHORIZATION=token,
        )
        sid = resp.json()["id"]
        resp = self.client.patch(
            f"/api/submissions/{sid}",
            data={"offset_raw": "8"},
            content_type="application/json",
            HTTP_AUTHORIZATION=token,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        resp = self.client.get("/api/history", HTTP_AUTHORIZATION=token)
        item = resp.json()[0]
        self.assertEqual(item["offset_raw"], "5")
        self.assertEqual(item["offset_um"], 5)
        self.assertEqual(item["current_offset_raw"], "8")
        self.assertEqual(item["current_offset_um"], 8)
        self.assertTrue(item["amended"])

    def test_operator_updates_range_over_http(self):
        resp = self.client.put(
            "/api/range",
            data={"lower_limit": -30, "upper_limit": 30},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth(self.machinist),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual((resp.json()["lower_limit"], resp.json()["upper_limit"]), (-30, 30))
        # 新区间下 30 落在边界，应被收下
        resp = self.client.post(
            "/api/submissions",
            data={"tool_code": "T09", "offset_raw": "30"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth(self.machinist),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
