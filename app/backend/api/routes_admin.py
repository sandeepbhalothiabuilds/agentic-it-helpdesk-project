from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.backend.db.session import get_db
from app.backend.services.admin_service import get_system_status

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/status")
def admin_status(db: Session = Depends(get_db)):
    return get_system_status(db)