from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from inspection.models import Inspection, OverdueEvent, OverdueSetting
from inspection.overdue import reconcile_overdue
from inspection.rules import judge


def _can_write(user) -> bool:
    return user.groups.filter(name="inspector").exists()


def health(_request):
    from django.http import JsonResponse

    return JsonResponse({"status": "ok", "service": "nav-aid-inspection"})


@require_http_methods(["GET", "POST"])
def login_view(request):
    from django.contrib.auth import authenticate, login

    error = ""
    if request.method == "POST":
        user = authenticate(
            request,
            username=request.POST.get("username", "").strip(),
            password=request.POST.get("password", ""),
        )
        if user is None:
            error = "用户名或密码错误"
        else:
            login(request, user)
            return redirect("list")
    return render(request, "login.html", {"error": error})


def logout_view(request):
    from django.contrib.auth import logout

    logout(request)
    return redirect("login")


@login_required
def list_view(request):
    rows = Inspection.objects.all()
    return render(request, "list.html", {"rows": rows, "can_write": _can_write(request.user)})


@login_required
def detail_view(request, pk):
    row = get_object_or_404(Inspection, pk=pk)
    return render(request, "detail.html", {"row": row})


@login_required
@require_http_methods(["GET", "POST"])
def create_view(request):
    if not _can_write(request.user):
        return HttpResponseForbidden("仅巡检员可登记灯光巡检")
    error = ""
    if request.method == "POST":
        try:
            measured = float(request.POST["measured_cd"])
            required = float(request.POST["required_cd"])
            bearing = float(request.POST["bearing_error_deg"])
            code = request.POST["aid_code"].strip()
            if not code:
                raise ValueError("empty")
        except (KeyError, ValueError):
            error = "请填编号和三项数值"
        else:
            verdict, note = judge(measured, required, bearing)
            row = Inspection.objects.create(
                aid_code=code,
                measured_cd=measured,
                required_cd=required,
                bearing_error_deg=bearing,
                verdict=verdict,
                note=note,
                created_by=request.user.username,
            )
            return redirect("detail", pk=row.pk)
    return render(request, "form.html", {"error": error})


@login_required
@require_http_methods(["GET", "POST"])
def overdue_view(request):
    error = ""
    if request.method == "POST":
        if not _can_write(request.user):
            return HttpResponseForbidden("仅持灯账号可调整逾期天数")
        try:
            days = int(request.POST.get("days", ""))
            if days < 0:
                raise ValueError("negative")
        except (TypeError, ValueError):
            error = "请填不小于 0 的整数天数"
        else:
            OverdueSetting.set_days(days)
            return redirect("overdue")

    rows = reconcile_overdue()
    events = OverdueEvent.objects.select_related("source_inspection").all()
    active_events = {
        event.aid_code: event for event in events if not event.is_cleared
    }
    current_rows = [
        {"inspection": row, "entered_at": active_events[row.aid_code].entered_at}
        for row in rows
        if row.aid_code in active_events
    ]
    return render(
        request,
        "overdue.html",
        {
            "current_rows": current_rows,
            "events": events,
            "days": OverdueSetting.get_days(),
            "error": error,
        },
    )
