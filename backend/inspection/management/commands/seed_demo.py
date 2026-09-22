from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from inspection.models import Inspection, OverdueSetting
from inspection.overdue import reconcile_overdue
from inspection.rules import judge


class Command(BaseCommand):
    help = "seed two inspections and two accounts"

    def handle(self, *args, **options):
        group, _ = Group.objects.get_or_create(name="inspector")
        keeper, created = User.objects.get_or_create(username="keeper")
        if created or not keeper.check_password("light123456"):
            keeper.set_password("light123456")
            keeper.save()
        keeper.groups.add(group)
        watch, created = User.objects.get_or_create(username="watch")
        if created or not watch.check_password("watch123456"):
            watch.set_password("watch123456")
            watch.save()
        watch.groups.remove(group)
        # 交卷基线：天数门槛为 0，偏暗种子立即算逾期。
        OverdueSetting.objects.get_or_create(pk=1, defaults={"days": 0})
        if Inspection.objects.exists():
            self.stdout.write("already seeded")
            return
        samples = [
            ("LH-01", 1400, 1200, 0.4),
            ("LH-09", 800, 1200, 0.2),
        ]
        for code, measured, required, bearing in samples:
            verdict, note = judge(measured, required, bearing)
            Inspection.objects.create(
                aid_code=code,
                measured_cd=measured,
                required_cd=required,
                bearing_error_deg=bearing,
                verdict=verdict,
                note=note,
                created_by="keeper",
            )
        # 门槛 0 立即生效：偏暗灯进入逾期现表，大事记落下第一条。
        reconcile_overdue()
        self.stdout.write("seeded")
