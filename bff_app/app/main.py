import secrets
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Response, Depends, Cookie
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete

from app.config import settings
from app.session import engine, Base, get_db, AsyncSessionLocal
from app.models import BFFSession

logger = logging.getLogger(__name__)


async def periodic_session_cleanup():
    """Purge stale session rows from Postgres on a 1-hour interval."""
    while True:
        await asyncio.sleep(3600)
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    delete(BFFSession).where(BFFSession.expires_at < datetime.now(timezone.utc))
                )
                await session.commit()
                if result.rowcount > 0:
                    logger.info(f"Cleaned up {result.rowcount} expired BFF sessions")
        except Exception as e:
            logger.error(f"Error during periodic session cleanup: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database schema exists on boot and start background session pruner
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    cleanup_task = asyncio.create_task(periodic_session_cleanup())
    yield
    cleanup_task.cancel()
    await engine.dispose()


app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION, lifespan=lifespan)

# Required by Authlib to maintain transient state (PKCE verifier & nonce) during OIDC redirect
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    max_age=3600
)

# CORS setup for local web client development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Separate endpoints: FRONTEND_KC_URL is exposed to browser redirects; BACKEND_KC_URL is internal container traffic
FRONTEND_KC_URL = f"http://localhost:8180/realms/{settings.KEYCLOAK_REALM}"
BACKEND_KC_URL = f"http://keycloak:8080/realms/{settings.KEYCLOAK_REALM}"

oauth = OAuth()
oauth.register(
    name="keycloak",
    client_id=settings.KEYCLOAK_CLIENT_ID,
    client_secret=settings.KEYCLOAK_CLIENT_SECRET,
    authorize_url=f"{FRONTEND_KC_URL}/protocol/openid-connect/auth",
    access_token_url=f"{BACKEND_KC_URL}/protocol/openid-connect/token",
    jwks_uri=f"{BACKEND_KC_URL}/protocol/openid-connect/certs",
    client_kwargs={
        "scope": "openid profile email organization",
        "code_challenge_method": "S256"
    }
)


# Session Dependencies
async def get_current_session(
    bff_session_id: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db)
) -> BFFSession:
    """Strict session validation dependency. Rejects unauthenticated requests with 401."""
    if not bff_session_id:
        raise HTTPException(status_code=401, detail="Missing authentication session cookie")

    result = await db.execute(select(BFFSession).where(BFFSession.id == bff_session_id))
    db_session = result.scalars().first()

    if not db_session:
        raise HTTPException(status_code=401, detail="Session not found or invalid")

    if db_session.expires_at and db_session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        await db.delete(db_session)
        await db.commit()
        raise HTTPException(status_code=401, detail="Session expired")

    return db_session


async def get_optional_session(
    bff_session_id: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db)
) -> BFFSession | None:
    """Permissive session resolver for public endpoints that adapt based on login state."""
    if not bff_session_id:
        return None

    result = await db.execute(select(BFFSession).where(BFFSession.id == bff_session_id))
    db_session = result.scalars().first()

    if not db_session:
        return None

    if db_session.expires_at and db_session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        await db.delete(db_session)
        await db.commit()
        return None

    return db_session


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": settings.PROJECT_NAME}


@app.get("/auth/login")
async def login(request: Request):
    """Redirect browser to Keycloak authorization endpoint with PKCE challenge."""
    redirect_uri = "http://localhost:8001/auth/callback"
    return await oauth.keycloak.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback")
async def auth_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """Exchange OIDC authorization code for tokens and issue an HTTP-only session cookie."""
    try:
        token = await oauth.keycloak.authorize_access_token(request)
    except Exception as e:
        logger.error(f"Failed to exchange authorization code for tokens: {e}")
        raise HTTPException(status_code=400, detail=f"Authentication callback failed: {e}")

    user_info = token.get("userinfo")
    access_token_expires_in = token.get("expires_in", 300)
    session_lifetime = token.get("refresh_expires_in", 28800)

    session_id = secrets.token_urlsafe(32)
    db_session = BFFSession(
        id=session_id,
        access_token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
        id_token=token.get("id_token"),
        user_info=user_info,
        access_token_expires_at=datetime.now(timezone.utc) + timedelta(seconds=access_token_expires_in),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=session_lifetime)
    )
    db.add(db_session)
    await db.commit()

    # Drop temporary OAuth state cookie after successful token exchange
    request.session.clear()

    response = RedirectResponse(url="http://localhost:8080/")
    response.set_cookie(
        key="bff_session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True in production over HTTPS
        max_age=session_lifetime
    )
    return response


