from datetime import timedelta

from django.db.models import Max
from django.utils import timezone

from inspection.models import Inspection, OverdueEvent, OverdueSetting

DEFAULT_THRESHOLD_DAYS = 30


def get_threshold_days() -> int:
    row = OverdueSetting.objects.order_by("id").first()
    if row is None:
        return DEFAULT_THRESHOLD_DAYS
    return row.threshold_days


def set_threshold_days(days: int) -> None:
    row = OverdueSetting.objects.order_by("id").first()
    if row is None:
        OverdueSetting.objects.create(threshold_days=days)
    else:
        row.threshold_days = days
        row.save(update_fields=["threshold_days"])


def current_overdue(now=None):
    """逾期现表：按灯号归并，只留最近一次仍不合格且超出天数门槛的实测。"""
    now = now or timezone.now()
    cutoff = now - timedelta(days=get_threshold_days())
    latest_ids = (
        Inspection.objects.values("aid_code")
        .annotate(latest_id=Max("id"))
        .values_list("latest_id", flat=True)
    )
    return list(
        Inspection.objects.filter(id__in=latest_ids, created_at__lte=cutoff)
        .exclude(verdict="合格")
        .order_by("aid_code")
    )


def sync_overdue(now=None):
    """按当前门槛重算：首次进入现表的灯落一条大事记；已补上合格实测的大事记标已解除。"""
    now = now or timezone.now()
    rows = current_overdue(now)
    days = get_threshold_days()
    for row in rows:
        if not OverdueEvent.objects.filter(inspection_id=row.id).exists():
            OverdueEvent.objects.create(
                aid_code=row.aid_code,
                threshold_days=days,
                inspection_id=row.id,
            )
    for event in OverdueEvent.objects.filter(resolved_at__isnull=True):
        passed = Inspection.objects.filter(
            aid_code=event.aid_code,
            verdict="合格",
            id__gt=event.inspection_id,
        ).exists()
        if passed:
            event.resolved_at = now
            event.save(update_fields=["resolved_at"])
    return rows
