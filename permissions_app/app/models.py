from sqlalchemy import Column, Integer, String
from app.session import Base

class PermissionRequest(Base):
    __tablename__ = "permission_requests"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, index=True, nullable=False)
    role = Column(String, nullable=False)
    message = Column(String, nullable=False)
