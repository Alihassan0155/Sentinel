"""Opaque, revocable database sessions; passwords use salted scrypt."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.auth import Account, AuthAttempt, AuthSession

COOKIE = "sentinel_session"
router = APIRouter(prefix="/auth", tags=["Authentication"])


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"{salt}:{digest}"


def verify_password(password: str, encoded: str) -> bool:
    return hmac.compare_digest(password_hash(password, encoded.split(":")[0]), encoded)


DUMMY_HASH = password_hash("sentinel-dummy-password", "00" * 16)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf(request: Request):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("X-Sentinel-CSRF") != "1":
            raise HTTPException(403, "Missing CSRF protection header")
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in settings.frontend_origins.split(","):
            raise HTTPException(403, "Untrusted origin")


def current_account(request: Request, db: Session = Depends(get_db)) -> Account:
    csrf(request)
    token = request.cookies.get(COOKIE)
    session = db.get(AuthSession, token_hash(token)) if token else None
    if session is None or session.expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(401, "Please sign in")
    account = db.get(Account, session.account_id)
    if account is None:
        raise HTTPException(401, "Please sign in")
    return account


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if "@" not in value or "." not in value.rsplit("@", 1)[-1] or any(c.isspace() for c in value):
            raise ValueError("Enter a valid email address")
        return value


class Signup(Credentials):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value):
        if not value.strip():
            raise ValueError("Enter your name")
        return value.strip()


def public(account):
    return {"id": account.id, "email": account.email, "name": account.name}


def limit_attempts(request, db):
    # Shared across API processes, keyed by direct peer. Never trust arbitrary forwarded IPs.
    key = token_hash(request.client.host if request.client else "unknown")
    row = db.get(AuthAttempt, key, with_for_update=True)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if row is None:
        row = AuthAttempt(key=key, count=0, window_start=now)
        db.add(row)
    elif row.window_start < now - timedelta(minutes=15):
        row.count = 0
        row.window_start = now
    if row.count >= 30:
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
    row.count += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(429, "Please try again shortly")


def start_session(account, request, response, db):
    old = request.cookies.get(COOKIE)
    if old:
        session = db.get(AuthSession, token_hash(old))
        if session:
            db.delete(session)
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=token_hash(token), account_id=account.id,
                       expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)))
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, secure=settings.auth_cookie_secure,
                        samesite="lax", max_age=604800, path="/")
    response.headers["Cache-Control"] = "no-store"
    return public(account)


@router.post("/signup", status_code=201, dependencies=[Depends(csrf)])
def signup(data: Signup, request: Request, response: Response, db: Session = Depends(get_db)):
    limit_attempts(request, db)
    account = Account(email=data.email, name=data.name, password_hash=password_hash(data.password))
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists")
    return start_session(account, request, response, db)


@router.post("/login", dependencies=[Depends(csrf)])
def login(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    limit_attempts(request, db)
    account = db.query(Account).filter(Account.email == data.email).first()
    # Run the same expensive hash even for an unknown account.
    encoded = account.password_hash if account else DUMMY_HASH
    valid = verify_password(data.password, encoded)
    if account is None or not valid:
        raise HTTPException(401, "Incorrect email or password")
    return start_session(account, request, response, db)


@router.get("/me")
def me(response: Response, account: Account = Depends(current_account)):
    response.headers["Cache-Control"] = "no-store"
    return public(account)


@router.post("/logout", dependencies=[Depends(csrf)])
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    session = db.get(AuthSession, token_hash(token)) if token else None
    if session:
        db.delete(session)
        db.commit()
    response.delete_cookie(COOKIE, path="/", secure=settings.auth_cookie_secure, httponly=True, samesite="lax")
    return {"ok": True}
