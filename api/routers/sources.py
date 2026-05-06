from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import require_token
from database import get_db
from models import Source
from schemas import SourceRead, SourcesList


router = APIRouter(
    prefix="",
    tags=["sources"],
    dependencies=[Depends(require_token)],
)


@router.get("/sources", response_model=SourcesList)
def list_sources(db: Session = Depends(get_db)) -> SourcesList:
    sources = db.scalars(select(Source).order_by(Source.id.asc())).all()
    return SourcesList(data=[SourceRead.model_validate(source) for source in sources])
