from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from pydantic import BaseModel
from database import get_db, calc_priority
from auth import get_current_user
from routers.incidents import _next_incident_id

router = APIRouter(prefix="/api/itsm/portal", tags=["portal"])


class PortalIncidentCreate(BaseModel):
    service_catalog_id: int
    urgency: str                 # 2-high / 3-medium / 4-low
    short_description: str
    description: Optional[str] = None


@router.get("/catalogs")
async def list_catalogs(
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT catalog_id, name, description, icon FROM service_catalog"
        " WHERE is_active = 1 ORDER BY catalog_id"
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/incidents", status_code=201)
async def portal_create_incident(
    body: PortalIncidentCreate,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Validate catalog exists
    async with db.execute(
        "SELECT catalog_id FROM service_catalog WHERE catalog_id = ? AND is_active = 1",
        [body.service_catalog_id],
    ) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(400, "指定されたサービスカタログが存在しません")

    # Auto-route catalog → group
    async with db.execute(
        "SELECT group_id FROM assignment_group WHERE catalog_id = ?",
        [body.service_catalog_id],
    ) as cur:
        grp = await cur.fetchone()
    if grp is None:
        raise HTTPException(400, "担当グループが見つかりません")

    # Portal users submit with 4-user impact (conservative)
    impact = "4-user"
    urgency = body.urgency
    priority = calc_priority(impact, urgency)

    caller_id = current_user["user_id"]
    dept_id = current_user.get("department_id")

    incident_id = await _next_incident_id(db)
    opened_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    await db.execute(
        """INSERT INTO incident (
            incident_id, short_description, description,
            service_catalog_id, channel,
            priority, impact, urgency, state,
            caller_user_id, assigned_group_id, department_id,
            opened_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            incident_id, body.short_description, body.description,
            body.service_catalog_id, "portal",
            priority, impact, urgency, "new",
            caller_id, grp["group_id"], dept_id,
            opened_at,
        ),
    )
    await db.commit()

    async with db.execute(
        """SELECT i.*, sc.name AS catalog_name, sc.icon AS catalog_icon,
                  ag.name AS group_name
           FROM incident i
           LEFT JOIN service_catalog sc ON i.service_catalog_id = sc.catalog_id
           LEFT JOIN assignment_group ag ON i.assigned_group_id = ag.group_id
           WHERE i.incident_id = ?""",
        [incident_id],
    ) as cur:
        row = await cur.fetchone()
    return dict(row)


@router.get("/my-incidents")
async def my_incidents(
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    caller_id = current_user["user_id"]
    sql = """
        SELECT
            i.incident_id, i.short_description, i.state, i.priority,
            i.urgency, i.channel, i.opened_at, i.resolved_at,
            sc.name AS catalog_name,
            sc.icon AS catalog_icon,
            ag.name AS group_name
        FROM incident i
        LEFT JOIN service_catalog sc ON i.service_catalog_id = sc.catalog_id
        LEFT JOIN assignment_group ag ON i.assigned_group_id  = ag.group_id
        WHERE i.caller_user_id = ?
        ORDER BY i.opened_at DESC
    """
    async with db.execute(sql, [caller_id]) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]
