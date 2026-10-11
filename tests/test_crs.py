from shapely.geometry import Polygon

from app.services.crs import WGS84, choose_projected_crs, project_geometry
from app.services.geo_reader import FeatureRecord
from app.services.measurements import measure_features


def test_geographic_polygon_is_projected_before_area():
    polygon = Polygon(
        [
            (77.5900, 12.9700),
            (77.5910, 12.9700),
            (77.5910, 12.9710),
            (77.5900, 12.9710),
            (77.5900, 12.9700),
        ]
    )
    degree_area = polygon.area
    projected_crs = choose_projected_crs(polygon, WGS84)
    projected = project_geometry(polygon, WGS84, projected_crs)

    assert projected_crs.to_epsg() == 32643
    assert projected.area > 10_000
    assert projected.area != degree_area


def test_unsupported_geometry_does_not_raise():
    from shapely.geometry import GeometryCollection, Point

    feature = FeatureRecord(
        feature_id=1,
        geometry=GeometryCollection([Point(0, 0), Point(1, 1)]),
        properties={},
        crs=WGS84,
    )
    result = measure_features([feature])[0]
    assert result["value"] is None
    assert "not supported" in result["note"]
