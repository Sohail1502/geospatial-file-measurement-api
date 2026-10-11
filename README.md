# Geospatial File Measurement API

Backend service that accepts a Shapefile ZIP or KML upload, extracts features, and returns area/length measurements. Geographic coordinates (for example EPSG:4326) are projected before any planar measurement so results are in metres, not degrees.

Built with **FastAPI** for the Aero assignment: file processing, geospatial handling, and a small production-shaped Python API.

## Setup

### Requirements

- Python 3.11+
- pip

GDAL is **not** required. Shapefiles are read with `pyshp`; KML is parsed with the standard library; measurements use `shapely` and `pyproj`.

### Local run

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API listens on `http://127.0.0.1:8000`.

- Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- Health: `GET /health`

Optional environment variables (see `.env.example`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy connection string |
| `UPLOAD_DIR` | `./data/uploads` | Stored originals |
| `MAX_UPLOAD_BYTES` | `52428800` | 50 MB upload cap |

### Tests

```bash
pytest -q
```

### Docker

```bash
docker build -t geospatial-measurement-api .
docker run --rm -p 8000:8000 geospatial-measurement-api
```

### Sample files

- `sample_data/survey.kml` — point, linestring, and polygon near Bengaluru (WGS84)
- Generate a matching shapefile ZIP:

```bash
python scripts/make_sample_shapefile.py
```

## API

Base path: `/api/files/`

### Upload and process

`POST /api/files/`

`multipart/form-data` field `file`:

- `.zip` containing one Shapefile (`.shp` plus sidecars; `.prj` used for CRS)
- `.kml`

```bash
curl -X POST http://127.0.0.1:8000/api/files/ ^
  -F "file=@sample_data/survey.kml"
```

Response `201`:

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "filename": "survey.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "error_message": null,
  "created_at": "2026-10-11T06:00:00.000000+00:00"
}
```

Statuses: `PROCESSING`, `COMPLETED`, `FAILED`. Processing is synchronous, so a successful upload returns `COMPLETED`. Invalid files return `400` and persist a `FAILED` record.

### File information

`GET /api/files/{id}/`

```bash
curl http://127.0.0.1:8000/api/files/a1b2c3d4-e5f6-7890-abcd-ef1234567890/
```

Same JSON shape as the upload response.

### Measurements

`GET /api/files/{id}/measurements/`

```bash
curl http://127.0.0.1:8000/api/files/a1b2c3d4-e5f6-7890-abcd-ef1234567890/measurements/
```

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "filename": "survey.kml",
  "status": "COMPLETED",
  "source_crs": "EPSG:4326",
  "feature_count": 3,
  "features": [
    {
      "feature_id": "Control Point",
      "geometry_type": "Point",
      "geometry": { "type": "Point", "coordinates": [77.5946, 12.9716] },
      "crs": "EPSG:4326",
      "properties": { "name": "Control Point" },
      "measurement_type": null,
      "value": null,
      "unit": null,
      "projected_crs": null,
      "note": "Point geometries have no area or length measurement"
    },
    {
      "feature_id": "Taxiway",
      "geometry_type": "LineString",
      "geometry": {
        "type": "LineString",
        "coordinates": [[77.59, 12.97], [77.6, 12.97]]
      },
      "crs": "EPSG:4326",
      "properties": { "name": "Taxiway" },
      "measurement_type": "length",
      "value": 1084.21,
      "unit": "meters",
      "projected_crs": "EPSG:32643",
      "note": null
    },
    {
      "feature_id": "Apron",
      "geometry_type": "Polygon",
      "geometry": { "type": "Polygon", "coordinates": [] },
      "crs": "EPSG:4326",
      "properties": { "name": "Apron" },
      "measurement_type": "area",
      "value": 12015.4,
      "unit": "square_meters",
      "projected_crs": "EPSG:32643",
      "note": null
    }
  ]
}
```

Numeric values above are illustrative. Live values depend on the projection of each feature.

Unsupported or empty geometries do not fail the request; that feature gets `value: null` and a `note`.

## Architecture

