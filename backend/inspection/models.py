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
    """单行配置：不合格实测超过多少天没有新合格实测即算逾期。"""

    threshold_days = models.IntegerField("逾期天数门槛", default=30)


class OverdueEvent(models.Model):
    """逾期大事记：灯首次进入现表时落库，补上合格实测后标已解除。"""

    aid_code = models.CharField("航标编号", max_length=40)
    threshold_days = models.IntegerField("当时天数门槛")
    inspection = models.ForeignKey(
        Inspection,
        verbose_name="所依不合格实测",
        on_delete=models.CASCADE,
        related_name="overdue_events",
    )
    entered_at = models.DateTimeField("进入时刻", auto_now_add=True)
    resolved_at = models.DateTimeField("解除时刻", null=True, blank=True)

    class Meta:
        ordering = ["-id"]
