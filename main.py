import asyncio
import importlib.util
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import init_db
from .routers import applications, environments, requests as req_router, auth, ci as ci_router, dashboard as dashboard_router, demand as demand_router, cmdb as cmdb_router

_SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "scripts", "seed.py")


def _run_seed():
    spec = importlib.util.spec_from_file_location("seed", os.path.abspath(_SEED_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.seed()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _run_seed)
    except Exception as e:
        print(f"[WARNING] Seed failed (non-fatal): {e}")
    yield


app = FastAPI(title="APM Portal API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(applications.router)
app.include_router(environments.router)
app.include_router(req_router.router)
app.include_router(ci_router.router)
app.include_router(dashboard_router.router)
app.include_router(demand_router.router)
app.include_router(cmdb_router.router)

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")
