from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
import aiosqlite
from database import get_db
from auth import get_current_user

router = APIRouter(prefix="/api/itsm", tags=["dashboard"])


@router.get("/dashboard")
async def get_dashboard(
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # ── KPI ──────────────────────────────────────────────────
    async with db.execute(
        "SELECT COUNT(*) FROM incident WHERE state IN ('new','assigned','in_progress')"
    ) as cur:
        open_count = (await cur.fetchone())[0]

    async with db.execute(
        "SELECT COUNT(*) FROM incident"
        " WHERE priority='1-critical' AND state NOT IN ('resolved','closed')"
    ) as cur:
        critical_count = (await cur.fetchone())[0]

    async with db.execute(
        "SELECT COUNT(*) FROM incident WHERE state = 'on_hold'"
    ) as cur:
        on_hold_count = (await cur.fetchone())[0]

    async with db.execute(
        "SELECT COUNT(*) FROM incident WHERE DATE(opened_at) = DATE('now')"
    ) as cur:
        today_count = (await cur.fetchone())[0]

    # ── State distribution ────────────────────────────────────
    async with db.execute(
        "SELECT state, COUNT(*) AS cnt FROM incident GROUP BY state ORDER BY state"
    ) as cur:
        rows = await cur.fetchall()
    by_state = [{"state": r[0], "count": r[1]} for r in rows]

    # ── Priority distribution ─────────────────────────────────
    async with db.execute(
        "SELECT priority, COUNT(*) AS cnt FROM incident GROUP BY priority ORDER BY priority"
    ) as cur:
        rows = await cur.fetchall()
    by_priority = [{"priority": r[0], "count": r[1]} for r in rows]

    # ── Weekly trend (last 7 days) ───────────────────────────
    today = datetime.now(timezone.utc).date()
    date_range = [
        (today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)
    ]
    async with db.execute(
        """SELECT DATE(opened_at) AS d, COUNT(*) AS cnt
           FROM incident
           WHERE DATE(opened_at) >= ?
           GROUP BY DATE(opened_at)""",
        [date_range[0]],
    ) as cur:
        rows = await cur.fetchall()
    trend_map = {r[0]: r[1] for r in rows}
    weekly_trend = [{"date": d, "count": trend_map.get(d, 0)} for d in date_range]

    # ── By service catalog ────────────────────────────────────
    async with db.execute(
        """SELECT sc.catalog_id, sc.name, sc.icon, COUNT(i.incident_id) AS cnt
           FROM service_catalog sc
           LEFT JOIN incident i ON i.service_catalog_id = sc.catalog_id
           GROUP BY sc.catalog_id
           ORDER BY cnt DESC"""
    ) as cur:
        rows = await cur.fetchall()
    by_catalog = [{"catalog_id": r[0], "catalog_name": r[1], "icon": r[2], "count": r[3]} for r in rows]

    # ── Recent open incidents (top 5) ────────────────────────
    async with db.execute(
        """SELECT i.incident_id, i.short_description, i.state, i.priority, i.opened_at,
                  u.full_name AS caller_name, sc.name AS catalog_name
           FROM incident i
           LEFT JOIN user u ON i.caller_user_id = u.user_id
           LEFT JOIN service_catalog sc ON i.service_catalog_id = sc.catalog_id
           WHERE i.state NOT IN ('resolved','closed')
           ORDER BY i.priority ASC, i.opened_at DESC
           LIMIT 5"""
    ) as cur:
        rows = await cur.fetchall()
    recent_open = [dict(r) for r in rows]

    return {
        "kpi": {
            "open_count":    open_count,
            "critical_count": critical_count,
            "on_hold_count": on_hold_count,
            "today_count":   today_count,
        },
        "by_state":     by_state,
        "by_priority":  by_priority,
        "weekly_trend": weekly_trend,
        "by_catalog":   by_catalog,
        "recent_open":  recent_open,
    }


@router.get("/groups")
async def list_groups(
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT group_id, name, catalog_id, description FROM assignment_group ORDER BY group_id"
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/groups/{group_id}/members")
async def get_group_members(
    group_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    async with db.execute(
        """SELECT u.user_id, u.username, u.full_name, u.email, gm.role
           FROM group_member gm
           JOIN user u ON gm.user_id = u.user_id
           WHERE gm.group_id = ?
           ORDER BY gm.role DESC, u.full_name""",
        [group_id],
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/users")
async def list_users(
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    async with db.execute(
        """SELECT u.user_id, u.username, u.full_name, u.email, u.role, d.name AS dept_name
           FROM user u
           LEFT JOIN department d ON u.department_id = d.department_id
           ORDER BY u.user_id""",
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.get("/departments")
async def list_departments(
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT department_id, name, code FROM department ORDER BY department_id"
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]
