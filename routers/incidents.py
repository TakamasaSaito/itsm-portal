from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
import aiosqlite
from pydantic import BaseModel
from database import get_db, calc_priority
from auth import get_current_user

router = APIRouter(prefix="/api/itsm/incidents", tags=["incidents"])

PER_PAGE = 10

# ── Pydantic models ──────────────────────────────────────────────────────────

class IncidentCreate(BaseModel):
    short_description: str
    service_catalog_id: int
    urgency: str
    description: Optional[str] = None
    impact: Optional[str] = "3-department"
    category: Optional[str] = None
    subcategory: Optional[str] = None
    channel: Optional[str] = "portal"
    caller_user_id: Optional[int] = None
    assigned_user_id: Optional[int] = None
    department_id: Optional[int] = None
    due_date: Optional[str] = None


class IncidentUpdate(BaseModel):
    short_description: Optional[str] = None
    description: Optional[str] = None
    service_catalog_id: Optional[int] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    channel: Optional[str] = None
    impact: Optional[str] = None
    urgency: Optional[str] = None
    state: Optional[str] = None
    assigned_group_id: Optional[int] = None
    assigned_user_id: Optional[int] = None
    caller_user_id: Optional[int] = None
    department_id: Optional[int] = None
    resolution_code: Optional[str] = None
    resolution_notes: Optional[str] = None
    due_date: Optional[str] = None


class NoteCreate(BaseModel):
    body: str
    note_type: Optional[str] = "work_note"


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _next_incident_id(db: aiosqlite.Connection) -> str:
    async with db.execute("SELECT MAX(incident_id) FROM incident") as cur:
        row = await cur.fetchone()
    if row[0] is None:
        return "INC0001001"
    num = int(row[0][3:]) + 1
    return "INC" + str(num).zfill(7)


