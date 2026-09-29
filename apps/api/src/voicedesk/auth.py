import secrets
from datetime import timedelta
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, WebSocket, status
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from voicedesk.config import get_settings
from voicedesk.db import get_db
from voicedesk.models import AuthSession, User, utcnow

_hasher = PasswordHasher()
COOKIE_NAME = "voicedesk_session"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def serializer() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().app_secret_key, salt="voicedesk-session-v1")


def create_auth_session(db: Session, user: User, response: Response) -> AuthSession:
    settings = get_settings()
    auth_session = AuthSession(
        id=str(uuid4()), user_id=user.id, csrf_token=secrets.token_urlsafe(32),
        expires_at=utcnow() + timedelta(hours=12),
    )
    db.add(auth_session)
    db.commit()
    response.set_cookie(
        COOKIE_NAME, serializer().dumps(auth_session.id), httponly=True,
        secure=settings.cookie_secure, samesite="lax", max_age=12 * 3600,
        domain=settings.cookie_domain, path="/",
    )
    return auth_session


def _get_auth_session(db: Session, cookie: str | None) -> tuple[AuthSession, User] | None:
    if not cookie:
        return None
    try:
        session_id = serializer().loads(cookie)
    except BadSignature:
        return None
    auth_session = db.get(AuthSession, session_id)
    if not auth_session or auth_session.revoked_at or auth_session.expires_at.replace(tzinfo=None) < utcnow().replace(tzinfo=None):
        return None
    user = db.get(User, auth_session.user_id)
    if not user or not user.active:
        return None
    return auth_session, user


def current_auth(request: Request, db: Session = Depends(get_db)) -> tuple[AuthSession, User]:
    result = _get_auth_session(db, request.cookies.get(COOKIE_NAME))
    if not result:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in is required.")
    return result


def current_user(auth: tuple[AuthSession, User] = Depends(current_auth)) -> User:
    return auth[1]


def mutation_user(request: Request, auth: tuple[AuthSession, User] = Depends(current_auth)) -> User:
    auth_session, user = auth
    if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), auth_session.csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token.")
    return user


def operator_user(user: User = Depends(mutation_user)) -> User:
    if user.role not in {"operator", "admin"}:
        raise HTTPException(status_code=403, detail="Operator access is required.")
    return user


def websocket_user(websocket: WebSocket, db: Session) -> User | None:
    origin = websocket.headers.get("origin")
    allowed = {item.strip() for item in get_settings().cors_origins.split(",")}
    if origin and origin not in allowed:
        return None
    auth = _get_auth_session(db, websocket.cookies.get(COOKIE_NAME))
    return auth[1] if auth else None


def user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower().strip()))
