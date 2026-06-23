from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from ..database import get_db
from ..models import EnvironmentCreate, EnvironmentUpdate
from .auth import get_current_user

router = APIRouter(prefix="/api")

_ENV_SELECT = """
    SELECT e.*,
           rel.parent_id      AS application_id,
           a.application_name
    FROM environment e
    LEFT JOIN cmdb_rel_ci rel
        ON  rel.child_id     = CAST(e.environment_id AS TEXT)
        AND rel.child_table  = 'environment'
        AND rel.parent_table = 'application'
    LEFT JOIN application a ON a.application_id = rel.parent_id
"""

_HAS_ENV_ID = "(SELECT relation_type_id FROM relation_type WHERE type_name='has_environment')"


@router.get("/environments")
async def list_environments(
    q: str = "",
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    query = _ENV_SELECT + " WHERE 1=1"
    params = []
    if q:
        query += (
            " AND (rel.parent_id LIKE ? OR a.application_name LIKE ?"
            " OR e.ip LIKE ? OR e.env_type LIKE ?)"
        )
        params += [f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"]
    query += " ORDER BY rel.parent_id, e.environment_id"
    async with db.execute(query, params) as cur:
        return [dict(row) for row in await cur.fetchall()]


@router.post("/environments", status_code=201)
async def create_environment(
    data: EnvironmentCreate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        """INSERT INTO environment
               (env_type, location, ip, host, os, middleware, cpu_mem, storage)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [data.env_type, data.location, data.ip, data.host,
         data.os, data.middleware, data.cpu_mem, data.storage],
    ) as cur:
        env_id = cur.lastrowid

    if data.application_id:
        await db.execute(
            f"""INSERT INTO cmdb_rel_ci
                   (parent_table, parent_id, child_table, child_id, relation_type_id)
                   VALUES ('application', ?, 'environment', ?, {_HAS_ENV_ID})""",
            [data.application_id, str(env_id)],
        )

    await db.commit()
    async with db.execute(_ENV_SELECT + " WHERE e.environment_id = ?", [env_id]) as cur:
        return dict(await cur.fetchone())


@router.put("/environments/{env_id}")
async def update_environment(
    env_id: int,
    data: EnvironmentUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    all_fields = data.model_dump()
    new_app_id = all_fields.pop("application_id")  # None if not provided
    updates = {k: v for k, v in all_fields.items() if v is not None}

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(
            f"UPDATE environment SET {set_clause} WHERE environment_id = ?",
            [*updates.values(), env_id],
        )

    if new_app_id is not None:
        await db.execute(
            """DELETE FROM cmdb_rel_ci
               WHERE child_id = ? AND child_table = 'environment' AND parent_table = 'application'""",
            [str(env_id)],
        )
        if new_app_id:
            await db.execute(
                f"""INSERT INTO cmdb_rel_ci
                       (parent_table, parent_id, child_table, child_id, relation_type_id)
                       VALUES ('application', ?, 'environment', ?, {_HAS_ENV_ID})""",
                [new_app_id, str(env_id)],
            )

    await db.commit()
    async with db.execute(_ENV_SELECT + " WHERE e.environment_id = ?", [env_id]) as cur:
        return dict(await cur.fetchone())


@router.delete("/environments/{env_id}", status_code=204)
async def delete_environment(
    env_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    await db.execute(
        "DELETE FROM cmdb_rel_ci WHERE child_id = ? AND child_table = 'environment'",
        [str(env_id)],
    )
    await db.execute("DELETE FROM environment WHERE environment_id = ?", [env_id])
    await db.commit()