@app.get("/auth/me")
async def get_current_user(db_session: BFFSession | None = Depends(get_optional_session)):
    """Return identity claims and organization info for the active browser session."""
    if not db_session:
        return {"authenticated": False}

    user = db_session.user_info or {}
    org_claim = user.get("organization")
    if isinstance(org_claim, list) and len(org_claim) > 0:
        org_name = org_claim[0]
    elif isinstance(org_claim, str):
        org_name = org_claim
    else:
        org_name = "No Organization"

    return {
        "authenticated": True,
        "name": user.get("name", user.get("preferred_username", "Unknown User")),
        "email": user.get("email"),
        "organization": org_name,
        "raw_info": user
    }


@app.get("/auth/logout")
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    bff_session_id: str | None = Cookie(default=None)
):
    """Destroy local Postgres session and trigger Keycloak RP-Initiated Logout."""
    id_token = None
    if bff_session_id:
        result = await db.execute(select(BFFSession).where(BFFSession.id == bff_session_id))
        db_session = result.scalars().first()
        if db_session:
            id_token = db_session.id_token
            await db.delete(db_session)
            await db.commit()

    logout_url = f"{FRONTEND_KC_URL}/protocol/openid-connect/logout"
    if id_token:
        logout_url += f"?id_token_hint={id_token}&client_id={settings.KEYCLOAK_CLIENT_ID}&post_logout_redirect_uri=http://localhost:8080/"
    else:
        logout_url += f"?client_id={settings.KEYCLOAK_CLIENT_ID}&post_logout_redirect_uri=http://localhost:8080/"

    redirect_response = RedirectResponse(url=logout_url)
    redirect_response.delete_cookie("bff_session_id")
    return redirect_response


@app.get("/auth/debug/token")
async def debug_token(db_session: BFFSession = Depends(get_current_session)):
    """Inspection endpoint for checking raw token lifetimes during dev."""
    return {
        "session_id": db_session.id,
        "access_token": db_session.access_token,
        "refresh_token": db_session.refresh_token,
        "id_token": db_session.id_token,
        "access_token_expires_at": db_session.access_token_expires_at,
        "expires_at": db_session.expires_at,
        "user_info": db_session.user_info,
    }


async def ensure_fresh_token(db_session: BFFSession, db: AsyncSession) -> str:
    """Verify access token validity and refresh via Keycloak backchannel if near expiry."""
    if db_session.access_token_expires_at and \
       db_session.access_token_expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) + timedelta(seconds=30):
        return db_session.access_token

    if not db_session.refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing, re-authentication required")

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{BACKEND_KC_URL}/protocol/openid-connect/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": db_session.refresh_token,
                    "client_id": settings.KEYCLOAK_CLIENT_ID,
                    "client_secret": settings.KEYCLOAK_CLIENT_SECRET,
                }
            )
            if resp.status_code != 200:
                logger.warning(f"Keycloak refresh token request rejected with status {resp.status_code}")
                raise HTTPException(status_code=401, detail="Session expired, please log in again")

            new_tokens = resp.json()
            db_session.access_token = new_tokens["access_token"]
            db_session.refresh_token = new_tokens.get("refresh_token", db_session.refresh_token)
            db_session.access_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=new_tokens.get("expires_in", 300))
            await db.commit()
            return db_session.access_token
        except httpx.RequestError as e:
            logger.error(f"Unreachable Keycloak token endpoint during refresh: {e}")
            raise HTTPException(status_code=502, detail="Identity provider unavailable")


ALLOWED_PROXY_HEADERS = {"content-type", "accept", "accept-language", "accept-encoding"}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_to_downstream(
    path: str,
    request: Request,
    db_session: BFFSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db)
):
    """Reverse proxy gateway. Attaches Bearer token to requests forwarded to internal services."""
    # CSRF mitigation for unsafe methods when using cookie-based auth
    if request.method in ("POST", "PUT", "DELETE"):
        csrf_header = request.headers.get("x-requested-with")
        if csrf_header != "XMLHttpRequest":
            raise HTTPException(status_code=403, detail="CSRF validation failed: missing custom header")

    access_token = await ensure_fresh_token(db_session, db)
    target_url = f"{settings.PERMISSIONS_API_URL}/api/{path}"
    body = await request.body()

    headers = {k: v for k, v in request.headers.items() if k.lower() in ALLOWED_PROXY_HEADERS}
    headers["authorization"] = f"Bearer {access_token}"

    async with httpx.AsyncClient() as client:
        try:
            proxy_req = client.build_request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=request.query_params
            )
            response = await client.send(proxy_req)
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
        except httpx.RequestError as e:
            logger.error(f"Downstream service proxy failure for {target_url}: {e}")
            raise HTTPException(status_code=502, detail="Target microservice unreachable")
