"""逾期现表与大事记的归并逻辑。

现表不单独落库：每次按"灯号最新一条实测"实时归并——最新实测仍不合格、
且距登记已超过天数门槛的灯才出现。大事记在灯首次进入现表时写入一条，
之后补合格实测只会把现表里的灯去掉、并把该大事记标记为已解除，记录保留。
"""

from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from inspection.models import Inspection, OverdueEvent, OverdueSetting

FAIL = "不合格"


def _overdue_rows(days: int):
    """每个灯号取最近一次实测，只留仍不合格且超出天数门槛的。"""
    latest_ids = (
        Inspection.objects.values("aid_code")
        .annotate(latest_id=Max("id"))
        .values_list("latest_id", flat=True)
    )
    rows = Inspection.objects.filter(id__in=list(latest_ids), verdict=FAIL)
    if days <= 0:
        return list(rows)
    cutoff = timezone.now() - timedelta(days=days)
    return [row for row in rows if row.created_at < cutoff]


def _active_event(aid_code: str):
    return (
        OverdueEvent.objects.filter(aid_code=aid_code, cleared_at__isnull=True)
        .order_by("-id")
        .first()
    )


def reconcile_overdue() -> list[Inspection]:
    """按当前天数门槛归并现表，同步大事记，返回现表行（每灯一条）。"""
    days = OverdueSetting.get_days()
    with transaction.atomic():
        current = {row.aid_code: row for row in _overdue_rows(days)}

        # 新进入现表的灯：落一条大事记，记下门槛与所依不合格实测。
        for code, row in current.items():
            if _active_event(code) is None:
                OverdueEvent.objects.create(
                    aid_code=code,
                    threshold_days=days,
                    source_inspection=row,
                )

        # 已不在现表（补了合格实测，或门槛变化后不再逾期）的灯：解除大事记。
        for event in OverdueEvent.objects.filter(cleared_at__isnull=True):
            if event.aid_code not in current:
                event.cleared_at = timezone.now()
                event.save(update_fields=["cleared_at"])

    return list(current.values())
