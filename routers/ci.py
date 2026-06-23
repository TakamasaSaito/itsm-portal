from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from ..database import get_db
from ..models import ConfigurationItemCreate, ConfigurationItemUpdate
from .auth import get_current_user

router = APIRouter(prefix="/api/ci", tags=["ci"])

_CI_SELECT = """
    SELECT c.*,
           CAST(env_rel.parent_id AS INTEGER) AS environment_id,
           e.env_type,
           app_rel.parent_id                  AS application_id,
           a.application_name
    FROM configuration_item c
    LEFT JOIN cmdb_rel_ci env_rel
        ON  env_rel.child_id     = CAST(c.ci_id AS TEXT)
        AND env_rel.child_table  = 'configuration_item'
        AND env_rel.parent_table = 'environment'
    LEFT JOIN environment e
        ON  e.environment_id = CAST(env_rel.parent_id AS INTEGER)
    LEFT JOIN cmdb_rel_ci app_rel
        ON  app_rel.child_id     = env_rel.parent_id
        AND app_rel.child_table  = 'environment'
        AND app_rel.parent_table = 'application'
    LEFT JOIN application a ON a.application_id = app_rel.parent_id
"""

_HAS_CI_ID = "(SELECT relation_type_id FROM relation_type WHERE type_name='has_ci')"


@router.get("")
async def list_ci(
    environment_id: int = 0,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    query = _CI_SELECT + " WHERE 1=1"
    params = []
    if environment_id:
        query += " AND env_rel.parent_id = ?"
        params.append(str(environment_id))
    query += " ORDER BY c.ci_id"
    async with db.execute(query, params) as cur:
        return [dict(row) for row in await cur.fetchall()]


@router.get("/{ci_id}")
async def get_ci(
    ci_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(_CI_SELECT + " WHERE c.ci_id = ?", [ci_id]) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(404, "CI not found")
    return dict(row)


@router.post("", status_code=201)
async def create_ci(
    data: ConfigurationItemCreate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        """INSERT INTO configuration_item
               (ci_name, ci_type, hostname, ip_address, bmc_ip,
                os, os_version, cpu, memory, storage, vendor, model, status, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [data.ci_name, data.ci_type, data.hostname, data.ip_address, data.bmc_ip,
         data.os, data.os_version, data.cpu, data.memory, data.storage,
         data.vendor, data.model, data.status or "active", data.note],
    ) as cur:
        ci_id = cur.lastrowid

    if data.environment_id:
        await db.execute(
            f"""INSERT INTO cmdb_rel_ci
                   (parent_table, parent_id, child_table, child_id, relation_type_id)
                   VALUES ('environment', ?, 'configuration_item', ?, {_HAS_CI_ID})""",
            [str(data.environment_id), str(ci_id)],
        )

    await db.commit()
    return {"ci_id": ci_id}


@router.put("/{ci_id}")
async def update_ci(
    ci_id: int,
    data: ConfigurationItemUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    all_fields = data.model_dump()
    new_env_id = all_fields.pop("environment_id")  # None if not provided
    updates = {k: v for k, v in all_fields.items() if v is not None}

    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(
            f"UPDATE configuration_item SET {sets} WHERE ci_id = ?",
            [*updates.values(), ci_id],
        )

    if new_env_id is not None:
        await db.execute(
            """DELETE FROM cmdb_rel_ci
               WHERE child_id = ? AND child_table = 'configuration_item' AND parent_table = 'environment'""",
            [str(ci_id)],
        )
        if new_env_id:
            await db.execute(
                f"""INSERT INTO cmdb_rel_ci
                       (parent_table, parent_id, child_table, child_id, relation_type_id)
                       VALUES ('environment', ?, 'configuration_item', ?, {_HAS_CI_ID})""",
                [str(new_env_id), str(ci_id)],
            )

    await db.commit()
    return {"status": "updated"}


@router.delete("/{ci_id}", status_code=204)
async def delete_ci(
    ci_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(
        "SELECT ci_id FROM configuration_item WHERE ci_id = ?", [ci_id]
    ) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "CI not found")
    await db.execute(
        "DELETE FROM cmdb_rel_ci WHERE child_id = ? AND child_table = 'configuration_item'",
        [str(ci_id)],
    )
    await db.execute("DELETE FROM configuration_item WHERE ci_id = ?", [ci_id])
    await db.commit()
