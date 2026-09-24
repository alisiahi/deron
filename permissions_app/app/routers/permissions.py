from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from pydantic import BaseModel, Field

from app.session import get_db
from app.models import PermissionRequest
from app.security import verify_token

router = APIRouter()

class PermissionRequestCreate(BaseModel):
    firstName: str = Field(..., min_length=2, description="Must be at least 2 characters")
    lastName: str = Field(..., min_length=2)
    email: str = Field(..., pattern=r"^\S+@\S+\.\S+$", description="Basic email regex")
    role: str = Field(...)
    message: str = Field(..., min_length=10)

class PermissionRequestResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    role: str
    message: str
    
    class Config:
        from_attributes = True

@router.post("/", response_model=PermissionRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_permission_request(
    request_in: PermissionRequestCreate, 
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_token)
):
    db_obj = PermissionRequest(
        first_name=request_in.firstName,
        last_name=request_in.lastName,
        email=request_in.email,
        role=request_in.role,
        message=request_in.message
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

@router.get("/", response_model=List[PermissionRequestResponse])
async def read_permission_requests(
    skip: int = 0, 
    limit: int = 100, 
    db: AsyncSession = Depends(get_db),
    token_payload: dict = Depends(verify_token)
):
    result = await db.execute(select(PermissionRequest).offset(skip).limit(limit))
    return result.scalars().all()
