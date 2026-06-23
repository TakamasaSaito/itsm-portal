import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "apm.db")

async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()

async def init_db():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS relation_type (
  relation_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
  type_name        TEXT NOT NULL UNIQUE,
  parent_label     TEXT,
  child_label      TEXT
);

CREATE TABLE IF NOT EXISTS cmdb_rel_ci (
  rel_id           INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_table     TEXT NOT NULL,
  parent_id        TEXT NOT NULL,
  child_table      TEXT NOT NULL,
  child_id         TEXT NOT NULL,
  relation_type_id INTEGER REFERENCES relation_type(relation_type_id),
  note             TEXT,
  created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS demand (
  demand_id      TEXT PRIMARY KEY,
  title          TEXT NOT NULL,
  it_class       TEXT,
  category       TEXT,
  domain         TEXT,
  type           TEXT,
  start_date     DATE,
  due_date       DATE,
  submitter_user_id   INTEGER REFERENCES user(user_id),
  department_id       INTEGER REFERENCES department(department_id),
  manager_user_id     INTEGER REFERENCES user(user_id),
  system_owner_user_id INTEGER REFERENCES user(user_id),
  pm_user_id          INTEGER REFERENCES user(user_id),
  description    TEXT,
  portfolio      TEXT,
  program        TEXT,
  change_type    TEXT,
  purpose        TEXT,
  feasibility    TEXT,
  priority       TEXT,
  region         TEXT,
  company        TEXT,
  business_unit  TEXT,
  business_case  TEXT,
  expected_benefit TEXT,
  target_date    DATE,
  estimated_cost INTEGER,
  requested_budget INTEGER,
  cost_note      TEXT,
  notes          TEXT,
  stage          TEXT DEFAULT 'draft',
  reject_reason  TEXT,
  review_comment TEXT,
  approval_comment TEXT,
  created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS demand_application (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  demand_id      TEXT REFERENCES demand(demand_id),
  application_id TEXT REFERENCES application(application_id),
  relation_note  TEXT
);

CREATE TABLE IF NOT EXISTS cost_plan (
  cost_plan_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  demand_id      TEXT REFERENCES demand(demand_id),
  fiscal_year    INTEGER,
  fiscal_period  TEXT,
  cost_type      TEXT,
  unit_cost      INTEGER,
  quantity       INTEGER DEFAULT 1,
  planned_cost   INTEGER,
  actual_cost    INTEGER DEFAULT 0,
  note           TEXT,
  created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS demand_task (
  task_id        TEXT PRIMARY KEY,
  demand_id      TEXT REFERENCES demand(demand_id),
  name           TEXT NOT NULL,
  due_date       DATE,
  assignee_user_id INTEGER REFERENCES user(user_id),
  priority       TEXT,
  state          TEXT DEFAULT 'open',
  comment        TEXT,
  ai_generated   INTEGER DEFAULT 0,
  rationale      TEXT,
  created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project (
  project_id     TEXT PRIMARY KEY,
  demand_id      TEXT REFERENCES demand(demand_id),
  title          TEXT NOT NULL,
  status         TEXT DEFAULT 'active',
  created_date   DATE,
  created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS department (
    department_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    department_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS user (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name     TEXT NOT NULL,
    department_id INTEGER REFERENCES department(department_id),
    role          TEXT NOT NULL DEFAULT 'applicant',
    login_id      TEXT,
    password_hash TEXT
);

CREATE TABLE IF NOT EXISTS application (
    application_id       TEXT PRIMARY KEY,
    application_name     TEXT NOT NULL,
    owner_department_id  INTEGER REFERENCES department(department_id),
    status               TEXT NOT NULL DEFAULT 'plan',
    vendor               TEXT,
    business_owner       TEXT,
    system_owner         TEXT,
    ops_manager          TEXT,
    dev_manager          TEXT,
    start_plan           TEXT,
    start_actual         TEXT,
    end_plan             TEXT,
    end_actual           TEXT,
    app_category         TEXT,
    portfolio_area       INTEGER,
    migration_target_id  TEXT REFERENCES application(application_id),
    annual_cost_million  INTEGER,
    is_infrastructure    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS application_dependency (
    dependency_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id            TEXT REFERENCES application(application_id),
    depends_on_app_id TEXT REFERENCES application(application_id),
    dependency_type   TEXT,
    note              TEXT
);

CREATE TABLE IF NOT EXISTS environment (
    environment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    env_type       TEXT NOT NULL,
    location       TEXT,
    ip             TEXT,
    host           TEXT,
    os             TEXT,
    middleware     TEXT,
    cpu_mem        TEXT,
    storage        TEXT
);

CREATE TABLE IF NOT EXISTS configuration_item (
    ci_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ci_name        TEXT NOT NULL,
    ci_type        TEXT,
    hostname       TEXT,
    ip_address     TEXT,
    bmc_ip         TEXT,
    os             TEXT,
    os_version     TEXT,
    cpu            TEXT,
    memory         TEXT,
    storage        TEXT,
    vendor         TEXT,
    model          TEXT,
    status         TEXT DEFAULT 'active',
    note           TEXT
);

CREATE TABLE IF NOT EXISTS apm_request (
    request_id        TEXT PRIMARY KEY,
    type              TEXT NOT NULL,
    application_id    TEXT REFERENCES application(application_id),
    applicant_user_id INTEGER REFERENCES user(user_id),
    applied_at        TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    approver_user_id  INTEGER REFERENCES user(user_id),
    approved_at       TEXT,
    reason            TEXT,
    changes           TEXT,
    app_name          TEXT,
    dept              TEXT,
    biz_owner         TEXT,
    new_status        TEXT,
    start_plan        TEXT,
    end_plan          TEXT,
    app_category      TEXT
);
        """)

        # Seed relation_type master data
        for row in (
            ("has_environment", "環境を持つ", "環境である"),
            ("has_ci",          "構成情報を持つ", "構成情報である"),
        ):
            try:
                await db.execute(
                    "INSERT OR IGNORE INTO relation_type (type_name, parent_label, child_label) VALUES (?,?,?)",
                    list(row),
                )
            except Exception:
                pass

        # ALTER TABLE additions for legacy DBs
        for stmt in (
            "ALTER TABLE user ADD COLUMN login_id TEXT",
            "ALTER TABLE user ADD COLUMN password_hash TEXT",
            "ALTER TABLE application ADD COLUMN app_category TEXT",
            "ALTER TABLE application ADD COLUMN portfolio_area INTEGER",
            "ALTER TABLE application ADD COLUMN migration_target_id TEXT",
            "ALTER TABLE application ADD COLUMN annual_cost_million INTEGER",
            "ALTER TABLE application ADD COLUMN is_infrastructure INTEGER DEFAULT 0",
            "ALTER TABLE application ADD COLUMN vendor TEXT",
            "ALTER TABLE apm_request ADD COLUMN app_category TEXT",
            "ALTER TABLE application_dependency ADD COLUMN migration_status TEXT DEFAULT 'not_planned'",
            "ALTER TABLE application_dependency ADD COLUMN migration_due_date DATE",
            "ALTER TABLE application_dependency ADD COLUMN migration_note TEXT",
            "ALTER TABLE demand ADD COLUMN score INTEGER",
            "ALTER TABLE demand ADD COLUMN investment_class TEXT",
            "ALTER TABLE demand ADD COLUMN capital_expense INTEGER",
            "ALTER TABLE demand ADD COLUMN operating_expense INTEGER",
            "ALTER TABLE demand ADD COLUMN financial_benefit INTEGER",
            "ALTER TABLE demand ADD COLUMN roi_percent REAL",
            "ALTER TABLE demand ADD COLUMN npv INTEGER",
            "ALTER TABLE demand ADD COLUMN irr REAL",
            "ALTER TABLE demand ADD COLUMN capital_budget INTEGER",
            "ALTER TABLE demand ADD COLUMN operating_budget INTEGER",
            "ALTER TABLE demand ADD COLUMN discount_rate REAL",
            "ALTER TABLE demand ADD COLUMN demand_actual_cost INTEGER",
            "ALTER TABLE project ADD COLUMN manager_user_id INTEGER",
            "ALTER TABLE project ADD COLUMN portfolio TEXT",
            "ALTER TABLE project ADD COLUMN description TEXT",
        ):
            try:
                await db.execute(stmt)
            except Exception:
                pass

        # ── Migration: environment.application_id → cmdb_rel_ci ──────────
        async with db.execute("PRAGMA table_info(environment)") as cur:
            env_col_names = [r[1] for r in await cur.fetchall()]

        if "application_id" in env_col_names:
            async with db.execute(
                "SELECT relation_type_id FROM relation_type WHERE type_name='has_environment'"
            ) as cur:
                row = await cur.fetchone()
                has_env_id = row[0] if row else 1

            # Migrate existing relationships before dropping the column
            await db.execute(
                """INSERT OR IGNORE INTO cmdb_rel_ci
                   (parent_table, parent_id, child_table, child_id, relation_type_id)
                   SELECT 'application', application_id,
                          'environment', CAST(environment_id AS TEXT), ?
                   FROM environment WHERE application_id IS NOT NULL""",
                [has_env_id],
            )
            # Recreate environment without application_id
            await db.execute(
                """CREATE TABLE IF NOT EXISTS environment_v2 (
                    environment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    env_type TEXT NOT NULL, location TEXT, ip TEXT,
                    host TEXT, os TEXT, middleware TEXT, cpu_mem TEXT, storage TEXT
                )"""
            )
            await db.execute(
                """INSERT INTO environment_v2
                   SELECT environment_id, env_type, location, ip, host, os, middleware, cpu_mem, storage
                   FROM environment"""
            )
            await db.execute("DROP TABLE environment")
            await db.execute("ALTER TABLE environment_v2 RENAME TO environment")

        # ── Migration: configuration_item.environment_id → cmdb_rel_ci ───
        async with db.execute("PRAGMA table_info(configuration_item)") as cur:
            ci_col_names = [r[1] for r in await cur.fetchall()]

        if "environment_id" in ci_col_names:
            async with db.execute(
                "SELECT relation_type_id FROM relation_type WHERE type_name='has_ci'"
            ) as cur:
                row = await cur.fetchone()
                has_ci_id = row[0] if row else 2

            # Migrate existing relationships before dropping the column
            await db.execute(
                """INSERT OR IGNORE INTO cmdb_rel_ci
                   (parent_table, parent_id, child_table, child_id, relation_type_id)
                   SELECT 'environment', CAST(environment_id AS TEXT),
                          'configuration_item', CAST(ci_id AS TEXT), ?
                   FROM configuration_item WHERE environment_id IS NOT NULL""",
                [has_ci_id],
            )
            # Recreate configuration_item without environment_id
            await db.execute(
                """CREATE TABLE IF NOT EXISTS ci_v2 (
                    ci_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ci_name TEXT NOT NULL, ci_type TEXT,
                    hostname TEXT, ip_address TEXT, bmc_ip TEXT,
                    os TEXT, os_version TEXT, cpu TEXT, memory TEXT, storage TEXT,
                    vendor TEXT, model TEXT,
                    status TEXT DEFAULT 'active', note TEXT
                )"""
            )
            await db.execute(
                """INSERT INTO ci_v2
                   SELECT ci_id, ci_name, ci_type, hostname, ip_address, bmc_ip,
                          os, os_version, cpu, memory, storage, vendor, model, status, note
                   FROM configuration_item"""
            )
            await db.execute("DROP TABLE configuration_item")
            await db.execute("ALTER TABLE ci_v2 RENAME TO configuration_item")

        await db.commit()
