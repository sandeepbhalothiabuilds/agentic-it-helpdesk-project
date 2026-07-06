from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.backend.db.session import get_db
from app.backend.services.architecture_service import get_architecture_summary

router = APIRouter(prefix="/architecture", tags=["architecture"])


@router.get("/summary")
def architecture_summary(db: Session = Depends(get_db)):
    return get_architecture_summary(db)