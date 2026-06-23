from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from ..database import get_db
from ..models import CmdbRelCreate, CmdbRelUpdate
from .auth import get_current_user

router = APIRouter(prefix="/api", tags=["cmdb"])

_REL_SELECT = """
    SELECT r.*, rt.type_name AS relation_type, rt.parent_label AS relation_label
    FROM cmdb_rel_ci r
    LEFT JOIN relation_type rt ON rt.relation_type_id = r.relation_type_id
"""


async def _resolve_name(db: aiosqlite.Connection, table: str, record_id: str) -> str:
    try:
        if table == "application":
            async with db.execute(
                "SELECT application_name FROM application WHERE application_id = ?", [record_id]
            ) as cur:
                row = await cur.fetchone()
            return row["application_name"] if row else record_id
        elif table == "environment":
            async with db.execute(
                "SELECT env_type FROM environment WHERE environment_id = ?", [int(record_id)]
            ) as cur:
                row = await cur.fetchone()
            return row["env_type"] if row else f"env#{record_id}"
        elif table == "configuration_item":
            async with db.execute(
                "SELECT ci_name FROM configuration_item WHERE ci_id = ?", [int(record_id)]
            ) as cur:
                row = await cur.fetchone()
            return row["ci_name"] if row else f"ci#{record_id}"
    except Exception:
        pass
    return record_id


async def _enrich(db: aiosqlite.Connection, row: dict) -> dict:
    row["parent_name"] = await _resolve_name(db, row["parent_table"], row["parent_id"])
    row["child_name"]  = await _resolve_name(db, row["child_table"],  row["child_id"])
    return row


@router.get("/relation-types")
async def list_relation_types(
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute("SELECT * FROM relation_type ORDER BY relation_type_id") as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/cmdb-relations")
async def list_cmdb_relations(
    db: aiosqlite.Connection = Depends(get_db),
    _: dict = Depends(get_current_user),
):
    async with db.execute(_REL_SELECT + " ORDER BY r.rel_id") as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    return [await _enrich(db, r) for r in rows]


@router.post("/cmdb-relations", status_code=201)
async def create_cmdb_relation(
    payload: CmdbRelCreate,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin only")

    async with db.execute(
        """INSERT INTO cmdb_rel_ci
               (parent_table, parent_id, child_table, child_id, relation_type_id, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [payload.parent_table, payload.parent_id, payload.child_table,
         payload.child_id, payload.relation_type_id, payload.note],
    ) as cur:
        rel_id = cur.lastrowid
    await db.commit()

    async with db.execute(_REL_SELECT + " WHERE r.rel_id = ?", [rel_id]) as cur:
        row = dict(await cur.fetchone())
    return await _enrich(db, row)


@router.put("/cmdb-relations/{rel_id}")
async def update_cmdb_relation(
    rel_id: int,
    payload: CmdbRelUpdate,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin only")

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(f"UPDATE cmdb_rel_ci SET {sets} WHERE rel_id = ?", [*updates.values(), rel_id])
        await db.commit()
    return {"status": "updated"}


@router.delete("/cmdb-relations/{rel_id}", status_code=204)
async def delete_cmdb_relation(
    rel_id: int,
    db: aiosqlite.Connection = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin only")

    await db.execute("DELETE FROM cmdb_rel_ci WHERE rel_id = ?", [rel_id])
    await db.commit()
