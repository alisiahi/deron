# Deron Project — Kiwi App IAM Architecture Guide

A complete, production-grade reference implementation for Identity & Access Management (IAM) and Backend-for-Frontend (BFF) security pattern using **Flutter Web**, **FastAPI**, **Keycloak**, and **PostgreSQL**.

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Component Breakdown](#component-breakdown)
3. [How to Run Locally (Quickstart)](#how-to-run-locally-quickstart)
4. [Keycloak Setup — Local Development](#keycloak-setup--local-development)
5. [Production Deployment Guide](#production-deployment-guide)
6. [Keycloak Setup — Production](#keycloak-setup--production)
7. [Updating Client Secret in Running Containers](#updating-client-secret-in-running-containers)
8. [How the Auth & Session Flow Works](#how-the-auth--session-flow-works)
9. [Multi-VM Production Architecture Guide](#multi-vm-production-architecture-guide)
10. [Connecting Other FastAPI Microservices to the BFF](#connecting-other-fastapi-microservices-to-the-bff)
11. [Integrating Auth into the Existing Flutter Web Production App](#integrating-auth-into-the-existing-flutter-web-production-app)
12. [Security Best Practices](#security-best-practices)

---

## Architecture Overview

In a modern enterprise web application with multiple microservices, storing access tokens (JWTs) in browser storage (like `localStorage` or `sessionStorage`) exposes the application to **Cross-Site Scripting (XSS)** token theft.

The **Backend-for-Frontend (BFF)** pattern eliminates this vulnerability by keeping raw JWTs entirely on the server. The browser only receives an **opaque, HTTP-only, SameSite session cookie**. The BFF intercepts API calls from the browser, retrieves the corresponding JWT from PostgreSQL, refreshes it if needed, and forwards it to downstream microservices in an `Authorization: Bearer <token>` header.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     LOCAL / SINGLE VM                                       │
│                                                                                             │
│  ┌──────────────────┐               ┌──────────────────┐               ┌─────────────────┐  │
│  │   Flutter Web    │  Cookie Auth  │     BFF App      │  Bearer Token │ Permissions App │  │
│  │    (Frontend)    │──────────────>│    (FastAPI)     │──────────────>│   (FastAPI)     │  │
│  │   Port: 8080     │               │    Port: 8001    │               │   Port: 8000    │  │
│  └──────────────────┘               └────────┬─────────┘               └────────┬────────┘  │
│                                              │                                  │           │
│                                    Token / JWKS Verification             JWKS Public Key    │
│                                              │                                  │           │
│                                              ▼                                  ▼           │
│                                     ┌──────────────────┐               ┌─────────────────┐  │
│                                     │     Keycloak     │               │   PostgreSQL    │  │
│                                     │  (Port 8180/8080)│               │   (Port 5432)   │  │
│                                     └──────────────────┘               └─────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. `flutter_web` (Frontend)
- **Framework**: Flutter Web 3.27+ with Dart 3.6+
- **State Management**: `provider` (`AuthProvider`)
- **Routing**: `go_router` (`appRouter`)
- **Role**: Renders UI, handles browser redirection for login/logout, and sends requests to the BFF using `BrowserClient(withCredentials = true)`. It **never** sees or stores access/refresh tokens.

### 2. `bff_app` (Backend-for-Frontend & API Gateway)
- **Framework**: FastAPI (Python 3.12) with Authlib OAuth client & SQLAlchemy Async
- **Role**:
  - Initiates OIDC Authorization Code Flow with PKCE (`S256`).
  - Exchanges authorization code for Keycloak access, refresh, and ID tokens.
  - Stores token data securely in PostgreSQL (`bff_sessions` table).
  - Sets HTTP-only `bff_session_id` cookie.
  - Verifies user authentication status (`/auth/me`).
  - Automatically refreshes access tokens using refresh tokens when expired.
  - Proxies `/api/*` requests to downstream FastAPI services while attaching `Authorization: Bearer <access_token>`.
  - Enforces CSRF header validation (`X-Requested-With: XMLHttpRequest`) for POST/PUT/DELETE requests.

### 3. `permissions_app` (Downstream Microservice)
- **Framework**: FastAPI (Python 3.12)
- **Role**: Represents a business microservice (e.g. `kiwi-backend-drone-permissions-v2`).
  - Contains no session logic.
  - Validates incoming `Authorization: Bearer <token>` headers cryptographically using Keycloak's public keys (`JWKS_URL`).
  - Checks role-based access control (RBAC) like organization claims (`adminsop` / `adminops`).

### 4. `Keycloak` (Identity Provider)
- **Version**: Keycloak 26.7.0
- **Role**: Centralized identity and access management server. Authenticates users, issues OIDC JWT tokens, and exposes JWKS endpoints for public key verification.

### 5. `PostgreSQL` (Database)
- **Version**: PostgreSQL 16 Alpine
- **Role**: Stores BFF session records (`bff_sessions`) and business data (`permission_requests`).

---

## How to Run Locally (Quickstart)

### Prerequisites
- Docker & Docker Compose installed
- Flutter SDK / FVM installed (`fvm flutter`)

### Step 1: Start the Backend Stack
From the project root directory:
```bash
docker compose up -d --build
```
Verify that all 4 containers are running:
- PostgreSQL: `localhost:5432`
- Permissions API: `http://localhost:8000/health`
- BFF App: `http://localhost:8001/health`
- Keycloak: `http://localhost:8180`

### Step 2: Configure Keycloak
Follow the [Keycloak Setup — Local Development](#keycloak-setup--local-development) section below.

### Step 3: Update the Client Secret
After creating the client in Keycloak, copy the **Client Secret** from the Credentials tab and paste it into `docker-compose.yml` under the `bff_app` service:
```yaml
bff_app:
  environment:
    - KEYCLOAK_CLIENT_SECRET=<paste-your-secret-here>
```
Then recreate the BFF container to pick up the new secret:
```bash
docker compose up -d bff_app
```

### Step 4: Run Flutter Web
```bash
cd flutter_web
fvm flutter run -d chrome --web-port=8080
```
Open **`http://localhost:8080`** in Google Chrome.

---

## Keycloak Setup — Local Development

### Accessing the Admin Dashboard
- **URL**: `http://localhost:8180`
- **Credentials**: `admin` / `admin`

### Step 1: Create the Realm
1. Click the realm dropdown (top-left) → **Create Realm**
2. **Realm Name**: `deron-realm`
3. Click **Create**

### Step 2: Create the Client

Go to **Clients** → **Create client**.

**General Settings tab:**

| Field | Value |
|---|---|
| **Client type** | OpenID Connect |
| **Client ID** | `deron-bff` |

Click **Next**.

**Capability Config tab:**

| Field | Value |
|---|---|
| **Client Authentication** | **ON** |
| **Authorization** | **OFF** |
| **Authentication flow** | ☑ Standard flow (check), uncheck all others |

Click **Next**.

**Login Settings tab:**

> ⚠️ **IMPORTANT**: The **Valid redirect URIs** must point to the **BFF app on port `8001`**, NOT the Flutter frontend on port `8080`. This is because Keycloak redirects back to the BFF (which handles the OAuth callback), not to the Flutter frontend directly. Make sure you type the full URL including the `http://` prefix — a common mistake is to accidentally cut off the `h` when pasting.

| Field | Value | Why |
|---|---|---|
| **Root URL** | `http://localhost:8080` | The Flutter frontend base URL |
| **Home URL** | `http://localhost:8080/` | Landing page after Keycloak actions |
| **Valid redirect URIs** | `http://localhost:8001/auth/callback` | The BFF callback endpoint (**port 8001**, not 8080!) |
| *(add another)* | `http://localhost:8001/*` | Wildcard fallback for the BFF |
| **Valid post logout redirect URIs** | `http://localhost:8080/*` | Where the browser goes after logout (back to Flutter frontend) |
| **Web origins** | `+` | Automatically allows CORS from redirect URI origins |

Click **Save**.

### Step 3: Enable PKCE

After saving, go to the **Advanced** tab of the client:

| Field | Value |
|---|---|
| **Proof Key for Code Exchange Code Challenge Method** | `S256` |

Click **Save**.

### Step 4: Copy the Client Secret
Go to the **Credentials** tab → copy the **Client Secret**.

Paste it into `docker-compose.yml` under the `bff_app` environment:
```yaml
bff_app:
  environment:
    - KEYCLOAK_CLIENT_SECRET=<paste-your-secret-here>
```
Then restart the BFF:
```bash
docker compose up -d bff_app
```

### Step 5: Create a Test User
1. Go to **Users** → **Add user**
2. **Username**: `testuser` (fill in email, first/last name as desired)
3. Click **Create**
4. Go to the **Credentials** tab → **Set password**
5. Enter a password and turn **OFF** the **Temporary** toggle
6. Click **Save**

### Step 6 (Optional): Create an Organization
1. Go to **Organizations** → **Create organization**
2. **Name**: `adminsop`
3. Click **Create**
4. Go to the **Members** tab → **Add member** → select your test user

---

## Production Deployment Guide

**Production URL**: `https://rlab-drone-establish.egov.uni-koblenz.de`

The production stack uses `docker-compose.prod.yml`, which runs all services behind an Nginx reverse proxy with HTTPS. In production, all services (Flutter frontend, BFF, Keycloak) are accessed through the **same domain** — Nginx routes requests to the correct container based on the URL path:

| Path | Routed to | Purpose |
|---|---|---|
| `/` | Flutter Web (static files) | Frontend |
| `/auth/*` | `bff_app:8001` | BFF authentication endpoints |
| `/api/*` | `bff_app:8001` | BFF API gateway |
| `/kc/*` | `keycloak:8080` | Keycloak identity provider |

### Step 1: Push the Code to the VM

From your local machine, sync the project to the VM using `rsync`:
```bash
rsync -avz --exclude='.git' --exclude='node_modules' --exclude='.dart_tool' --exclude='build' \
  /home/yaqoosh/Music/deron/ vm-drone:~/deron/
```

### Step 2: Build and Start Everything on the VM

SSH into the VM:
```bash
ssh vm-drone
```

Navigate to the project directory and build all containers:
```bash
cd ~/deron
docker compose -f docker-compose.prod.yml up -d --build
```

At this point, Keycloak will be running at `https://rlab-drone-establish.egov.uni-koblenz.de/kc/` and ready for configuration.

### Step 3: Configure Keycloak on the VM
Follow the [Keycloak Setup — Production](#keycloak-setup--production) section below to create the realm and client in the production Keycloak dashboard.

### Step 4: Copy the Client Secret into docker-compose.prod.yml

After creating the client in the Keycloak dashboard, copy the **Client Secret** from the **Credentials** tab. Then edit `docker-compose.prod.yml` on the VM and paste it:
```bash
nano ~/deron/docker-compose.prod.yml
```
Find the `bff_app` service and update:
```yaml
bff_app:
  environment:
    - KEYCLOAK_CLIENT_SECRET=<paste-your-production-secret-here>
```

### Step 5: Rebuild the BFF with the New Secret

Recreate only the BFF container so it picks up the new secret:
```bash
docker compose -f docker-compose.prod.yml up -d bff_app
```

### Rebuilding After Code Changes

When you make code changes locally and want to redeploy:
```bash
# 1. From your local machine — push updated code to the VM
rsync -avz --exclude='.git' --exclude='node_modules' --exclude='.dart_tool' --exclude='build' \
  /home/yaqoosh/Music/deron/ vm-drone:~/deron/

# 2. SSH into the VM
ssh vm-drone

# 3. Rebuild and restart all containers
cd ~/deron
docker compose -f docker-compose.prod.yml up -d --build

# Or rebuild only specific services (e.g. just the BFF and frontend):
docker compose -f docker-compose.prod.yml up -d --build bff_app frontend
```

### Viewing Logs on the VM

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f bff_app
```

---

## Keycloak Setup — Production

### Accessing the Admin Dashboard
- **URL**: `https://rlab-drone-establish.egov.uni-koblenz.de/kc/admin/`
- **Credentials**: `admin` / `admin` *(change these immediately in production!)*

### Step 1: Create the Realm
1. Click the realm dropdown (top-left) → **Create Realm**
2. **Realm Name**: `deron-realm`
3. Click **Create**

### Step 2: Create the Client

Go to **Clients** → **Create client**.

**General Settings tab:**

| Field | Value |
|---|---|
| **Client type** | OpenID Connect |
| **Client ID** | `deron-bff` |

Click **Next**.

**Capability Config tab:**

| Field | Value |
|---|---|
| **Client Authentication** | **ON** |
| **Authorization** | **OFF** |
| **Authentication flow** | ☑ Standard flow (check), uncheck all others |

Click **Next**.

**Login Settings tab:**

> ⚠️ **IMPORTANT**: In production, Nginx proxies everything under the same domain. So unlike local development (where the BFF is on a different port), in production **all redirect URIs use the same base URL** `https://rlab-drone-establish.egov.uni-koblenz.de`. Make sure you type the full URLs including `https://` — do not accidentally cut off any characters when pasting.

| Field | Value | Why |
|---|---|---|
| **Root URL** | `https://rlab-drone-establish.egov.uni-koblenz.de` | The production domain |
| **Home URL** | `https://rlab-drone-establish.egov.uni-koblenz.de/` | Landing page |
| **Valid redirect URIs** | `https://rlab-drone-establish.egov.uni-koblenz.de/auth/callback` | The BFF callback (proxied via Nginx `/auth/`) |
| *(add another)* | `https://rlab-drone-establish.egov.uni-koblenz.de/*` | Wildcard fallback |
| **Valid post logout redirect URIs** | `https://rlab-drone-establish.egov.uni-koblenz.de/*` | Where the browser goes after logout |
| **Web origins** | `+` | Automatically allows CORS from redirect URI origins |

Click **Save**.

### Step 3: Enable PKCE

After saving, go to the **Advanced** tab of the client:

| Field | Value |
|---|---|
| **Proof Key for Code Exchange Code Challenge Method** | `S256` |

Click **Save**.

### Step 4: Copy the Client Secret
Go to the **Credentials** tab → copy the **Client Secret**.

Then follow [Production Deployment Guide — Step 4](#step-4-copy-the-client-secret-into-docker-composeprodyml) to paste it into `docker-compose.prod.yml` and restart the BFF.

### Step 5: Create Users and Organizations
1. Go to **Users** → **Add user** → create your production users
2. Set passwords under the **Credentials** tab (turn off **Temporary**)
3. (Optional) Go to **Organizations** → create `adminsop` → assign users

---

## Updating Client Secret in Running Containers

If you regenerate or change the Client Secret in the Keycloak Admin Dashboard, update the running BFF container without needing a full rebuild:

### In Local Development:
1. Update `KEYCLOAK_CLIENT_SECRET` in `docker-compose.yml` (under `bff_app` environment variables).
2. Recreate the BFF container:
   ```bash
   docker compose up -d bff_app
   ```

### In Production (VM):
1. SSH into the VM: `ssh vm-drone`
2. Update `KEYCLOAK_CLIENT_SECRET` in `docker-compose.prod.yml` (under `bff_app` environment variables).
3. Recreate the BFF container:
   ```bash
   docker compose -f docker-compose.prod.yml up -d bff_app
   ```

---

## How the Auth & Session Flow Works

### Login Flow
```
User clicks "Login with Keycloak" in Flutter Web
  └─> Browser navigates to <DOMAIN>/auth/login
       └─> BFF generates PKCE code_challenge (S256) and stores verifier in temporary session cookie
            └─> Browser redirected to Keycloak login page (<DOMAIN>/kc/realms/deron-realm/...)
                 └─> User logs in
                      └─> Keycloak redirects browser to BFF callback: <DOMAIN>/auth/callback?code=XYZ
                           └─> BFF exchanges authorization code for tokens via backchannel (http://keycloak:8080/...)
                                └─> BFF generates opaque session_id and saves tokens + userinfo into PostgreSQL
                                     └─> BFF sets HTTP-only `bff_session_id` cookie
                                          └─> Browser redirected to Flutter Web: <DOMAIN>/
```

### Authenticated Request Flow
```
Flutter Web makes API call: POST <DOMAIN>/api/v1/permissions/
  └─> Browser automatically includes `bff_session_id` cookie
       └─> BFF looks up `bff_session_id` in PostgreSQL (`bff_sessions` table)
            └─> BFF checks token expiration (auto-refreshes via Keycloak if expired)
                 └─> BFF attaches `Authorization: Bearer <access_token>`
                      └─> BFF forwards request to Permissions API (http://permissions_app:8000/api/v1/permissions/)
                           └─> Permissions API verifies JWT signature via Keycloak JWKS endpoint
                                └─> Permissions API executes logic and returns JSON to BFF
                                     └─> BFF returns JSON to Flutter Web
```

### Logout Flow
```
User clicks "Logout" in Flutter Web
  └─> Browser navigates to <DOMAIN>/auth/logout
       └─> BFF deletes session row from PostgreSQL
            └─> BFF clears `bff_session_id` cookie
                 └─> BFF redirects browser to Keycloak logout URL (with id_token_hint)
                      └─> Keycloak revokes SSO session
                           └─> Browser redirected back to Flutter Web (<DOMAIN>/)
```

---

## Multi-VM Production Architecture Guide

In production at the university, services are distributed across **3 or more Virtual Machines (VMs)**:

```
┌─────────────────────────┐      ┌─────────────────────────┐      ┌─────────────────────────┐
│          VM 1           │      │          VM 2           │      │          VM 3           │
│  Keycloak Identity Server│      │   PostgreSQL Database   │      │   BFF + Microservices   │
│ (kc.kiwi.uni-koblenz.de)│      │(db.kiwi.internal:5432)  │      │(api.kiwi.uni-koblenz.de)│
└─────────────────────────┘      └─────────────────────────┘      └─────────────────────────┘
```

### Configuring Environment Variables for Multi-VM

#### 1. In `docker-compose.prod.yml` (or your chosen environment configuration):
```env
# Keycloak Configuration
# Public URL used by browser redirects
KEYCLOAK_SERVER_URL=https://rlab-drone-establish.egov.uni-koblenz.de/kc
# Internal IP / hostname for BFF backchannel token exchange (example: Docker network hostname)
KEYCLOAK_INTERNAL_URL=http://keycloak:8080/kc

KEYCLOAK_REALM=deron-realm
KEYCLOAK_CLIENT_ID=deron-bff
KEYCLOAK_CLIENT_SECRET=prod_secret_here

# PostgreSQL Connection String
DATABASE_URL=postgresql+asyncpg://postgres:postgrespassword@db:5432/drone_db

# Downstream Microservices URLs (internal Docker network or cluster IPs)
PERMISSIONS_API_URL=http://permissions_app:8000
```

#### 2. Dual Keycloak URLs in BFF Code (`bff_app/app/main.py`):
In production, the browser reaches Keycloak over HTTPS (`https://rlab-drone-establish.egov.uni-koblenz.de/kc`), while the BFF talks to Keycloak over the internal Docker network (`http://keycloak:8080/kc`):

```python
FRONTEND_KC_URL = "https://rlab-drone-establish.egov.uni-koblenz.de/kc/realms/deron-realm"
BACKEND_KC_URL = "http://keycloak:8080/kc/realms/deron-realm"

oauth.register(
    name="keycloak",
    client_id=settings.KEYCLOAK_CLIENT_ID,
    client_secret=settings.KEYCLOAK_CLIENT_SECRET,
    authorize_url=f"{FRONTEND_KC_URL}/protocol/openid-connect/auth",
    access_token_url=f"{BACKEND_KC_URL}/protocol/openid-connect/token",
    jwks_uri=f"{BACKEND_KC_URL}/protocol/openid-connect/certs",
    ...
)
```

#### 3. In Downstream Microservices (`permissions_app/app/security.py`):
Downstream APIs need Keycloak's public keys to cryptographically verify incoming Bearer tokens:

```python
KEYCLOAK_ISSUER_URL = "https://rlab-drone-establish.egov.uni-koblenz.de/kc/realms/deron-realm"
KEYCLOAK_INTERNAL_URL = "http://keycloak:8080/kc/realms/deron-realm"
JWKS_URL = f"{KEYCLOAK_INTERNAL_URL}/protocol/openid-connect/certs"

jwks_client = PyJWKClient(JWKS_URL)
```

---

## Connecting Other FastAPI Microservices to the BFF

The university project has 5 FastAPI backend repositories (`kiwi-backend-cost-calculator-v2`, `kiwi-backend-digital-cellar-v2`, `kiwi-backend-fertilization-v2`, etc.).

To connect any new microservice to this BFF:

### Step 1: Add Security Verification to the Microservice
Copy `permissions_app/app/security.py` into the microservice repo. Add `token_payload: dict = Depends(verify_token)` to any protected endpoint:

```python
from app.security import verify_token

@router.get("/cost/summary")
async def get_cost_summary(token_payload: dict = Depends(verify_token)):
    user_email = token_payload.get("email")
    return {"cost": 42.0, "user": user_email}
```

### Step 2: Add Proxy Route in BFF (`bff_app/app/main.py`)
Add routing prefixes in BFF to proxy requests to the appropriate downstream service:

```python
@app.api_route("/api/cost-calculator/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_to_cost_calculator(
    path: str,
    request: Request,
    db_session: BFFSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db)
):
    return await forward_request(
        target_base_url=settings.COST_CALCULATOR_API_URL,
        path=path,
        request=request,
        db_session=db_session,
        db=db
    )
```

---

## Integrating Auth into the Existing Flutter Web Production App

When bringing this logic into the main repository (`kiwi-frontend-v2`):

### 1. Copy the Auth Service & Provider
Copy the following files into `kiwi-frontend-v2`:
- `lib/models/user.dart`
- `lib/services/auth_service.dart`
- `lib/providers/auth_provider.dart`

### 2. Wrap `main.dart` with Provider
```dart
void main() {
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthProvider()),
      ],
      child: const KiwiApp(),
    ),
  );
}
```

### 3. Trigger Login / Logout
- **Login Button**: `context.read<AuthProvider>().login();` (triggers `html.window.location.href = 'http://bff-url/auth/login'`).
- **Logout Button**: `context.read<AuthProvider>().logout();` (triggers `html.window.location.href = 'http://bff-url/auth/logout'`).

### 4. Making Authenticated Requests in Flutter Web
For any API call from Flutter Web to the BFF, always use `BrowserClient` with credentials enabled and pass the CSRF header for state-changing methods:

```dart
import 'package:http/browser_client.dart';
import 'package:flutter/foundation.dart';

http.Client createHttpClient() {
  if (kIsWeb) {
    final client = BrowserClient();
    client.withCredentials = true; // CRITICAL for sending bff_session_id cookie!
    return client;
  }
  return http.Client();
}

// POST request example
final client = createHttpClient();
final response = await client.post(
  Uri.parse('https://rlab-drone-establish.egov.uni-koblenz.de/api/v1/permissions/'),
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest', // CSRF protection
  },
  body: jsonEncode(data),
);
```

---

## Security Best Practices

1. **HTTP-Only Cookies**: The `bff_session_id` cookie is set with `httponly=True`. JavaScript running in the browser (including malicious XSS scripts) **cannot read the session ID**.
2. **SameSite Lax / Strict**: Prevents Cross-Site Request Forgery (CSRF).
3. **CSRF Custom Header**: All POST/PUT/DELETE requests in BFF require `X-Requested-With: XMLHttpRequest`. Standard HTML forms or malicious cross-site images cannot produce custom headers without preflight CORS checks.
4. **Token Isolation**: Access tokens and refresh tokens are stored in PostgreSQL and never sent to the browser.
5. **Periodic Session Cleanup**: The BFF runs an async background loop every hour to purge expired session rows from PostgreSQL (`delete(BFFSession).where(BFFSession.expires_at < now)`).
