import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import aiosqlite
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from ..database import get_db

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "apm-portal-dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    login_id: str
    password: str


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
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
    return dict(row)


@router.post("/login")
async def login(req: LoginRequest, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT * FROM user WHERE login_id = ?", [req.login_id]
    ) as cur:
        row = await cur.fetchone()

    if row is None or not row["password_hash"] or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ログインIDまたはパスワードが正しくありません",
        )

    token = create_access_token({
        "user_id": row["user_id"],
        "login_id": row["login_id"],
        "role": row["role"],
    })
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": row["user_id"],
        "user_name": row["user_name"],
        "role": row["role"],
    }
