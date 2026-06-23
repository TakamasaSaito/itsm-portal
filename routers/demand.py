from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from datetime import date
from ..database import get_db
from ..models import (DemandCreate, DemandUpdate, DemandStageUpdate,
                      DemandTaskCreate, DemandTaskUpdate,
                      DemandApplicationCreate, CostPlanCreate, CostPlanUpdate,
                      ProjectCreate)
from .auth import get_current_user

router = APIRouter(prefix="/api")


def _next_demand_id(cur):
    cur.execute("SELECT demand_id FROM demand ORDER BY demand_id DESC LIMIT 1")
    row = cur.fetchone()
    if row:
        num = int(row[0].replace("DMND", "")) + 1
    else:
        num = 1001001
    return f"DMND{num:07d}"


def _next_task_id(cur):
    cur.execute("SELECT task_id FROM demand_task ORDER BY task_id DESC LIMIT 1")
    row = cur.fetchone()
    if row:
        num = int(row[0].replace("DMNTSK", "")) + 1
    else:
        num = 4001001
    return f"DMNTSK{num:07d}"


def _next_project_id(cur):
    cur.execute("SELECT project_id FROM project ORDER BY project_id DESC LIMIT 1")
    row = cur.fetchone()
    if row:
        num = int(row[0].replace("PROJ", "")) + 1
    else:
        num = 1
    return f"PROJ{num:05d}"


async def _demand_with_users(db, demand_id):
    async with db.execute("""
        SELECT d.*,
               u1.user_name AS submitter_name,
               u2.user_name AS manager_name,
               u3.user_name AS system_owner_name,
               u4.user_name AS pm_name,
               dep.department_name
        FROM demand d
        LEFT JOIN user u1 ON d.submitter_user_id = u1.user_id
        LEFT JOIN user u2 ON d.manager_user_id = u2.user_id
        LEFT JOIN user u3 ON d.system_owner_user_id = u3.user_id
        LEFT JOIN user u4 ON d.pm_user_id = u4.user_id
        LEFT JOIN department dep ON d.department_id = dep.department_id
        WHERE d.demand_id = ?
    """, [demand_id]) as cur:
        row = await cur.fetchone()
        return dict(row) if row else None