```
app/
  main.py              FastAPI app, lifespan, CORS
  api/routes.py        HTTP endpoints
  models.py            SQLAlchemy GeospatialFile
  schemas.py           Response models
  services/
    file_service.py    Upload, persistence, orchestration
    geo_reader.py      Shapefile ZIP + KML readers
    crs.py             CRS parse / UTM (or UPS) selection / transform
    measurements.py    Area and length with graceful fallbacks
data/                  SQLite DB and uploaded originals (gitignored)
```

### File-processing flow

1. Validate extension (`.zip` / `.kml`) and size (50 MB).
2. Persist the original under `data/uploads/{id}/`.
3. Insert a `PROCESSING` row.
4. Read features:
   - ZIP: extract, require a single `.shp`, load attributes with `pyshp`, CRS from `.prj` (default EPSG:4326).
   - KML: parse `Placemark` geometries (Point, LineString, Polygon, MultiGeometry). KML is always WGS84.
5. Skip empty geometries. Store feature GeoJSON + properties on the row.
6. Mark `COMPLETED` or `FAILED`.

### Measurement flow

1. `GET .../measurements/` rehydrates stored geometries.
2. Point / MultiPoint: no measurement.
3. Polygon / MultiPolygon: area in square metres.
4. LineString / MultiLineString / LinearRing: length in metres.
5. Anything else (for example GeometryCollection): `note` explaining it is unsupported.

### CRS handling

Planar `area` / `length` on lon/lat is wrong (units would be square-degrees / degrees). For each feature:

1. If the source CRS is already projected, measure in that CRS.
2. If it is geographic, take the feature centroid, convert to WGS84 if needed, and choose:
   - UTM zone `326xx` / `327xx` from longitude and hemisphere
   - UPS (`32661` / `32761`) near the poles
3. Transform with `pyproj` (`always_xy=True`) and then measure.

Per-feature UTM keeps airport/survey-scale files accurate. A single world-wide equal-area CRS would distort local length more.

## Design decisions

| Decision | Why | Alternatives considered |
| --- | --- | --- |
| FastAPI instead of Django REST Framework | Small async-friendly API, native OpenAPI, less boilerplate for one resource | Django + DRF is stronger if you already need admin/auth/ORM batteries |
| `pyshp` + stdlib KML instead of GeoPandas/Fiona | Avoids GDAL wheels on Windows, which is the usual setup failure | GeoPandas is richer (reprojection helpers, more drivers) if GDAL is guaranteed |
| Synchronous processing on upload | Assignment files are small; the client gets `COMPLETED` in one round trip | Background workers (Celery / ARQ) for large layers and `PROCESSING` polling |
| SQLite + JSON blob of features | Zero-ops local demo; enough for typical survey feature counts | Postgres + PostGIS if you need spatial indexes and concurrent writers |
| Per-feature UTM | Matches local mapping practice; metres suitable for area and length | Geodesic `pyproj.Geod` for length only; Lambert azimuthal equal-area for global area; a single file-level CRS |
| Store source geometry as uploaded | Response geometry stays in the file CRS; `projected_crs` documents what was used to measure | Returning projected coordinates would surprise GIS clients |

## Learning

- Geographic CRS values are angles. Area and length only make sense after a projection (or a geodesic formula).
- A Shapefile is a set of files; a ZIP without `.shp` / `.shx` / `.dbf` is not enough.
- KML is XML with nested `Placemark`s; coordinates are `lon,lat[,alt]`, not lat-first.
- APIs that process files should fail per feature when possible, and fail the request only when the file itself is unreadable.
- Keeping GDAL out of the dependency graph makes the project much easier to run in an assignment environment.

## Future scope

- KMZ, GeoJSON, and GeoPackage readers
- Async jobs plus webhook/status polling for large uploads
- Auth (API keys) and per-user quotas
- Optional geodesic length and equal-area algorithms selectable via query param
- Persist measurements so GET does not recompute
- PostGIS, spatial indexes, and bounding-box filters
- Simple map preview of uploaded features
- Kubernetes/Helm packaging and object storage for originals
