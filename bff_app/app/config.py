from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Deron BFF App"
    VERSION: str = "1.0.0"
    
    # Keycloak OAuth2 Config
    KEYCLOAK_SERVER_URL: str = "http://localhost:8180"
    KEYCLOAK_REALM: str = "deron-realm"
    KEYCLOAK_CLIENT_ID: str = "deron-bff"
    KEYCLOAK_CLIENT_SECRET: str
    
    # BFF Session Secret (used by Starlette SessionMiddleware for temporary login state)
    SESSION_SECRET_KEY: str
    
    # Downstream API URL
    PERMISSIONS_API_URL: str = "http://permissions_app:8000"
    
    # Database for BFF Sessions
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgrespassword@db:5432/drone_db"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

settings = Settings()
