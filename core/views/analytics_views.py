'''
from django.shortcuts import render, redirect
from core.permissions import PermissionChecker
from django.contrib import messages
def analytics_view(request):
    if not PermissionChecker.can_view(request.user, 'AUDIT_LOG', 'access'):
        messages.error(request, 'У вас нет доступа к журналу аудита')
        return redirect('workspace_home')
    return render(request, 'core/analytics.html', {})

'''
"""
analytics_views.py — Страница аналитики + все API-эндпоинты
v3.25.0

Расположение: core/views/analytics_views.py
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import connection

from core.permissions import PermissionChecker


# ──────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────
def _fetchall(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        cols = [col[0] for col in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetchval(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params or [])
        row = cur.fetchone()
        return row[0] if row else None


# ──────────────────────────────────────────────
# Главная страница аналитики
# GET /workspace/analytics/
# ──────────────────────────────────────────────
@login_required
def analytics_view(request):
    if not PermissionChecker.can_view(request.user, 'ANALYTICS', 'access'):
        return redirect('workspace_home')
    context = {
        'can_edit': PermissionChecker.can_edit(request.user, 'ANALYTICS', 'access'),
    }
    return render(request, 'core/analytics.html', context)


# ──────────────────────────────────────────────
# API: список лабораторий
# GET /workspace/analytics/api/laboratories
# ──────────────────────────────────────────────
@login_required
def api_laboratories(request):
    if not PermissionChecker.can_view(request.user, 'ANALYTICS', 'access'):
        return JsonResponse([], safe=False, status=403)
    rows = _fetchall("""
        SELECT id, name, code
        FROM laboratories
        WHERE is_active = TRUE
        ORDER BY name
    """)
    data = [{"id": 0, "name": "Все лаборатории", "code": "ALL"}] + rows
    return JsonResponse(data, safe=False)


# ──────────────────────────────────────────────
# API: KPI-карточки
# GET /workspace/analytics/api/kpi?lab_id=0
# ──────────────────────────────────────────────
@login_required
def api_kpi(request):
    if not PermissionChecker.can_view(request.user, 'ANALYTICS', 'access'):
        return JsonResponse({}, status=403)

    lab_id = int(request.GET.get('lab_id', 0))
    f = "AND laboratory_id = %s" if lab_id else ""
    p = [lab_id] if lab_id else []

    total     = _fetchval(f"SELECT COUNT(*) FROM samples WHERE status != 'CANCELLED' {f}", p)
    active    = _fetchval(f"SELECT COUNT(*) FROM samples WHERE status NOT IN ('COMPLETED','CANCELLED') {f}", p)
    overdue   = _fetchval(f"SELECT COUNT(*) FROM samples WHERE deadline < CURRENT_DATE AND status NOT IN ('COMPLETED','CANCELLED') {f}", p)
    cancelled = _fetchval(f"SELECT COUNT(*) FROM samples WHERE status = 'CANCELLED' {f}", p)

    avg_time = _fetchval(f"""
        SELECT COALESCE(ROUND(AVG(
            EXTRACT(DAY FROM (
                COALESCE(testing_end_datetime, CURRENT_TIMESTAMP) -
                COALESCE(testing_start_datetime, registration_date::timestamp)
            ))
        )::numeric, 1), 0)
        FROM samples
        WHERE (testing_start_datetime IS NOT NULL OR testing_end_datetime IS NOT NULL) {f}
    """, p)

    if not avg_time:
        avg_time = _fetchval(f"""
            SELECT COALESCE(ROUND(AVG(deadline - registration_date)::numeric, 1), 0)
            FROM samples
            WHERE deadline IS NOT NULL AND registration_date IS NOT NULL {f}
        """, p)

    if lab_id:
        employees  = _fetchval("SELECT COUNT(*) FROM users WHERE is_active = TRUE AND laboratory_id = %s", [lab_id])
        equipment  = _fetchval("SELECT COUNT(*) FROM equipment WHERE status = 'OPERATIONAL' AND laboratory_id = %s", [lab_id])
        this_month = _fetchval("SELECT COUNT(*) FROM samples WHERE laboratory_id = %s AND registration_date >= DATE_TRUNC('month', CURRENT_DATE)", [lab_id])
        completed  = _fetchval("SELECT COUNT(*) FROM samples WHERE laboratory_id = %s AND status = 'COMPLETED' AND updated_at >= DATE_TRUNC('month', CURRENT_DATE)", [lab_id])
    else:
        employees  = _fetchval("SELECT COUNT(*) FROM users WHERE is_active = TRUE")
        equipment  = _fetchval("SELECT COUNT(*) FROM equipment WHERE status = 'OPERATIONAL'")
        this_month = _fetchval("SELECT COUNT(*) FROM samples WHERE registration_date >= DATE_TRUNC('month', CURRENT_DATE)")
        completed  = _fetchval("SELECT COUNT(*) FROM samples WHERE status = 'COMPLETED' AND updated_at >= DATE_TRUNC('month', CURRENT_DATE)")

    return JsonResponse({
        "total_samples":        int(total or 0),
        "active_samples":       int(active or 0),
        "overdue_samples":      int(overdue or 0),
        "cancelled_samples":    int(cancelled or 0),
        "avg_test_days":        float(avg_time or 0),
        "total_employees":      int(employees or 0),
        "active_equipment":     int(equipment or 0),
        "samples_this_month":   int(this_month or 0),
        "completed_this_month": int(completed or 0),
    })


# ──────────────────────────────────────────────
# API: трудоёмкость по месяцам
# GET /workspace/analytics/api/monthly-labor?lab_id=0
# ──────────────────────────────────────────────
@login_required
def api_monthly_labor(request):
    if not PermissionChecker.can_view(request.user, 'ANALYTICS', 'access'):
        return JsonResponse([], safe=False, status=403)

    lab_id = int(request.GET.get('lab_id', 0))
    if lab_id:
        rows = _fetchall("""
            SELECT TO_CHAR(registration_date, 'YYYY-MM') as month,
                   COUNT(*) as samples_count
            FROM samples WHERE laboratory_id = %s
            GROUP BY TO_CHAR(registration_date, 'YYYY-MM')
            ORDER BY month
        """, [lab_id])
    else:
        rows = _fetchall("""
            SELECT TO_CHAR(registration_date, 'YYYY-MM') as month,
                   COUNT(*) as samples_count
            FROM samples
            GROUP BY TO_CHAR(registration_date, 'YYYY-MM')
            ORDER BY month
        """)
    return JsonResponse(rows, safe=False)


# ──────────────────────────────────────────────
# API: распределение по лабораториям
# GET /workspace/analytics/api/laboratory-distribution
# ──────────────────────────────────────────────
@login_required
def api_laboratory_distribution(request):
    if not PermissionChecker.can_view(request.user, 'ANALYTICS', 'access'):
        return JsonResponse([], safe=False, status=403)

    rows = _fetchall("""
        SELECT COALESCE(l.name, 'Без лаборатории') as laboratory,
               COUNT(s.id) as samples_count
        FROM samples s
        LEFT JOIN laboratories l ON s.laboratory_id = l.id
        GROUP BY l.id, l.name
        ORDER BY samples_count DESC
    """)
    return JsonResponse(rows, safe=False)


# ──────────────────────────────────────────────
# API: распределение по статусам
# GET /workspace/analytics/api/status-distribution?lab_id=0
# ──────────────────────────────────────────────
@login_required
def api_status_distribution(request):
    if not PermissionChecker.can_view(request.user, 'ANALYTICS', 'access'):
        return JsonResponse([], safe=False, status=403)

    lab_id = int(request.GET.get('lab_id', 0))
    if lab_id:
        rows = _fetchall("""
            SELECT status, COUNT(*) as count FROM samples
            WHERE laboratory_id = %s AND status IS NOT NULL
            GROUP BY status ORDER BY count DESC
        """, [lab_id])
    else:
        rows = _fetchall("""
            SELECT status, COUNT(*) as count FROM samples
            WHERE status IS NOT NULL
            GROUP BY status ORDER BY count DESC
        """)
    return JsonResponse(rows, safe=False)


# ──────────────────────────────────────────────
# API: динамика регистраций по дням
# GET /workspace/analytics/api/daily-registrations?lab_id=0
# ──────────────────────────────────────────────
@login_required
def api_daily_registrations(request):
    if not PermissionChecker.can_view(request.user, 'ANALYTICS', 'access'):
        return JsonResponse([], safe=False, status=403)

    lab_id = int(request.GET.get('lab_id', 0))
    if lab_id:
        rows = _fetchall("""
            SELECT TO_CHAR(registration_date, 'YYYY-MM-DD') as date,
                   COUNT(*) as registrations
            FROM samples WHERE laboratory_id = %s
            GROUP BY registration_date ORDER BY date
        """, [lab_id])
    else:
        rows = _fetchall("""
            SELECT TO_CHAR(registration_date, 'YYYY-MM-DD') as date,
                   COUNT(*) as registrations
            FROM samples
            GROUP BY registration_date ORDER BY date
        """)
    return JsonResponse(rows, safe=False)


# ──────────────────────────────────────────────
# API: статистика сотрудников
# GET /workspace/analytics/api/employee-stats?lab_id=0
# ──────────────────────────────────────────────
@login_required
def api_employee_stats(request):
    if not PermissionChecker.can_view(request.user, 'ANALYTICS', 'access'):
        return JsonResponse([], safe=False, status=403)

    lab_id = int(request.GET.get('lab_id', 0))
    lab_filter = "AND u.laboratory_id = %s" if lab_id else ""
    p = [lab_id] if lab_id else []

    rows = _fetchall(f"""
        SELECT
            u.id,
            u.last_name,
            u.first_name,
            u.role,
            l.name as laboratory_name,
            COUNT(DISTINCT so.sample_id) as samples_tested,
            COUNT(DISTINCT s.id)         as protocols_made
        FROM users u
        LEFT JOIN laboratories l ON u.laboratory_id = l.id
        LEFT JOIN sample_operators so ON u.id = so.user_id
            AND so.sample_id IN (
                SELECT id FROM samples WHERE testing_end_datetime IS NOT NULL
            )
        LEFT JOIN samples s ON u.id = s.report_prepared_by_id
            AND s.testing_end_datetime IS NOT NULL
        WHERE u.is_active = TRUE {lab_filter}
        GROUP BY u.id, u.last_name, u.first_name, u.role, l.name
        ORDER BY samples_tested DESC, protocols_made DESC
    """, p)

    return JsonResponse(rows, safe=False)