from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from inspection.models import Inspection, OverdueEvent, OverdueSetting
from inspection.overdue import get_threshold_days
from inspection.rules import judge


def _seed_accounts():
    group = Group.objects.create(name="inspector")
    keeper = User.objects.create_user(username="keeper", password="light123456")
    keeper.groups.add(group)
    User.objects.create_user(username="watch", password="watch123456")


def _add_inspection(code, measured, required=1200, bearing=0.2, by="keeper"):
    verdict, note = judge(measured, required, bearing)
    return Inspection.objects.create(
        aid_code=code,
        measured_cd=measured,
        required_cd=required,
        bearing_error_deg=bearing,
        verdict=verdict,
        note=note,
        created_by=by,
    )


class OverdueFlowTests(TestCase):
    def setUp(self):
        _seed_accounts()
        self.dim = _add_inspection("LH-09", 800)  # 偏暗：光强不足
        _add_inspection("LH-01", 1400, bearing=0.4)
        self.keeper = Client()
        self.keeper.login(username="keeper", password="light123456")
        self.watch = Client()
        self.watch.login(username="watch", password="watch123456")

    def _current_table_body(self, response):
        body = response.content.decode()
        return body.split("逾期现表")[1].split("逾期大事记")[0]

    def test_threshold_zero_then_passing_measurement(self):
        # 默认门槛下种子不逾期
        self.assertEqual(get_threshold_days(), 30)
        resp = self.keeper.get(reverse("overdue"))
        self.assertNotContains(resp, "LH-09")
        self.assertEqual(OverdueEvent.objects.count(), 0)

        # 天数改成 0：偏暗种子进入现表，大事记多一条
        resp = self.keeper.post(reverse("overdue"), {"threshold_days": "0"})
        self.assertRedirects(resp, reverse("overdue"))
        self.assertEqual(OverdueSetting.objects.get().threshold_days, 0)
        resp = self.keeper.get(reverse("overdue"))
        self.assertIn("LH-09", self._current_table_body(resp))
        self.assertNotIn("LH-01", self._current_table_body(resp))
        event = OverdueEvent.objects.get()
        self.assertEqual(event.aid_code, "LH-09")
        self.assertEqual(event.threshold_days, 0)
        self.assertEqual(event.inspection_id, self.dim.pk)
        self.assertIsNotNone(event.entered_at)
        self.assertIsNone(event.resolved_at)

        # 重复访问不重复落大事记
        self.keeper.get(reverse("overdue"))
        self.assertEqual(OverdueEvent.objects.count(), 1)

        # 补合格实测：现表去掉该灯，大事记保留并标已解除
        _add_inspection("LH-09", 1300, bearing=0.1)
        resp = self.keeper.get(reverse("overdue"))
        self.assertNotIn("LH-09", self._current_table_body(resp))
        event.refresh_from_db()
        self.assertIsNotNone(event.resolved_at)
        self.assertContains(resp, "已解除")

    def test_reoverdue_writes_new_event(self):
        self.keeper.post(reverse("overdue"), {"threshold_days": "0"})
        self.keeper.get(reverse("overdue"))
        _add_inspection("LH-09", 1300, bearing=0.1)
        self.keeper.get(reverse("overdue"))
        _add_inspection("LH-09", 900)
        resp = self.keeper.get(reverse("overdue"))
        self.assertIn("LH-09", self._current_table_body(resp))
        self.assertEqual(OverdueEvent.objects.count(), 2)
        self.assertEqual(OverdueEvent.objects.filter(resolved_at__isnull=True).count(), 1)

    def test_threshold_change_takes_effect_immediately(self):
        self.keeper.post(reverse("overdue"), {"threshold_days": "0"})
        resp = self.keeper.get(reverse("overdue"))
        self.assertIn("LH-09", self._current_table_body(resp))
        self.keeper.post(reverse("overdue"), {"threshold_days": "30"})
        resp = self.keeper.get(reverse("overdue"))
        self.assertNotIn("LH-09", self._current_table_body(resp))
        # 改天数不解除大事记，只有合格实测能解除
        self.assertEqual(OverdueEvent.objects.filter(resolved_at__isnull=True).count(), 1)

    def test_readonly_account(self):
        self.keeper.post(reverse("overdue"), {"threshold_days": "0"})
        self.keeper.get(reverse("overdue"))
        resp = self.watch.get(reverse("overdue"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("LH-09", self._current_table_body(resp))
        self.assertNotContains(resp, 'name="threshold_days"')
        resp = self.watch.post(reverse("overdue"), {"threshold_days": "99"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(get_threshold_days(), 0)

    def test_invalid_threshold_rejected(self):
        for bad in ("-1", "abc", ""):
            resp = self.keeper.post(reverse("overdue"), {"threshold_days": bad})
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, "请填")
            self.assertEqual(get_threshold_days(), 30)

    def test_anonymous_redirected_to_login(self):
        resp = Client().get(reverse("overdue"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])
