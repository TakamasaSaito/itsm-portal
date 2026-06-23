from fastapi import APIRouter, Depends
import aiosqlite
from datetime import date, timedelta
from ..database import get_db
from .auth import get_current_user

router = APIRouter(prefix="/api/dashboard")


@router.get("/summary")
async def get_summary(
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    today = date.today().isoformat()
    in_12m = (date.today() + timedelta(days=365)).isoformat()

    async with db.execute(
        "SELECT status, COUNT(*) as cnt FROM application GROUP BY status"
    ) as cur:
        status_counts = {row["status"]: row["cnt"] for row in await cur.fetchall()}

    async with db.execute(
        """SELECT COALESCE(app_category, '未設定') as category, COUNT(*) as cnt
           FROM application GROUP BY app_category ORDER BY cnt DESC"""
    ) as cur:
        category_counts = [
            {"category": row["category"], "count": row["cnt"]}
            for row in await cur.fetchall()
        ]

    async with db.execute(
        """SELECT d.department_name, COUNT(*) as cnt
           FROM application a
           JOIN department d ON a.owner_department_id = d.department_id
           GROUP BY d.department_name ORDER BY cnt DESC"""
    ) as cur:
        dept_counts = [
            {"dept": row["department_name"], "count": row["cnt"]}
            for row in await cur.fetchall()
        ]

    async with db.execute(
        """SELECT a.application_id, a.application_name, a.status, a.end_plan,
                  a.business_owner, d.department_name
           FROM application a
           LEFT JOIN department d ON a.owner_department_id = d.department_id
           WHERE a.end_plan BETWEEN ? AND ? AND a.status != 'retire'
           ORDER BY a.end_plan""",
        [today, in_12m],
    ) as cur:
        retiring_soon = [dict(row) for row in await cur.fetchall()]

    async with db.execute(
        "SELECT COUNT(*) as cnt FROM apm_request WHERE status = 'pending'"
    ) as cur:
        pending = (await cur.fetchone())["cnt"]

    async with db.execute("SELECT COUNT(*) as cnt FROM environment") as cur:
        env_count = (await cur.fetchone())["cnt"]

    async with db.execute("SELECT COUNT(*) as cnt FROM configuration_item") as cur:
        ci_count = (await cur.fetchone())["cnt"]

    return {
        "status_counts": status_counts,
        "category_counts": category_counts,
        "dept_counts": dept_counts,
        "retiring_soon": retiring_soon,
        "pending_requests": pending,
        "env_count": env_count,
        "ci_count": ci_count,
    }


@router.get("/retirement-readiness")
async def get_retirement_readiness(
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    today = date.today()
    in_3m  = (today + timedelta(days=90)).isoformat()
    in_12m = (today + timedelta(days=365)).isoformat()
    today_s = today.isoformat()

    # 廃止予定システム（end_plan設定 または status='retire'）
    async with db.execute("""
        SELECT application_id, application_name, end_plan, status, end_actual
        FROM application
        WHERE end_plan IS NOT NULL OR status = 'retire'
        ORDER BY end_plan NULLS LAST, application_id
    """) as cur:
        retiring = [dict(r) for r in await cur.fetchall()]

    result = []
    for sys in retiring:
        async with db.execute("""
            SELECT ad.dependency_id, ad.app_id, a.application_name,
                   ad.dependency_type, ad.note,
                   COALESCE(ad.migration_status, 'not_planned') AS migration_status,
                   ad.migration_due_date, ad.migration_note,
                   a.status AS system_status, a.end_plan AS system_end_plan,
                   a.end_actual AS system_end_actual
            FROM application_dependency ad
            JOIN application a ON a.application_id = ad.app_id
            WHERE ad.depends_on_app_id = ?
            ORDER BY a.application_name
        """, [sys["application_id"]]) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

        if not rows:
            continue

        enriched = []
        for dep in rows:
            cond_a = (dep["system_status"] == "retire"
                      or dep["system_end_plan"] is not None)
            cond_b = dep["migration_status"] in ("planned", "in_progress", "completed")
            is_ready = cond_a or cond_b

            if is_ready:
                if cond_b:
                    ms = dep["migration_status"]
                    due = dep["migration_due_date"]
                    if ms == "completed":
                        ready_reason = "移行完了済み"
                    elif due:
                        ready_reason = f"移行計画あり（{due}予定）"
                    else:
                        ready_reason = f"移行計画あり（{ms}）"
                else:
                    ready_reason = "廃止計画あり（システム自体が廃止予定）"
                not_ready_reason = None
            else:
                ready_reason = None
                not_ready_reason = "システムの廃止計画も、依存関係の移行計画も登録されていません"

            enriched.append({
                "application_id":   dep["app_id"],
                "application_name": dep["application_name"],
                "dependency_type":  dep["dependency_type"],
                "is_ready":         is_ready,
                "ready_reason":     ready_reason,
                "not_ready_reason": not_ready_reason,
                "system_status":    dep["system_status"],
                "system_end_plan":  dep["system_end_plan"],
                "migration_status": dep["migration_status"],
                "migration_due_date": dep["migration_due_date"],
                "migration_note":   dep["migration_note"],
            })

        ready_count     = sum(1 for d in enriched if d["is_ready"])
        not_ready_count = sum(1 for d in enriched if not d["is_ready"])

        ep = sys["end_plan"]
        if ep is None:
            urgency = "overdue" if sys["status"] == "retire" else "next_year"
        elif ep <= in_3m:
            urgency = "today_period"
        elif ep <= in_12m:
            urgency = "this_year"
        else:
            urgency = "next_year"

        result.append({
            "application_id":   sys["application_id"],
            "application_name": sys["application_name"],
            "end_plan":         ep,
            "status":           sys["status"],
            "urgency":          urgency,
            "total_dependents": len(enriched),
            "ready_count":      ready_count,
            "not_ready_count":  not_ready_count,
            "dependents":       enriched,
        })

    total_not_ready = sum(r["not_ready_count"] for r in result)
    return {"retiring_infra": result, "total_not_ready": total_not_ready}


@router.get("/bubble")
async def get_bubble(
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        """SELECT a.application_id, a.application_name, a.status,
                  a.portfolio_area, a.annual_cost_million, a.is_infrastructure,
                  a.migration_target_id, a.app_category, a.vendor,
                  d.department_name
           FROM application a
           LEFT JOIN department d ON a.owner_department_id = d.department_id
           WHERE a.portfolio_area IS NOT NULL
           ORDER BY a.portfolio_area, a.annual_cost_million DESC"""
    ) as cur:
        apps = [dict(row) for row in await cur.fetchall()]

    async with db.execute(
        """SELECT dependency_id, app_id, depends_on_app_id, dependency_type, note
           FROM application_dependency"""
    ) as cur:
        deps = [dict(row) for row in await cur.fetchall()]

    return {"apps": apps, "dependencies": deps}
