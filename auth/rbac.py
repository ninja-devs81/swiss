"""
JWT-based authentication with bcrypt password hashing and cookie transport.
Tokens are stored in httponly cookies — no localStorage exposure.
"""
import datetime

import bcrypt
import jwt
from fastapi import Cookie, HTTPException, status

from config import settings

ALGORITHM = "HS256"


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(12)).decode()


def create_token(username: str, role: str) -> str:
    expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=settings.TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token abgelaufen")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiger Token")


def get_current_user(access_token: str = Cookie(None)) -> dict:
    """FastAPI dependency — extracts user from httponly cookie."""
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return decode_token(access_token)


def require_role(*roles: str):
    """Factory for role-gated dependency."""
    def _check(access_token: str = Cookie(None)):
        u = get_current_user(access_token)
        if u.get("role") not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Zugriff verweigert")
        return u
    return _check


def authenticate_user(username: str, password: str) -> dict | None:
    for u in settings.users:
        if u["username"] == username and verify_password(password, u["password"]):
            return u
    return None
