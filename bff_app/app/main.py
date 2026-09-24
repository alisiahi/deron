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
    """Background task purging expired sessions from Postgres every hour."""
    while True:
        await asyncio.sleep(3600)
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    delete(BFFSession).where(BFFSession.expires_at < datetime.now(timezone.utc))
                )
                await session.commit()
                logger.info(f"Session cleanup: purged {result.rowcount} expired sessions")
        except Exception as e:
            logger.error(f"Session cleanup failed: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    cleanup_task = asyncio.create_task(periodic_session_cleanup())
    yield
    cleanup_task.cancel()
    await engine.dispose()

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION, lifespan=lifespan)

# Starlette SessionMiddleware for Authlib temporary login state (PKCE verifier)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    max_age=3600
)

# CORS middleware for Flutter Web & dev servers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Keycloak URLs
FRONTEND_KC_URL = f"http://localhost:8180/realms/{settings.KEYCLOAK_REALM}"
BACKEND_KC_URL = f"http://keycloak:8080/realms/{settings.KEYCLOAK_REALM}"

# Initialize Authlib OAuth
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


# --- Dependencies to validate custom DB-backed session ---
async def get_current_session(
    bff_session_id: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db)
) -> BFFSession:
    if not bff_session_id:
        raise HTTPException(status_code=401, detail="No session cookie provided")
    
    result = await db.execute(select(BFFSession).where(BFFSession.id == bff_session_id))
    db_session = result.scalars().first()
    
    if not db_session:
        raise HTTPException(status_code=401, detail="Invalid session")
        
    if db_session.expires_at and db_session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        await db.delete(db_session)
        await db.commit()
        raise HTTPException(status_code=401, detail="Session expired")
        
    return db_session


async def get_optional_session(
    bff_session_id: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db)
) -> BFFSession | None:
    """Same as get_current_session, but returns None instead of raising 401"""
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
    """Initiates OIDC Login Flow with Keycloak"""
    redirect_uri = "http://localhost:8001/auth/callback"
    return await oauth.keycloak.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback")
async def auth_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """Handles callback, exchanges code for tokens, and creates Postgres DB session"""
    try:
        token = await oauth.keycloak.authorize_access_token(request)
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise HTTPException(status_code=400, detail=f"Authentication failed: {e}")

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

    # Clear temporary Authlib PKCE state cookie
    request.session.clear()

    # Redirect browser back to Flutter Web
    response = RedirectResponse(url="http://localhost:8080/")

    response.set_cookie(
        key="bff_session_id",
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=session_lifetime
    )
    return response


@app.get("/auth/me")
async def get_current_user(db_session: BFFSession | None = Depends(get_optional_session)):
    """Flutter Web calls this to know who is logged in"""
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
    """Clears Postgres DB session and redirects to Keycloak logout endpoint"""
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
    """Debug endpoint to inspect full raw token structure"""
    return {
        "session_id": db_session.id,
        "access_token": db_session.access_token,
        "refresh_token": db_session.refresh_token,
        "id_token": db_session.id_token,
        "access_token_expires_at": db_session.access_token_expires_at,
        "expires_at": db_session.expires_at,
        "user_info": db_session.user_info,
    }


# --- Token Refresh ---
async def ensure_fresh_token(db_session: BFFSession, db: AsyncSession) -> str:
    """Refreshes access token if expired or expiring within 30s."""
    if db_session.access_token_expires_at and \
       db_session.access_token_expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) + timedelta(seconds=30):
        return db_session.access_token

    if not db_session.refresh_token:
        raise HTTPException(status_code=401, detail="Session expired, please log in again")

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
                logger.warning(f"Token refresh failed with status {resp.status_code}")
                raise HTTPException(status_code=401, detail="Session expired, please log in again")

            new_tokens = resp.json()
            db_session.access_token = new_tokens["access_token"]
            db_session.refresh_token = new_tokens.get("refresh_token", db_session.refresh_token)
            db_session.access_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=new_tokens.get("expires_in", 300))
            await db.commit()
            return db_session.access_token
        except httpx.RequestError as e:
            logger.error(f"Failed to reach Keycloak for token refresh: {e}")
            raise HTTPException(status_code=502, detail="Authentication service unavailable")


ALLOWED_PROXY_HEADERS = {"content-type", "accept", "accept-language", "accept-encoding"}


# --- Downstream Reverse Proxy / API Gateway ---
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_to_downstream(
    path: str,
    request: Request,
    db_session: BFFSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db)
):
    """
    Intercepts /api/* requests from Flutter Web, retrieves Bearer token from Postgres
    using the bff_session_id cookie, refreshes if needed, and forwards to permissions_app.
    """
    if request.method in ("POST", "PUT", "DELETE"):
        csrf_header = request.headers.get("x-requested-with")
        if csrf_header != "XMLHttpRequest":
            raise HTTPException(status_code=403, detail="CSRF validation failed")

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
            logger.error(f"Proxy error to {target_url}: {e}")
            raise HTTPException(status_code=502, detail="Downstream service unavailable")
