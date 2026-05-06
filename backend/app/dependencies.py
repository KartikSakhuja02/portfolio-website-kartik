from fastapi import Header, HTTPException, status
from .config import get_settings

settings = get_settings()

def verify_admin(x_admin_key: str = Header(None)):
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Invalid admin key",
        )