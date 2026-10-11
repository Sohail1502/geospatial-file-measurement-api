"""Read Shapefile ZIP archives and KML files without requiring GDAL."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import shapefile
from pyproj import CRS
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    mapping,
    shape,
)
from shapely.geometry.base import BaseGeometry

from app.services.crs import WGS84, crs_label, parse_crs

KML_NS = {
    "kml": "http://www.opengis.net/kml/2.2",
    "gx": "http://www.google.com/kml/ext/2.2",
}


class UnsupportedGeospatialFile(ValueError):
    pass


@dataclass
class FeatureRecord:
    feature_id: int | str
    geometry: BaseGeometry
    properties: dict[str, Any] = field(default_factory=dict)
    crs: CRS = field(default_factory=lambda: WGS84)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "geometry_type": self.geometry.geom_type if self.geometry else "Unknown",
            "geometry": mapping(self.geometry) if self.geometry and not self.geometry.is_empty else None,
            "crs": crs_label(self.crs),
            "properties": _json_safe(self.properties),
        }


def read_geospatial_file(path: Path) -> tuple[list[FeatureRecord], CRS]:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return read_shapefile_zip(path)
    if suffix == ".kml":
        return read_kml(path)
    raise UnsupportedGeospatialFile(f"Unsupported file type: {suffix}")


def read_shapefile_zip(zip_path: Path) -> tuple[list[FeatureRecord], CRS]:
    extract_dir = zip_path.parent / f"{zip_path.stem}_extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            if zf.testzip() is not None:
                raise UnsupportedGeospatialFile("Corrupt ZIP archive")
            zf.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        raise UnsupportedGeospatialFile("File is not a valid ZIP archive") from exc

    shp_files = list(extract_dir.rglob("*.shp"))
    if not shp_files:
        raise UnsupportedGeospatialFile("ZIP archive does not contain a .shp file")
    if len(shp_files) > 1:
        raise UnsupportedGeospatialFile("ZIP archive contains multiple shapefiles; upload one layer per request")

    shp_path = shp_files[0]
    prj_path = shp_path.with_suffix(".prj")
    source_crs = WGS84
    if prj_path.exists():
        source_crs = parse_crs(prj_path.read_text(encoding="utf-8", errors="ignore"))

    features: list[FeatureRecord] = []
    with shapefile.Reader(str(shp_path)) as reader:
        field_names = [field[0] for field in reader.fields[1:]]
        for index, sr in enumerate(reader.shapeRecords()):
            try:
                geom = _shape_to_geometry(sr.shape)
            except Exception:
                continue
            if geom is None or geom.is_empty:
                continue
            properties = {}
            for name, value in zip(field_names, sr.record):
                properties[name] = value
            feature_id = properties.get("id", properties.get("ID", index))
            features.append(
                FeatureRecord(
                    feature_id=feature_id,
                    geometry=geom,
                    properties=properties,
                    crs=source_crs,
                )
            )
    return features, source_crs


def _shape_to_geometry(shp) -> BaseGeometry | None:
    if getattr(shp, "shapeType", None) in (0, None):
        return None
    try:
        geojson = shp.__geo_interface__
    except Exception:
        return None
    if not geojson or geojson.get("type") in (None, "Null"):
        return None
    try:
        return shape(geojson)
    except Exception:
        return None


def read_kml(path: Path) -> tuple[list[FeatureRecord], CRS]:
    """Parse KML Placemarks. KML coordinates are lon,lat[,alt] in WGS84."""
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError as exc:
        raise UnsupportedGeospatialFile("Invalid KML XML") from exc

    features: list[FeatureRecord] = []
    placemarks = _findall(root, "Placemark")
    for index, placemark in enumerate(placemarks):
        name = _child_text(placemark, "name")
        description = _child_text(placemark, "description")
        geom = _kml_geometry(placemark)
        if geom is None or geom.is_empty:
            continue
        properties: dict[str, Any] = {}
        if name:
            properties["name"] = name
        if description:
            properties["description"] = description
        properties.update(_kml_extended_data(placemark))
        feature_id = properties.get("id", name or index)
        features.append(
            FeatureRecord(
                feature_id=feature_id,
                geometry=geom,
                properties=properties,
                crs=WGS84,
            )
        )
    return features, WGS84


def _local_tag(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _findall(element: ET.Element, local_name: str) -> list[ET.Element]:
    return [el for el in element.iter() if _local_tag(el.tag) == local_name]


def _find_child(element: ET.Element, local_name: str) -> ET.Element | None:
    for child in list(element):
        if _local_tag(child.tag) == local_name:
            return child
    return None


def _child_text(element: ET.Element, local_name: str) -> str | None:
    child = _find_child(element, local_name)
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text or None


def _kml_extended_data(placemark: ET.Element) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for data in _findall(placemark, "Data"):
        key = data.attrib.get("name")
        value = _child_text(data, "value")
        if key:
            props[key] = value
    for simple in _findall(placemark, "SimpleData"):
        key = simple.attrib.get("name")
        if key:
            props[key] = (simple.text or "").strip()
    return props


def _kml_geometry(element: ET.Element) -> BaseGeometry | None:
    for child in list(element):
        kind = _local_tag(child.tag)
        if kind == "Point":
            coords = _parse_kml_coordinates(_child_text(child, "coordinates") or "")
            return Point(coords[0]) if coords else None
        if kind == "LineString":
            coords = _parse_kml_coordinates(_child_text(child, "coordinates") or "")
            return LineString(coords) if len(coords) >= 2 else None
        if kind == "Polygon":
            return _kml_polygon(child)
        if kind == "MultiGeometry":
            parts = [_kml_geometry(part) for part in list(child)]
            parts = [g for g in parts if g is not None]
            if not parts:
                return None
            return _collapse_collection(parts)
        if kind in {"MultiTrack", "Track"}:
            return None
        nested = _kml_geometry(child)
        if nested is not None:
            return nested
    return None


def _first_coordinates_text(element: ET.Element) -> str:
    for el in element.iter():
        if _local_tag(el.tag) == "coordinates" and el.text:
            return el.text
    return ""


def _kml_polygon(polygon_el: ET.Element) -> Polygon | None:
    outer = None
    holes: list[list[tuple[float, float]]] = []
    for child in polygon_el.iter():
        tag = _local_tag(child.tag)
        if tag == "outerBoundaryIs":
            coords = _parse_kml_coordinates(_first_coordinates_text(child))
            if coords:
                outer = coords
        elif tag == "innerBoundaryIs":
            coords = _parse_kml_coordinates(_first_coordinates_text(child))
            if coords:
                holes.append(coords)
    if not outer:
        return None
    try:
        return Polygon(outer, holes)
    except Exception:
        return None


def _parse_kml_coordinates(text: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for token in text.replace("\n", " ").split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            continue
        points.append((lon, lat))
    return points


def _collapse_collection(geoms: list[BaseGeometry]) -> BaseGeometry:
    types = {g.geom_type for g in geoms}
    if types == {"Point"}:
        return MultiPoint(geoms)
    if types == {"LineString"}:
        return MultiLineString(geoms)
    if types == {"Polygon"}:
        return MultiPolygon(geoms)
    return GeometryCollection(geoms)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def dump_features(features: list[FeatureRecord]) -> str:
    return json.dumps([f.to_dict() for f in features], default=str)
