import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient

from app.config import settings

logger = logging.getLogger(__name__)

# Keycloak issuer URL matching the realm payload claim
KEYCLOAK_ISSUER_URL = f"http://localhost:8180/realms/{settings.KEYCLOAK_REALM}"
KEYCLOAK_INTERNAL_URL = f"http://keycloak:8080/realms/{settings.KEYCLOAK_REALM}"
JWKS_URL = f"{KEYCLOAK_INTERNAL_URL}/protocol/openid-connect/certs"

# JWKS client handles fetching and caching Keycloak's public RSA signing keys
jwks_client = PyJWKClient(JWKS_URL)
security = HTTPBearer()


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Extract Authorization header and cryptographically validate the JWT against Keycloak JWKS."""
    token = credentials.credentials
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.KEYCLOAK_AUDIENCE,
            issuer=KEYCLOAK_ISSUER_URL,
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token signature has expired")
    except jwt.InvalidTokenError:
        logger.warning("Invalid JWT signature or claim set")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except Exception:
        logger.error("Token verification failed unexpectedly", exc_info=True)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unable to validate credentials")
