from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.backend.db.session import get_db
from app.backend.services.dashboard_service import get_dashboard_snapshot

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(db: Session = Depends(get_db)):
    return get_dashboard_snapshot(db)