async def _get_incident_detail(db: aiosqlite.Connection, incident_id: str) -> dict:
    sql = """
        SELECT
            i.*,
            u_caller.full_name   AS caller_name,
            u_caller.username    AS caller_username,
            u_caller.email       AS caller_email,
            d_caller.name        AS caller_dept_name,
            sc.name              AS catalog_name,
            sc.icon              AS catalog_icon,
            sc.description       AS catalog_description,
            ag.name              AS group_name,
            ag.description       AS group_description,
            u_asgn.full_name     AS assigned_name,
            u_asgn.username      AS assigned_username,
            d_inc.name           AS dept_name
        FROM incident i
        LEFT JOIN user       u_caller ON i.caller_user_id   = u_caller.user_id
        LEFT JOIN department d_caller ON u_caller.department_id = d_caller.department_id
        LEFT JOIN service_catalog sc  ON i.service_catalog_id  = sc.catalog_id
        LEFT JOIN assignment_group ag ON i.assigned_group_id   = ag.group_id
        LEFT JOIN user       u_asgn  ON i.assigned_user_id    = u_asgn.user_id
        LEFT JOIN department d_inc   ON i.department_id        = d_inc.department_id
        WHERE i.incident_id = ?
    """
    async with db.execute(sql, [incident_id]) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(404, "Incident not found")

    d = dict(row)
    return {
        "incident_id":      d["incident_id"],
        "short_description": d["short_description"],
        "description":      d["description"],
        "state":            d["state"],
        "priority":         d["priority"],
        "impact":           d["impact"],
        "urgency":          d["urgency"],
        "category":         d["category"],
        "subcategory":      d["subcategory"],
        "channel":          d["channel"],
        "opened_at":        d["opened_at"],
        "resolved_at":      d["resolved_at"],
        "closed_at":        d["closed_at"],
        "due_date":         d["due_date"],
        "resolution_code":  d["resolution_code"],
        "resolution_notes": d["resolution_notes"],
        "service_catalog_id": d["service_catalog_id"],
        "assigned_group_id":  d["assigned_group_id"],
        "assigned_user_id":   d["assigned_user_id"],
        "caller_user_id":     d["caller_user_id"],
        "department_id":      d["department_id"],
        "caller": {
            "user_id":   d["caller_user_id"],
            "full_name": d["caller_name"],
            "username":  d["caller_username"],
            "email":     d["caller_email"],
            "dept_name": d["caller_dept_name"],
        } if d["caller_user_id"] else None,
        "service_catalog": {
            "catalog_id":  d["service_catalog_id"],
            "name":        d["catalog_name"],
            "icon":        d["catalog_icon"],
            "description": d["catalog_description"],
        } if d["service_catalog_id"] else None,
        "assigned_group": {
            "group_id":    d["assigned_group_id"],
            "name":        d["group_name"],
            "description": d["group_description"],
        } if d["assigned_group_id"] else None,
        "assigned_user": {
            "user_id":   d["assigned_user_id"],
            "full_name": d["assigned_name"],
            "username":  d["assigned_username"],
        } if d["assigned_user_id"] else None,
        "department": {
            "department_id": d["department_id"],
            "name":          d["dept_name"],
        } if d["department_id"] else None,
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("")
async def list_incidents(
    page: int = Query(1, ge=1),
    state: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    service_catalog_id: Optional[int] = Query(None),
    assigned_group_id: Optional[int] = Query(None),
    assigned_user_id: Optional[int] = Query(None),
    q: Optional[str] = Query(None),
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    where = ["1=1"]
    params = []

    if state:
        where.append("i.state = ?")
        params.append(state)
    if priority:
        where.append("i.priority = ?")
        params.append(priority)
    if service_catalog_id:
        where.append("i.service_catalog_id = ?")
        params.append(service_catalog_id)
    if assigned_group_id:
        where.append("i.assigned_group_id = ?")
        params.append(assigned_group_id)
    if assigned_user_id:
        where.append("i.assigned_user_id = ?")
        params.append(assigned_user_id)
    if q:
        where.append("(i.short_description LIKE ? OR i.incident_id LIKE ?)")
        params.extend(["%" + q + "%", "%" + q + "%"])

    where_sql = " AND ".join(where)

    async with db.execute(
        "SELECT COUNT(*) FROM incident i WHERE " + where_sql, params
    ) as cur:
        total = (await cur.fetchone())[0]

    offset = (page - 1) * PER_PAGE
    list_sql = """
        SELECT
            i.incident_id, i.short_description, i.state, i.priority,
            i.category, i.impact, i.urgency, i.channel, i.opened_at, i.due_date,
            i.service_catalog_id, i.assigned_group_id, i.assigned_user_id, i.caller_user_id,
            u_caller.full_name AS caller_name,
            sc.name            AS catalog_name,
            sc.icon            AS catalog_icon,
            ag.name            AS group_name,
            u_asgn.full_name   AS assigned_name
        FROM incident i
        LEFT JOIN user          u_caller ON i.caller_user_id   = u_caller.user_id
        LEFT JOIN service_catalog sc      ON i.service_catalog_id  = sc.catalog_id
        LEFT JOIN assignment_group ag     ON i.assigned_group_id   = ag.group_id
        LEFT JOIN user          u_asgn   ON i.assigned_user_id    = u_asgn.user_id
        WHERE """ + where_sql + """
        ORDER BY i.opened_at DESC
        LIMIT ? OFFSET ?
    """
    async with db.execute(list_sql, params + [PER_PAGE, offset]) as cur:
        rows = await cur.fetchall()

    items = [dict(r) for r in rows]
    return {
        "total":    total,
        "page":     page,
        "per_page": PER_PAGE,
        "pages":    max(1, (total + PER_PAGE - 1) // PER_PAGE),
        "items":    items,
    }


@router.get("/{incident_id}")
async def get_incident(
    incident_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await _get_incident_detail(db, incident_id)


@router.post("", status_code=201)
async def create_incident(
    body: IncidentCreate,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Auto-route: catalog → group
    async with db.execute(
        "SELECT group_id FROM assignment_group WHERE catalog_id = ?",
        [body.service_catalog_id],
    ) as cur:
        grp = await cur.fetchone()
    if grp is None:
        raise HTTPException(400, "指定されたサービスカタログに対応するグループが存在しません")

    impact = body.impact or "3-department"
    priority = calc_priority(impact, body.urgency)
    incident_id = await _next_incident_id(db)
    opened_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    caller_id = body.caller_user_id or current_user["user_id"]

    # Use caller's department if not specified
    dept_id = body.department_id
    if dept_id is None and caller_id:
        async with db.execute(
            "SELECT department_id FROM user WHERE user_id = ?", [caller_id]
        ) as cur:
            u = await cur.fetchone()
        if u:
            dept_id = u["department_id"]

    await db.execute(
        """INSERT INTO incident (
            incident_id, short_description, description,
            service_catalog_id, category, subcategory, channel,
            priority, impact, urgency, state,
            caller_user_id, assigned_group_id, assigned_user_id, department_id,
            opened_at, due_date
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            incident_id, body.short_description, body.description,
            body.service_catalog_id, body.category, body.subcategory, body.channel,
            priority, impact, body.urgency, "new",
            caller_id, grp["group_id"], body.assigned_user_id, dept_id,
            opened_at, body.due_date,
        ),
    )
    await db.commit()
    return await _get_incident_detail(db, incident_id)


@router.patch("/{incident_id}")
async def update_incident(
    incident_id: str,
    body: IncidentUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT * FROM incident WHERE incident_id = ?", [incident_id]
    ) as cur:
        inc = await cur.fetchone()
    if inc is None:
        raise HTTPException(404, "Incident not found")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "更新フィールドが指定されていません")

    # Auto-route when catalog changes
    if "service_catalog_id" in updates:
        async with db.execute(
            "SELECT group_id FROM assignment_group WHERE catalog_id = ?",
            [updates["service_catalog_id"]],
        ) as cur:
            grp = await cur.fetchone()
        if grp:
            updates.setdefault("assigned_group_id", grp["group_id"])

    # Recalculate priority when impact or urgency changes
    if "impact" in updates or "urgency" in updates:
        new_impact = updates.get("impact", inc["impact"])
        new_urgency = updates.get("urgency", inc["urgency"])
        updates["priority"] = calc_priority(new_impact, new_urgency)

    # State transition timestamps
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    new_state = updates.get("state")
    if new_state == "resolved" and inc["resolved_at"] is None:
        updates["resolved_at"] = now
    elif new_state == "closed":
        if inc["resolved_at"] is None:
            updates["resolved_at"] = now
        updates["closed_at"] = now

    set_clause = ", ".join([k + " = ?" for k in updates])
    values = list(updates.values()) + [incident_id]
    await db.execute(
        "UPDATE incident SET " + set_clause + " WHERE incident_id = ?", values
    )
    await db.commit()
    return await _get_incident_detail(db, incident_id)


@router.get("/{incident_id}/notes")
async def list_notes(
    incident_id: str,
    note_type: Optional[str] = Query(None),
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT incident_id FROM incident WHERE incident_id = ?", [incident_id]
    ) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(404, "Incident not found")

    where = ["wn.ticket_type = 'incident'", "wn.ticket_id = ?"]
    params = [incident_id]
    if note_type:
        where.append("wn.note_type = ?")
        params.append(note_type)

    sql = """
        SELECT
            wn.note_id, wn.note_type, wn.body, wn.created_at,
            u.user_id   AS author_user_id,
            u.full_name AS author_name,
            u.username  AS author_username
        FROM work_note wn
        LEFT JOIN user u ON wn.author_user_id = u.user_id
        WHERE """ + " AND ".join(where) + """
        ORDER BY wn.created_at ASC
    """
    async with db.execute(sql, params) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/{incident_id}/notes", status_code=201)
async def add_note(
    incident_id: str,
    body: NoteCreate,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT incident_id FROM incident WHERE incident_id = ?", [incident_id]
    ) as cur:
        if await cur.fetchone() is None:
            raise HTTPException(404, "Incident not found")

    note_type = body.note_type or "work_note"
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    await db.execute(
        """INSERT INTO work_note (ticket_type, ticket_id, author_user_id, note_type, body, created_at)
           VALUES ('incident', ?, ?, ?, ?, ?)""",
        [incident_id, current_user["user_id"], note_type, body.body, created_at],
    )
    await db.commit()

    async with db.execute(
        """SELECT wn.*, u.full_name AS author_name, u.username AS author_username
           FROM work_note wn
           LEFT JOIN user u ON wn.author_user_id = u.user_id
           WHERE wn.note_id = last_insert_rowid()"""
    ) as cur:
        row = await cur.fetchone()
    return dict(row)
