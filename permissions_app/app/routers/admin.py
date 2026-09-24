from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from app.session import get_db
from app.models import PermissionRequest
from app.routers.permissions import PermissionRequestResponse
from app.security import verify_token

router = APIRouter()

def verify_admin(token_payload: dict = Depends(verify_token)):
    """Ensures the user belongs to the adminops organization"""
    orgs = token_payload.get("organization", [])
    if not isinstance(orgs, list):
        orgs = [orgs]
    if "adminsop" not in orgs and "adminops" not in orgs:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Access denied. Must belong to the admin organization."
        )
    return token_payload

@router.get("/permissions", response_model=List[PermissionRequestResponse])
async def get_all_permission_requests(
    skip: int = 0, 
    limit: int = 100, 
    db: AsyncSession = Depends(get_db),
    admin_payload: dict = Depends(verify_admin)
):
    result = await db.execute(select(PermissionRequest).offset(skip).limit(limit))
    return result.scalars().all()

@router.delete("/permissions/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission_request(
    request_id: int, 
    db: AsyncSession = Depends(get_db),
    admin_payload: dict = Depends(verify_admin)
):
    result = await db.execute(select(PermissionRequest).where(PermissionRequest.id == request_id))
    db_obj = result.scalars().first()
    
    if not db_obj:
        raise HTTPException(status_code=404, detail="Permission request not found")
        
    await db.delete(db_obj)
    await db.commit()
    
    return None