# ── デマンド一覧 ──────────────────────────────────────────────
@router.get("/demands")
async def list_demands(
    stage: str = "",
    priority: str = "",
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    q = """
        SELECT d.*,
               u1.user_name AS submitter_name,
               u2.user_name AS manager_name,
               dep.department_name,
               (SELECT COUNT(*) FROM demand_application da WHERE da.demand_id = d.demand_id) AS related_app_count,
               (SELECT GROUP_CONCAT(da.application_id) FROM demand_application da WHERE da.demand_id = d.demand_id) AS related_app_ids,
               p.project_id AS linked_project_id,
               p.status     AS linked_project_status,
               p.title      AS linked_project_title
        FROM demand d
        LEFT JOIN user u1  ON d.submitter_user_id = u1.user_id
        LEFT JOIN user u2  ON d.manager_user_id   = u2.user_id
        LEFT JOIN department dep ON d.department_id = dep.department_id
        LEFT JOIN project p ON p.demand_id = d.demand_id
        WHERE 1=1
    """
    params = []
    if stage:
        q += " AND d.stage = ?"
        params.append(stage)
    if priority:
        q += " AND d.priority = ?"
        params.append(priority)
    q += " ORDER BY d.created_at DESC"
    async with db.execute(q, params) as cur:
        return [dict(r) for r in await cur.fetchall()]


# ── デマンド詳細 ──────────────────────────────────────────────
@router.get("/demands/{demand_id}")
async def get_demand(
    demand_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    d = await _demand_with_users(db, demand_id)
    if not d:
        raise HTTPException(404, "demand not found")
    return d


# ── デマンド新規作成 ──────────────────────────────────────────
@router.post("/demands", status_code=201)
async def create_demand(
    payload: DemandCreate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute("SELECT demand_id FROM demand ORDER BY demand_id DESC LIMIT 1") as cur:
        row = await cur.fetchone()
    num = int(row["demand_id"].replace("DMND", "")) + 1 if row else 1001001
    demand_id = f"DMND{num:07d}"

    data = payload.dict()
    cols = list(data.keys())
    vals = [data[c] for c in cols]
    placeholders = ",".join("?" * len(cols))
    await db.execute(
        f"INSERT INTO demand (demand_id,{','.join(cols)}) VALUES (?," + placeholders + ")",
        [demand_id] + vals,
    )
    await db.commit()
    return await _demand_with_users(db, demand_id)


# ── デマンド更新 ──────────────────────────────────────────────
@router.put("/demands/{demand_id}")
async def update_demand(
    demand_id: str,
    payload: DemandUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    d = await _demand_with_users(db, demand_id)
    if not d:
        raise HTTPException(404, "demand not found")
    data = {k: v for k, v in payload.dict().items() if v is not None}
    if not data:
        return d
    set_clause = ", ".join(f"{k}=?" for k in data)
    await db.execute(
        f"UPDATE demand SET {set_clause}, updated_at=CURRENT_TIMESTAMP WHERE demand_id=?",
        list(data.values()) + [demand_id],
    )
    await db.commit()
    return await _demand_with_users(db, demand_id)


# ── ステージ変更 ──────────────────────────────────────────────
@router.put("/demands/{demand_id}/stage")
async def update_stage(
    demand_id: str,
    payload: DemandStageUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    d = await _demand_with_users(db, demand_id)
    if not d:
        raise HTTPException(404, "demand not found")
    await db.execute(
        """UPDATE demand SET stage=?, reject_reason=?, review_comment=?, approval_comment=?,
           updated_at=CURRENT_TIMESTAMP WHERE demand_id=?""",
        [payload.stage, payload.reject_reason, payload.review_comment, payload.approval_comment, demand_id],
    )
    await db.commit()
    return await _demand_with_users(db, demand_id)


# ── タスク一覧 ────────────────────────────────────────────────
@router.get("/demands/{demand_id}/tasks")
async def list_tasks(
    demand_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        """SELECT t.*, u.user_name AS assignee_name
           FROM demand_task t
           LEFT JOIN user u ON t.assignee_user_id = u.user_id
           WHERE t.demand_id=? ORDER BY t.created_at""",
        [demand_id],
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


# ── タスク追加 ────────────────────────────────────────────────
@router.post("/demands/{demand_id}/tasks", status_code=201)
async def create_task(
    demand_id: str,
    payload: DemandTaskCreate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute("SELECT task_id FROM demand_task ORDER BY task_id DESC LIMIT 1") as cur:
        row = await cur.fetchone()
    num = int(row["task_id"].replace("DMNTSK", "")) + 1 if row else 4001001
    task_id = f"DMNTSK{num:07d}"

    data = payload.dict()
    data["demand_id"] = demand_id
    cols = list(data.keys())
    vals = [data[c] for c in cols]
    await db.execute(
        f"INSERT INTO demand_task (task_id,{','.join(cols)}) VALUES (?," + ",".join("?" * len(cols)) + ")",
        [task_id] + vals,
    )
    await db.commit()
    async with db.execute(
        "SELECT t.*, u.user_name AS assignee_name FROM demand_task t LEFT JOIN user u ON t.assignee_user_id=u.user_id WHERE t.task_id=?",
        [task_id],
    ) as cur:
        row = await cur.fetchone()
    return dict(row)


# ── タスク更新 ────────────────────────────────────────────────
@router.put("/demands/{demand_id}/tasks/{task_id}")
async def update_task(
    demand_id: str,
    task_id: str,
    payload: DemandTaskUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    data = {k: v for k, v in payload.dict().items() if v is not None}
    if not data:
        raise HTTPException(400, "no fields to update")
    set_clause = ", ".join(f"{k}=?" for k in data)
    await db.execute(
        f"UPDATE demand_task SET {set_clause} WHERE task_id=? AND demand_id=?",
        list(data.values()) + [task_id, demand_id],
    )
    await db.commit()
    async with db.execute(
        "SELECT t.*, u.user_name AS assignee_name FROM demand_task t LEFT JOIN user u ON t.assignee_user_id=u.user_id WHERE t.task_id=?",
        [task_id],
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else {}


# ── 承認（プロジェクト自動作成）──────────────────────────────
@router.post("/demands/{demand_id}/approve")
async def approve_demand(
    demand_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    d = await _demand_with_users(db, demand_id)
    if not d:
        raise HTTPException(404, "demand not found")

    async with db.execute("SELECT project_id FROM project ORDER BY project_id DESC LIMIT 1") as cur:
        row = await cur.fetchone()
    num = int(row["project_id"].replace("PROJ", "")) + 1 if row else 1
    project_id = f"PROJ{num:05d}"

    await db.execute(
        "INSERT INTO project (project_id, demand_id, title, status, created_date) VALUES (?,?,?,?,?)",
        [project_id, demand_id, d["title"], "active", date.today().isoformat()],
    )
    await db.execute(
        "UPDATE demand SET stage='approved', updated_at=CURRENT_TIMESTAMP WHERE demand_id=?",
        [demand_id],
    )
    await db.commit()
    return {"project_id": project_id, "demand_id": demand_id}


# ── 却下 ─────────────────────────────────────────────────────
@router.post("/demands/{demand_id}/reject")
async def reject_demand(
    demand_id: str,
    payload: DemandStageUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    d = await _demand_with_users(db, demand_id)
    if not d:
        raise HTTPException(404, "demand not found")
    await db.execute(
        "UPDATE demand SET stage='rejected', reject_reason=?, updated_at=CURRENT_TIMESTAMP WHERE demand_id=?",
        [payload.reject_reason, demand_id],
    )
    await db.commit()
    return await _demand_with_users(db, demand_id)


# ── 関連システム一覧 ──────────────────────────────────────────
@router.get("/demands/{demand_id}/applications")
async def list_demand_applications(
    demand_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        """SELECT da.*, a.application_name, a.app_category, a.status AS app_status
           FROM demand_application da
           LEFT JOIN application a ON da.application_id = a.application_id
           WHERE da.demand_id = ? ORDER BY da.id""",
        [demand_id],
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


# ── 関連システム追加 ──────────────────────────────────────────
@router.post("/demands/{demand_id}/applications", status_code=201)
async def add_demand_application(
    demand_id: str,
    payload: DemandApplicationCreate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT id FROM demand_application WHERE demand_id=? AND application_id=?",
        [demand_id, payload.application_id],
    ) as cur:
        if await cur.fetchone():
            raise HTTPException(409, "already linked")
    await db.execute(
        "INSERT INTO demand_application (demand_id, application_id, relation_note) VALUES (?,?,?)",
        [demand_id, payload.application_id, payload.relation_note],
    )
    await db.commit()
    async with db.execute(
        """SELECT da.*, a.application_name, a.app_category, a.status AS app_status
           FROM demand_application da
           LEFT JOIN application a ON da.application_id = a.application_id
           WHERE da.demand_id = ? ORDER BY da.id""",
        [demand_id],
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


# ── 関連システム削除 ──────────────────────────────────────────
@router.delete("/demands/{demand_id}/applications/{application_id}", status_code=204)
async def remove_demand_application(
    demand_id: str,
    application_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    await db.execute(
        "DELETE FROM demand_application WHERE demand_id=? AND application_id=?",
        [demand_id, application_id],
    )
    await db.commit()


# ── コスト計画一覧 ────────────────────────────────────────────
@router.get("/demands/{demand_id}/cost-plans")
async def list_cost_plans(
    demand_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT * FROM cost_plan WHERE demand_id=? ORDER BY fiscal_year, fiscal_period",
        [demand_id],
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


# ── コスト計画追加 ────────────────────────────────────────────
@router.post("/demands/{demand_id}/cost-plans", status_code=201)
async def create_cost_plan(
    demand_id: str,
    payload: CostPlanCreate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    data = payload.dict()
    data["demand_id"] = demand_id
    cols = list(data.keys())
    vals = [data[c] for c in cols]
    await db.execute(
        f"INSERT INTO cost_plan ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})",
        vals,
    )
    await db.commit()
    async with db.execute(
        "SELECT * FROM cost_plan WHERE demand_id=? ORDER BY fiscal_year, fiscal_period",
        [demand_id],
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


# ── コスト計画更新 ────────────────────────────────────────────
@router.put("/cost-plans/{cost_plan_id}")
async def update_cost_plan(
    cost_plan_id: int,
    payload: CostPlanUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    data = {k: v for k, v in payload.dict().items() if v is not None}
    if not data:
        raise HTTPException(400, "no fields to update")
    set_clause = ", ".join(f"{k}=?" for k in data)
    await db.execute(
        f"UPDATE cost_plan SET {set_clause} WHERE cost_plan_id=?",
        list(data.values()) + [cost_plan_id],
    )
    await db.commit()
    async with db.execute("SELECT * FROM cost_plan WHERE cost_plan_id=?", [cost_plan_id]) as cur:
        row = await cur.fetchone()
    return dict(row) if row else {}


# ── コスト計画削除 ────────────────────────────────────────────
@router.delete("/cost-plans/{cost_plan_id}", status_code=204)
async def delete_cost_plan(
    cost_plan_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    await db.execute("DELETE FROM cost_plan WHERE cost_plan_id=?", [cost_plan_id])
    await db.commit()


# ── プロジェクト一覧 ──────────────────────────────────────────
@router.get("/projects")
async def list_projects(
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        """SELECT p.*, d.priority, d.stage AS demand_stage,
                  u.user_name AS manager_name
           FROM project p
           LEFT JOIN demand d ON p.demand_id = d.demand_id
           LEFT JOIN user u ON p.manager_user_id = u.user_id
           ORDER BY p.created_at DESC"""
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.post("/projects", status_code=201)
async def create_project(
    body: ProjectCreate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute("SELECT project_id FROM project ORDER BY project_id DESC LIMIT 1") as cur:
        row = await cur.fetchone()
    num = int(row["project_id"].replace("PROJ", "")) + 1 if row else 1
    project_id = f"PROJ{num:05d}"
    created_date = body.created_date or date.today().isoformat()
    await db.execute(
        """INSERT INTO project (project_id, demand_id, title, status, manager_user_id, portfolio, description, created_date)
           VALUES (?,?,?,?,?,?,?,?)""",
        [project_id, body.demand_id, body.title, body.status or "pending",
         body.manager_user_id, body.portfolio, body.description, created_date],
    )
    await db.commit()
    return {"project_id": project_id}


# ── プロジェクト詳細 ──────────────────────────────────────────
@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        """SELECT p.*, u.user_name AS manager_name
           FROM project p
           LEFT JOIN user u ON p.manager_user_id = u.user_id
           WHERE p.project_id=?""",
        [project_id],
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "project not found")
    return dict(row)
