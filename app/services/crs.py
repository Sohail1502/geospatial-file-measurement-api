"""CRS detection and projection selection for accurate measurements."""

from __future__ import annotations

from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

WGS84 = CRS.from_epsg(4326)


def parse_crs(value: str | None, default: CRS = WGS84) -> CRS:
    if not value:
        return default
    try:
        return CRS.from_user_input(value)
    except Exception:
        return default


def crs_label(crs: CRS) -> str:
    try:
        epsg = crs.to_epsg()
        if epsg:
            return f"EPSG:{epsg}"
    except Exception:
        pass
    return crs.to_string()


def _utm_crs_for_lon_lat(lon: float, lat: float) -> CRS:
    """Pick a UTM (or UPS near the poles) CRS from WGS84 lon/lat."""
    if lat >= 84:
        return CRS.from_epsg(32661)  # UPS North
    if lat <= -80:
        return CRS.from_epsg(32761)  # UPS South

    zone = int((lon + 180) / 6) + 1
    zone = min(max(zone, 1), 60)
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return CRS.from_epsg(epsg)


def choose_projected_crs(geometry: BaseGeometry, source_crs: CRS) -> CRS:
    """
    Select a projected CRS suitable for area/length on a single feature.

    Geographic coordinates (degrees) must not be used for planar measurements.
    UTM (or UPS) is chosen from the feature centroid so local survey files
    keep metre-based accuracy without a global equal-area compromise.
    """
    if source_crs is None:
        source_crs = WGS84

    if not source_crs.is_geographic:
        return source_crs

    lon, lat = _centroid_lon_lat(geometry, source_crs)
    return _utm_crs_for_lon_lat(lon, lat)


def _centroid_lon_lat(geometry: BaseGeometry, source_crs: CRS) -> tuple[float, float]:
    centroid = geometry.centroid
    if source_crs == WGS84 or source_crs.to_epsg() == 4326:
        return float(centroid.x), float(centroid.y)

    to_wgs84 = Transformer.from_crs(source_crs, WGS84, always_xy=True)
    lon, lat = to_wgs84.transform(centroid.x, centroid.y)
    return float(lon), float(lat)


def project_geometry(geometry: BaseGeometry, source_crs: CRS, target_crs: CRS) -> BaseGeometry:
    if source_crs == target_crs:
        return geometry
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    return shapely_transform(transformer.transform, geometry)
