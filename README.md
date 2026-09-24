# Deron Project — Kiwi App IAM Architecture Guide

A complete, production-grade reference implementation for Identity & Access Management (IAM) and Backend-for-Frontend (BFF) security pattern using **Flutter Web**, **FastAPI**, **Keycloak**, and **PostgreSQL**.

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Component Breakdown](#component-breakdown)
3. [How to Run Locally (Quickstart)](#how-to-run-locally-quickstart)
4. [Keycloak Setup Instructions](#keycloak-setup-instructions)
5. [Updating Client Secret in Running Containers](#updating-client-secret-in-running-containers)
6. [How the Auth & Session Flow Works](#how-the-auth--session-flow-works)
7. [Multi-VM Production Architecture Guide](#multi-vm-production-architecture-guide)
8. [Connecting Other FastAPI Microservices to the BFF](#connecting-other-fastapi-microservices-to-the-bff)
9. [Integrating Auth into the Existing Flutter Web Production App](#integrating-auth-into-the-existing-flutter-web-production-app)
10. [Security Best Practices](#security-best-practices)

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
From the root directory (`/home/yaqoosh/Music/deron`):
```bash
docker compose up -d --build
```
Verify that all 4 containers are running:
- PostgreSQL: `localhost:5432`
- Permissions API: `http://localhost:8000/health`
- BFF App: `http://localhost:8001/health`
- Keycloak: `http://localhost:8180`

### Step 2: Configure Keycloak
Follow the [Keycloak Setup Instructions](#keycloak-setup-instructions) below to create the realm and client.

### Step 3: Run Flutter Web
```bash
cd flutter_web
fvm flutter run -d chrome --web-port=8080
```
Open **`http://localhost:8080`** in Google Chrome.

---

## Keycloak Setup Instructions

### Accessing the Keycloak Admin Dashboard
- **Local Development**: `http://localhost:8180`
- **Production / VM**: `https://<YOUR_DOMAIN>/kc/admin/` *(e.g. `https://rlab-drone-establish.egov.uni-koblenz.de/kc/admin/`)*
- **Default Credentials**: `admin` / `admin`

---

### Dashboard Settings Template (Replace `<DOMAIN>` with your domain or `localhost:8080`)

1. Log in to the Admin Dashboard and create a realm:
   - **Realm Name**: `deron-realm` (or `kiwi-realm`)

2. Go to **Clients** $\rightarrow$ **Create client**:

| Field | Value | Purpose |
|---|---|---|
| **Client ID** | `deron-bff` | Unique client identifier |
| **Client Authentication** | **ON** | Makes client confidential (requires secret) |
| **Proof Key for Code Exchange (PKCE)** | **ON** (Method `S256`) | Required PKCE enforcement for code exchange |
| **Authorization** | **OFF** | Standard OIDC authentication only |
| **Authentication flow** | Standard Flow | Enables Authorization Code Flow |
| **Root URL** | `https://<DOMAIN>` | Primary base URL of frontend |
| **Home URL** | `https://<DOMAIN>/` | Default landing page |
| **Valid redirect URIs** | `https://<DOMAIN>/auth/callback`<br>`https://<DOMAIN>/*` | Allowed authentication callback endpoints |
| **Valid post logout redirect URIs** | `https://<DOMAIN>/*` | Allowed post-logout return URIs |
| **Web origins** | `+` *(or `https://<DOMAIN>`)* | Allows CORS origins matching redirect URIs |

3. Click **Save**, open the **Credentials** tab, and copy the **Client Secret**.

4. Go to **Users** $\rightarrow$ **Add user** (e.g. `testuser`) and set a password under the **Credentials** tab (turn off **Temporary**).

5. (Optional) Under **Organizations**, create an organization named `adminsop` and assign your test user to it for Admin Portal authorization testing.

---

## Updating Client Secret in Running Containers

If you regenerate or change the Client Secret in the Keycloak Admin Dashboard, update the running BFF container without needing a full rebuild:

### In Local Development:
1. Update `KEYCLOAK_CLIENT_SECRET` in `bff_app/.env`.
2. Restart the BFF container:
   ```bash
   docker compose restart bff_app
   ```

### In Production (VM):
1. Update `KEYCLOAK_CLIENT_SECRET` in `docker-compose.prod.yml` or `bff_app/.env`.
2. Restart the production BFF container:
   ```bash
   docker compose -f docker-compose.prod.yml restart bff_app
   ```

---

## How the Auth & Session Flow Works

### Login Flow
```
User clicks "Login with Keycloak" in Flutter Web
  └─> Browser navigates to https://<DOMAIN>/auth/login
       └─> BFF generates PKCE code_challenge (S256) and stores verifier in temporary session cookie
            └─> Browser redirected to Keycloak login page (https://<DOMAIN>/kc/realms/deron-realm/...)
                 └─> User logs in
                      └─> Keycloak redirects browser to BFF callback: https://<DOMAIN>/auth/callback?code=XYZ
                           └─> BFF exchanges authorization code for tokens via backchannel (http://keycloak:8080/...)
                                └─> BFF generates opaque session_id and saves tokens + userinfo into PostgreSQL
                                     └─> BFF sets HTTP-only `bff_session_id` cookie
                                          └─> Browser redirected to Flutter Web: https://<DOMAIN>/
```

### Authenticated Request Flow
```
Flutter Web makes API call: POST https://<DOMAIN>/api/v1/permissions/
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
  └─> Browser navigates to https://<DOMAIN>/auth/logout
       └─> BFF deletes session row from PostgreSQL
            └─> BFF clears `bff_session_id` cookie
                 └─> BFF redirects browser to Keycloak logout URL (with id_token_hint)
                      └─> Keycloak revokes SSO session
                           └─> Browser redirected back to Flutter Web (https://<DOMAIN>/)
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

#### 1. In `bff_app/.env`:
```env
# Keycloak Configuration
# Public URL used by browser redirects
KEYCLOAK_SERVER_URL=https://kc.kiwi.uni-koblenz.de
# Internal IP / hostname for BFF backchannel token exchange
KEYCLOAK_INTERNAL_URL=http://10.0.1.10:8080

KEYCLOAK_REALM=kiwi-realm
KEYCLOAK_CLIENT_ID=kiwi-bff
KEYCLOAK_CLIENT_SECRET=prod_secret_here

# PostgreSQL VM Connection String
DATABASE_URL=postgresql+asyncpg://kiwi_user:secure_password@10.0.1.20:5432/kiwi_db

# Downstream Microservices URLs (VM 3 or internal cluster IPs)
PERMISSIONS_API_URL=http://10.0.1.30:8000
COST_CALCULATOR_API_URL=http://10.0.1.31:8000
DIGITAL_CELLAR_API_URL=http://10.0.1.32:8000
```

#### 2. Dual Keycloak URLs in BFF Code (`bff_app/app/main.py`):
In production, the browser reaches Keycloak over HTTPS (`https://kc.kiwi.uni-koblenz.de`), while the BFF talks to Keycloak over the internal university network (`http://10.0.1.10:8080`):

```python
FRONTEND_KC_URL = "https://kc.kiwi.uni-koblenz.de/realms/kiwi-realm"
BACKEND_KC_URL = "http://10.0.1.10:8080/realms/kiwi-realm"

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
KEYCLOAK_ISSUER_URL = "https://kc.kiwi.uni-koblenz.de/realms/kiwi-realm"
KEYCLOAK_INTERNAL_URL = "http://10.0.1.10:8080/realms/kiwi-realm"
JWKS_URL = f"{KEYCLOAK_INTERNAL_URL}/protocol/openid-connect/certs"

jwks_client = PyJWKClient(JWKS_URL)
```

---

## Connecting Other FastAPI Microservices to the BFF

The university project has 5 FastAPI backend repositories (`kiwi-backend-cost-calculator-v2`, `kiwi-backend-digital-cellar-v2`, `kiwi-backend-fertilization-v2`, etc.).

To connect any new microservice to this BFF:

### Step 1: Add Security Verification to the Microservice
Copy [permissions_app/app/security.py](file:///home/yaqoosh/Music/deron/permissions_app/app/security.py) into the microservice repo. Add `token_payload: dict = Depends(verify_token)` to any protected endpoint:

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
  Uri.parse('https://api.kiwi.uni-koblenz.de/api/v1/permissions/'),
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
