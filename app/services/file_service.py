from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models import GeospatialFile
from app.services.crs import crs_label
from app.services.geo_reader import UnsupportedGeospatialFile, dump_features, read_geospatial_file
from app.services.measurements import measure_features


def ensure_storage() -> None:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    Path("./data").mkdir(parents=True, exist_ok=True)


def save_and_process(db: Session, upload: UploadFile) -> GeospatialFile:
    ensure_storage()
    filename = Path(upload.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .zip (shapefile) and .kml files are accepted",
        )

    file_id = str(uuid.uuid4())
    dest_dir = settings.upload_dir / file_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    size = 0
    with dest_path.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > settings.max_upload_bytes:
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="File exceeds the 50 MB upload limit",
                )
            out.write(chunk)

    record = GeospatialFile(
        id=file_id,
        filename=filename,
        stored_path=str(dest_path),
        content_type=upload.content_type,
        status="PROCESSING",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    try:
        features, source_crs = read_geospatial_file(dest_path)
        record.feature_count = len(features)
        record.crs = crs_label(source_crs)
        record.features_json = dump_features(features)
        record.status = "COMPLETED"
        record.error_message = None
        db.commit()
        db.refresh(record)
        return record
    except UnsupportedGeospatialFile as exc:
        record.status = "FAILED"
        record.error_message = str(exc)
        db.commit()
        db.refresh(record)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        record.status = "FAILED"
        record.error_message = "Failed to process geospatial file"
        db.commit()
        db.refresh(record)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Failed to process geospatial file",
        )


def get_file_or_404(db: Session, file_id: str) -> GeospatialFile:
    record = db.get(GeospatialFile, file_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return record


def get_measurements(record: GeospatialFile) -> list[dict]:
    if record.status != "COMPLETED" or not record.features_json:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Measurements are not available while status is {record.status}",
        )

    from shapely.geometry import shape

    from app.services.crs import parse_crs
    from app.services.geo_reader import FeatureRecord

    raw_features = json.loads(record.features_json)
    features: list[FeatureRecord] = []
    for item in raw_features:
        geom = shape(item["geometry"]) if item.get("geometry") else None
        if geom is None:
            continue
        features.append(
            FeatureRecord(
                feature_id=item.get("feature_id"),
                geometry=geom,
                properties=item.get("properties") or {},
                crs=parse_crs(item.get("crs") or record.crs),
            )
        )
    return measure_features(features)
