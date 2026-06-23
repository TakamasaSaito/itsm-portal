import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import aiosqlite
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from database import get_db

SECRET_KEY = os.getenv("SECRET_KEY", "itsm-portal-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer()

router = APIRouter(prefix="/api/itsm/auth", tags=["auth"])


async def _resolve_group_id(db: aiosqlite.Connection, user: dict):
    """group_leader→leaderロールのgroup_id、member→memberロールのgroup_idを返す。それ以外はNone。"""
    role = user["role"]
    if role not in ("group_leader", "member"):
        return None
    gm_role = "leader" if role == "group_leader" else "member"
    async with db.execute(
        "SELECT group_id FROM group_member WHERE user_id = ? AND role = ? ORDER BY group_id LIMIT 1",
        [user["user_id"], gm_role],
    ) as cur:
        gm = await cur.fetchone()
    return gm["group_id"] if gm else None


class LoginRequest(BaseModel):
    username: str
    password: str


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    async with db.execute("SELECT * FROM user WHERE user_id = ?", [user_id]) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="User not found")
    user_dict = dict(row)
    user_dict["group_id"] = await _resolve_group_id(db, user_dict)
    return user_dict


@router.post("/login")
async def login(req: LoginRequest, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT * FROM user WHERE username = ?", [req.username]
    ) as cur:
        row = await cur.fetchone()

    if row is None or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザー名またはパスワードが正しくありません",
        )

    token = create_access_token({
        "user_id": row["user_id"],
        "username": row["username"],
        "role": row["role"],
    })
    group_id = await _resolve_group_id(db, dict(row))
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": row["user_id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
        "group_id": group_id,
    }


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {
        "user_id": current_user["user_id"],
        "username": current_user["username"],
        "full_name": current_user["full_name"],
        "email": current_user["email"],
        "role": current_user["role"],
        "department_id": current_user["department_id"],
    }
