from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Deron BFF App"
    VERSION: str = "1.0.0"
    
    # Frontend & BFF URLs — set in docker-compose.yml (dev) or docker-compose.prod.yml (prod)
    FRONTEND_URL: str
    BFF_PUBLIC_URL: str
    
    # Keycloak OAuth2 Config
    KEYCLOAK_SERVER_URL: str
    KEYCLOAK_INTERNAL_URL: str
    KEYCLOAK_REALM: str
    KEYCLOAK_CLIENT_ID: str
    KEYCLOAK_CLIENT_SECRET: str
    
    # BFF Session Secret
    SESSION_SECRET_KEY: str
    
    # Downstream API URL
    PERMISSIONS_API_URL: str
    
    # Database for BFF Sessions
    DATABASE_URL: str

    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

settings = Settings()
