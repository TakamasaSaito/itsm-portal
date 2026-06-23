from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from ..database import get_db
from ..models import ApplicationUpdate, AppDepUpdate
from .auth import get_current_user

router = APIRouter(prefix="/api")


@router.get("/applications")
async def list_applications(
    q: str = "",
    status: str = "",
    dept: str = "",
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    query = """
        SELECT a.*, d.department_name
        FROM application a
        LEFT JOIN department d ON a.owner_department_id = d.department_id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND a.status = ?"
        params.append(status)
    if dept:
        query += " AND d.department_name = ?"
        params.append(dept)
    if q:
        query += " AND (a.application_name LIKE ? OR a.application_id LIKE ? OR d.department_name LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    query += " ORDER BY a.application_id"

    async with db.execute(query, params) as cur:
        apps = [dict(row) for row in await cur.fetchall()]

    for app in apps:
        async with db.execute(
            """SELECT e.env_type FROM environment e
               JOIN cmdb_rel_ci r ON r.child_id = CAST(e.environment_id AS TEXT)
                   AND r.child_table = 'environment' AND r.parent_table = 'application'
               WHERE r.parent_id = ?""",
            [app["application_id"]],
        ) as cur:
            app["env_types"] = [row["env_type"] for row in await cur.fetchall()]

    return apps


@router.get("/applications/{app_id}")
async def get_application(
    app_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        """
        SELECT a.*, d.department_name
        FROM application a
        LEFT JOIN department d ON a.owner_department_id = d.department_id
        WHERE a.application_id = ?
        """,
        [app_id],
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Application not found")
    app = dict(row)

    async with db.execute(
        """SELECT e.* FROM environment e
           JOIN cmdb_rel_ci r ON r.child_id = CAST(e.environment_id AS TEXT)
               AND r.child_table = 'environment' AND r.parent_table = 'application'
           WHERE r.parent_id = ? ORDER BY e.environment_id""",
        [app_id],
    ) as cur:
        app["environments"] = [dict(r) for r in await cur.fetchall()]

    return app


@router.put("/applications/{app_id}")
async def update_application(
    app_id: str,
    data: ApplicationUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT application_id FROM application WHERE application_id = ?", [app_id]
    ) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "Application not found")

    updates: dict = {}
    if data.application_name is not None:
        updates["application_name"] = data.application_name
    if data.status is not None:
        updates["status"] = data.status
    if data.vendor is not None:
        updates["vendor"] = data.vendor
    if data.business_owner is not None:
        updates["business_owner"] = data.business_owner
    if data.system_owner is not None:
        updates["system_owner"] = data.system_owner
    if data.ops_manager is not None:
        updates["ops_manager"] = data.ops_manager
    if data.dev_manager is not None:
        updates["dev_manager"] = data.dev_manager
    if data.start_plan is not None:
        updates["start_plan"] = data.start_plan or None
    if data.start_actual is not None:
        updates["start_actual"] = data.start_actual or None
    if data.end_plan is not None:
        updates["end_plan"] = data.end_plan or None
    if data.end_actual is not None:
        updates["end_actual"] = data.end_actual or None
    if data.app_category is not None:
        updates["app_category"] = data.app_category or None

    if data.department_name is not None:
        async with db.execute(
            "SELECT department_id FROM department WHERE department_name = ?",
            [data.department_name],
        ) as cur:
            row = await cur.fetchone()
        if row:
            updates["owner_department_id"] = row["department_id"]

    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(
            f"UPDATE application SET {sets} WHERE application_id = ?",
            [*updates.values(), app_id],
        )
        await db.commit()
    return {"status": "updated"}


@router.get("/applications/{app_id}/overview")
async def get_application_overview(
    app_id: str,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT a.*, d.department_name FROM application a LEFT JOIN department d ON a.owner_department_id = d.department_id WHERE a.application_id = ?",
        [app_id],
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Application not found")
    application = dict(row)

    if application.get("migration_target_id"):
        async with db.execute(
            "SELECT application_name FROM application WHERE application_id = ?",
            [application["migration_target_id"]],
        ) as cur:
            mt = await cur.fetchone()
        application["migration_target_name"] = mt["application_name"] if mt else None
    else:
        application["migration_target_name"] = None

    async with db.execute(
        """SELECT d.depends_on_app_id, a.application_name AS depends_on_name, d.dependency_type
           FROM application_dependency d
           JOIN application a ON a.application_id = d.depends_on_app_id
           WHERE d.app_id = ?""",
        [app_id],
    ) as cur:
        dependencies = [dict(r) for r in await cur.fetchall()]

    async with db.execute(
        """SELECT d.app_id, a.application_name, d.dependency_type
           FROM application_dependency d
           JOIN application a ON a.application_id = d.app_id
           WHERE d.depends_on_app_id = ?""",
        [app_id],
    ) as cur:
        dependents = [dict(r) for r in await cur.fetchall()]

    async with db.execute(
        """SELECT e.* FROM environment e
           JOIN cmdb_rel_ci r ON r.child_id = CAST(e.environment_id AS TEXT)
               AND r.child_table = 'environment' AND r.parent_table = 'application'
           WHERE r.parent_id = ? ORDER BY e.environment_id""",
        [app_id],
    ) as cur:
        environments = [dict(r) for r in await cur.fetchall()]

    for env in environments:
        async with db.execute(
            """SELECT c.* FROM configuration_item c
               JOIN cmdb_rel_ci r ON r.child_id = CAST(c.ci_id AS TEXT)
                   AND r.child_table = 'configuration_item' AND r.parent_table = 'environment'
               WHERE r.parent_id = ? ORDER BY c.ci_id""",
            [str(env["environment_id"])],
        ) as cur:
            env["configuration_items"] = [dict(r) for r in await cur.fetchall()]

    async with db.execute(
        """SELECT d.demand_id, d.title, d.stage, d.priority
           FROM demand d
           JOIN demand_application da ON da.demand_id = d.demand_id
           WHERE da.application_id = ? ORDER BY d.created_at DESC""",
        [app_id],
    ) as cur:
        demands = [dict(r) for r in await cur.fetchall()]

    return {
        "application": application,
        "dependencies": dependencies,
        "dependents": dependents,
        "environments": environments,
        "demands": demands,
    }


@router.get("/stats")
async def get_stats(
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT COUNT(*) AS c FROM application WHERE status = 'running'"
    ) as cur:
        running = (await cur.fetchone())["c"]
    async with db.execute(
        "SELECT COUNT(*) AS c FROM application WHERE status IN ('dev','plan','order')"
    ) as cur:
        dev = (await cur.fetchone())["c"]
    async with db.execute(
        "SELECT COUNT(*) AS c FROM apm_request WHERE status = 'pending'"
    ) as cur:
        pending = (await cur.fetchone())["c"]
    async with db.execute("SELECT COUNT(*) AS c FROM environment") as cur:
        env_count = (await cur.fetchone())["c"]
    return {"running": running, "dev": dev, "pending": pending, "env_count": env_count}


@router.get("/application-dependencies")
async def list_application_dependencies(
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute("""
        SELECT ad.dependency_id, ad.app_id, a1.application_name AS app_name,
               ad.depends_on_app_id, a2.application_name AS depends_on_name,
               ad.dependency_type, ad.note,
               COALESCE(ad.migration_status, 'not_planned') AS migration_status,
               ad.migration_due_date, ad.migration_note
        FROM application_dependency ad
        JOIN application a1 ON a1.application_id = ad.app_id
        JOIN application a2 ON a2.application_id = ad.depends_on_app_id
        ORDER BY ad.app_id, ad.depends_on_app_id
    """) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.put("/application-dependencies/{dep_id}")
async def update_application_dependency(
    dep_id: int,
    data: AppDepUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin only")

    async with db.execute(
        "SELECT dependency_id FROM application_dependency WHERE dependency_id = ?", [dep_id]
    ) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "Dependency not found")

    updates: dict = {}
    if data.migration_status is not None:
        updates["migration_status"] = data.migration_status
    if data.migration_due_date is not None:
        updates["migration_due_date"] = data.migration_due_date or None
    if data.migration_note is not None:
        updates["migration_note"] = data.migration_note or None

    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(
            f"UPDATE application_dependency SET {sets} WHERE dependency_id = ?",
            [*updates.values(), dep_id],
        )
        await db.commit()
    return {"status": "updated"}


@router.get("/departments")
async def list_departments(
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT * FROM department ORDER BY department_id"
    ) as cur:
        return [dict(row) for row in await cur.fetchall()]
