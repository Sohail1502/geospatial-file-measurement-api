from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import FileInfoResponse, MeasurementsResponse
from app.services.file_service import get_file_or_404, get_measurements, save_and_process

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/", response_model=FileInfoResponse, status_code=201)
def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    record = save_and_process(db, file)
    return record


@router.get("/{file_id}/", response_model=FileInfoResponse)
def get_file(file_id: str, db: Session = Depends(get_db)):
    return get_file_or_404(db, file_id)


@router.get("/{file_id}/measurements/", response_model=MeasurementsResponse)
def list_measurements(file_id: str, db: Session = Depends(get_db)):
    record = get_file_or_404(db, file_id)
    features = get_measurements(record)
    return {
        "id": record.id,
        "filename": record.filename,
        "status": record.status,
        "source_crs": record.crs,
        "feature_count": record.feature_count,
        "features": features,
    }
