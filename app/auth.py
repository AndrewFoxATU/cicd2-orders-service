# orders_service/auth.py
# Verifies user JWTs on incoming requests and mints short-lived "service"
# tokens for calls to the tyres/users services. All services share JWT_SECRET.
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
SERVICE_TOKEN_EXPIRE_MINUTES = 5


class TokenUser(BaseModel):
    id: Optional[int] = None
    name: str
    role: str


_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> TokenUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenUser(
        id=payload.get("user_id"),
        name=payload.get("name", ""),
        role=payload.get("role", ""),
    )


def require_roles(*roles: str):
    def dependency(user: TokenUser = Depends(get_current_user)) -> TokenUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return dependency


def create_service_token() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "orders-service",
        "user_id": None,
        "name": "orders-service",
        "role": "service",
        "iat": now,
        "exp": now + timedelta(minutes=SERVICE_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def service_auth_headers() -> dict:
    return {"Authorization": f"Bearer {create_service_token()}"}
