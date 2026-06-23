from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
import json
from datetime import datetime
from ..database import get_db
from ..models import RequestCreate
from .auth import get_current_user

router = APIRouter(prefix="/api")

STATUS_MAP = {
    "running": "本番稼働中",
    "plan": "企画",
    "dev": "開発中",
    "order": "発注中",
    "retire": "廃止",
}
STATUS_MAP_REV = {v: k for k, v in STATUS_MAP.items()}


async def _next_request_id(db: aiosqlite.Connection) -> str:
    async with db.execute("SELECT request_id FROM apm_request") as cur:
        rows = await cur.fetchall()
    nums = []
    for row in rows:
        try:
            nums.append(int(row["request_id"].split("-")[1]))
        except Exception:
            pass
    return f"REQ-{str(max(nums, default=0) + 1).zfill(3)}"


async def _next_app_id(db: aiosqlite.Connection) -> str:
    async with db.execute("SELECT application_id FROM application") as cur:
        rows = await cur.fetchall()
    nums = []
    for row in rows:
        try:
            nums.append(int(row["application_id"].split("-")[1]))
        except Exception:
            pass
    return f"APM-{str(max(nums, default=0) + 1).zfill(3)}"


@router.get("/requests")
async def list_requests(
    status: str = "",
    type: str = "",
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    query = """
        SELECT r.*,
               u1.user_name AS applicant_name,
               u2.user_name AS approver_name,
               a.application_name,
               a.status AS app_status,
               a.business_owner AS app_biz_owner,
               a.system_owner AS app_sys_owner,
               a.start_actual AS app_start_actual
        FROM apm_request r
        LEFT JOIN user u1 ON r.applicant_user_id = u1.user_id
        LEFT JOIN user u2 ON r.approver_user_id = u2.user_id
        LEFT JOIN application a ON r.application_id = a.application_id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND r.status = ?"
        params.append(status)
    if type:
        query += " AND r.type = ?"
        params.append(type)
    query += " ORDER BY r.applied_at DESC"

    async with db.execute(query, params) as cur:
        rows = [dict(row) for row in await cur.fetchall()]

    for row in rows:
        if row["application_id"]:
            async with db.execute(
                """SELECT e.* FROM environment e
                   JOIN cmdb_rel_ci r ON r.child_id = CAST(e.environment_id AS TEXT)
                       AND r.child_table = 'environment' AND r.parent_table = 'application'
                   WHERE r.parent_id = ? ORDER BY e.environment_id""",
                [row["application_id"]],
            ) as cur:
                row["app_envs"] = [dict(e) for e in await cur.fetchall()]
        else:
            row["app_envs"] = []

        if row.get("changes") and isinstance(row["changes"], str):
            try:
                row["changes"] = json.loads(row["changes"])
            except Exception:
                row["changes"] = []

    return rows


@router.post("/requests", status_code=201)
async def create_request(
    data: RequestCreate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    req_id = await _next_request_id(db)
    applied_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    changes = None
    if data.type == "update" and data.application_id:
        async with db.execute(
            "SELECT * FROM application WHERE application_id = ?", [data.application_id]
        ) as cur:
            app = dict(await cur.fetchone())
        changes_list = []
        if data.upd_status and data.upd_status != app["status"]:
            changes_list.append({
                "label": "ステータス", "field": "status",
                "before": STATUS_MAP.get(app["status"], app["status"]),
                "after": STATUS_MAP.get(data.upd_status, data.upd_status),
            })
        if data.upd_biz_owner and data.upd_biz_owner != app["business_owner"]:
            changes_list.append({
                "label": "ビジネスオーナー", "field": "business_owner",
                "before": app["business_owner"] or "", "after": data.upd_biz_owner,
            })
        if data.upd_end_plan and data.upd_end_plan != app["end_plan"]:
            changes_list.append({
                "label": "廃止予定日", "field": "end_plan",
                "before": app["end_plan"] or "", "after": data.upd_end_plan,
            })
        if data.upd_start_actual and data.upd_start_actual != app["start_actual"]:
            changes_list.append({
                "label": "サービス開始（実績）", "field": "start_actual",
                "before": app["start_actual"] or "", "after": data.upd_start_actual,
            })
        changes = json.dumps(changes_list, ensure_ascii=False)

    await db.execute(
        """
        INSERT INTO apm_request
            (request_id, type, application_id, applicant_user_id, applied_at, status,
             reason, changes, app_name, dept, biz_owner, new_status, start_plan, end_plan, app_category)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            req_id, data.type, data.application_id, data.applicant_user_id,
            applied_at, data.reason, changes,
            data.app_name, data.dept, data.biz_owner,
            data.new_status, data.start_plan, data.end_plan, data.app_category,
        ],
    )
    await db.commit()
    return {"request_id": req_id, "status": "pending"}


@router.put("/requests/{req_id}/approve")
async def approve_request(
    req_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT * FROM apm_request WHERE request_id = ?", [req_id]
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Request not found")
    req = dict(row)
    if req["status"] != "pending":
        raise HTTPException(400, "Request is not pending")
    if current_user.get("role") != "admin":
        raise HTTPException(403, "承認権限がありません")

    approver_user_id = current_user["user_id"]
    approved_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    await db.execute(
        "UPDATE apm_request SET status='approved', approver_user_id=?, approved_at=? WHERE request_id=?",
        [approver_user_id, approved_at, req_id],
    )

    if req["type"] == "retire" and req["application_id"]:
        end_actual = datetime.now().strftime("%Y-%m-%d")
        await db.execute(
            "UPDATE application SET status='retire', end_actual=? WHERE application_id=?",
            [end_actual, req["application_id"]],
        )

    elif req["type"] == "update" and req["application_id"] and req["changes"]:
        changes = json.loads(req["changes"])
        for ch in changes:
            field = ch.get("field")
            after = ch.get("after")
            if field and after is not None:
                await db.execute(
                    f"UPDATE application SET {field}=? WHERE application_id=?",
                    [after, req["application_id"]],
                )

    elif req["type"] == "register":
        new_app_id = await _next_app_id(db)
        async with db.execute(
            "SELECT department_id FROM department WHERE department_name=?", [req["dept"]]
        ) as cur:
            dept_row = await cur.fetchone()
        dept_id = dept_row["department_id"] if dept_row else None
        new_status = STATUS_MAP_REV.get(req["new_status"], req["new_status"] or "plan")
        await db.execute(
            """
            INSERT INTO application
                (application_id, application_name, owner_department_id, status,
                 business_owner, start_plan, app_category)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [new_app_id, req["app_name"] or "新規アプリ", dept_id, new_status,
             req["biz_owner"], req["start_plan"], req.get("app_category")],
        )
        await db.execute(
            "UPDATE apm_request SET application_id=? WHERE request_id=?",
            [new_app_id, req_id],
        )

    await db.commit()
    return {"status": "approved"}


@router.put("/requests/{req_id}/reject")
async def reject_request(
    req_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT status FROM apm_request WHERE request_id = ?", [req_id]
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Request not found")
    if dict(row)["status"] != "pending":
        raise HTTPException(400, "Request is not pending")
    if current_user.get("role") != "admin":
        raise HTTPException(403, "承認権限がありません")

    approver_user_id = current_user["user_id"]
    approved_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    await db.execute(
        "UPDATE apm_request SET status='rejected', approver_user_id=?, approved_at=? WHERE request_id=?",
        [approver_user_id, approved_at, req_id],
    )
    await db.commit()
    return {"status": "rejected"}
