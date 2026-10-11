"""Planar measurements after projecting out of geographic CRS."""

from __future__ import annotations

from typing import Any

from shapely.geometry.base import BaseGeometry

from app.services.crs import choose_projected_crs, crs_label, project_geometry
from app.services.geo_reader import FeatureRecord

AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "LinearRing", "MultiLineString"}
NO_MEASUREMENT_TYPES = {"Point", "MultiPoint"}


def measure_features(features: list[FeatureRecord]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for feature in features:
        results.append(_measure_one(feature))
    return results


def _measure_one(feature: FeatureRecord) -> dict[str, Any]:
    payload = feature.to_dict()
    geom = feature.geometry
    geom_type = geom.geom_type if geom else "Unknown"

    if geom is None or geom.is_empty:
        payload.update(
            {
                "measurement_type": None,
                "value": None,
                "unit": None,
                "projected_crs": None,
                "note": "Empty or missing geometry",
            }
        )
        return payload

    if geom_type in NO_MEASUREMENT_TYPES:
        payload.update(
            {
                "measurement_type": None,
                "value": None,
                "unit": None,
                "projected_crs": None,
                "note": "Point geometries have no area or length measurement",
            }
        )
        return payload

    if geom_type not in AREA_TYPES and geom_type not in LENGTH_TYPES:
        payload.update(
            {
                "measurement_type": None,
                "value": None,
                "unit": None,
                "projected_crs": None,
                "note": f"Geometry type {geom_type} is not supported for measurement",
            }
        )
        return payload

    try:
        projected_crs = choose_projected_crs(geom, feature.crs)
        projected = project_geometry(geom, feature.crs, projected_crs)
        payload["projected_crs"] = crs_label(projected_crs)

        if geom_type in AREA_TYPES:
            payload.update(
                {
                    "measurement_type": "area",
                    "value": float(projected.area),
                    "unit": "square_meters",
                    "note": None,
                }
            )
        else:
            payload.update(
                {
                    "measurement_type": "length",
                    "value": float(projected.length),
                    "unit": "meters",
                    "note": None,
                }
            )
    except Exception as exc:
        payload.update(
            {
                "measurement_type": None,
                "value": None,
                "unit": None,
                "projected_crs": None,
                "note": f"Measurement skipped: {exc}",
            }
        )
    return payload
