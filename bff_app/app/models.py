from sqlalchemy import Column, String, DateTime, JSON
from datetime import datetime, timezone

from app.session import Base

class BFFSession(Base):
    __tablename__ = "bff_sessions"

    id = Column(String(64), primary_key=True)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=True)
    id_token = Column(String, nullable=True)
    user_info = Column(JSON, nullable=True)
    access_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=True)
