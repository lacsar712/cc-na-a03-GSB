from django.db import models


class Inspection(models.Model):
    aid_code = models.CharField("航标编号", max_length=40)
    measured_cd = models.FloatField("实测光强")
    required_cd = models.FloatField("要求光强")
    bearing_error_deg = models.FloatField("方位偏差")
    verdict = models.CharField("结论", max_length=20)
    note = models.CharField("说明", max_length=200)
    created_by = models.CharField("登记人", max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class OverdueSetting(models.Model):
    """逾期判定的天数门槛，单独保存；全系统只有一行，改完下次计算立即生效。"""

    days = models.PositiveIntegerField("逾期天数门槛", default=0)

    class Meta:
        verbose_name = "逾期设置"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"逾期天数门槛：{self.days}"

    @classmethod
    def get_days(cls) -> int:
        obj = cls.objects.first()
        return obj.days if obj is not None else 0

    @classmethod
    def set_days(cls, days: int) -> int:
        obj = cls.objects.order_by("pk").first()
        if obj is None:
            obj = cls.objects.create(days=days)
        else:
            obj.days = days
            obj.save(update_fields=["days"])
        return obj.days


class OverdueEvent(models.Model):
    """逾期大事记：灯号首次进入逾期现表时落库，解除后仍永久保留。"""

    aid_code = models.CharField("航标编号", max_length=40, db_index=True)
    threshold_days = models.PositiveIntegerField("当时天数门槛")
    source_inspection = models.ForeignKey(
        Inspection,
        verbose_name="所依不合格实测",
        on_delete=models.PROTECT,
        related_name="overdue_events",
    )
    entered_at = models.DateTimeField("进入时刻", auto_now_add=True)
    cleared_at = models.DateTimeField("解除时刻", null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "逾期大事记"
        verbose_name_plural = verbose_name

    def __str__(self):
        state = "已解除" if self.cleared_at else "逾期中"
        return f"{self.aid_code} {state}（门槛{self.threshold_days}天）"

    @property
    def is_cleared(self) -> bool:
        return self.cleared_at is not None
