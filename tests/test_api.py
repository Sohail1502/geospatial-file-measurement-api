from tests.helpers import write_kml, write_mixed_shapefile_zip, write_shapefile_zip


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_rejects_unsupported_extension(client):
    response = client.post("/api/files/", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert response.status_code == 400


def test_kml_upload_and_measurements(client, tmp_path):
    kml_path = write_kml(tmp_path / "survey.kml")
    with kml_path.open("rb") as handle:
        response = client.post(
            "/api/files/",
            files={"file": ("survey.kml", handle, "application/vnd.google-earth.kml+xml")},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "survey.kml"
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"

    file_id = body["id"]
    info = client.get(f"/api/files/{file_id}/")
    assert info.status_code == 200
    assert info.json()["id"] == file_id

    measured = client.get(f"/api/files/{file_id}/measurements/")
    assert measured.status_code == 200
    features = measured.json()["features"]
    types = {item["geometry_type"]: item for item in features}

    assert types["Point"]["value"] is None
    assert types["Point"]["note"]

    assert types["LineString"]["measurement_type"] == "length"
    assert types["LineString"]["unit"] == "meters"
    assert types["LineString"]["value"] > 1000
    assert types["LineString"]["projected_crs"].startswith("EPSG:326")

    assert types["Polygon"]["measurement_type"] == "area"
    assert types["Polygon"]["unit"] == "square_meters"
    assert types["Polygon"]["value"] > 10_000
    assert types["Polygon"]["projected_crs"].startswith("EPSG:326")


def test_shapefile_zip_upload(client, tmp_path):
    zip_path = write_shapefile_zip(tmp_path / "survey.zip")
    with zip_path.open("rb") as handle:
        response = client.post(
            "/api/files/",
            files={"file": ("survey.zip", handle, "application/zip")},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 1
    assert body["crs"] == "EPSG:4326"

    measured = client.get(f"/api/files/{body['id']}/measurements/")
    feature = measured.json()["features"][0]
    assert feature["geometry_type"] == "Polygon"
    assert feature["measurement_type"] == "area"
    assert feature["value"] > 10_000


def test_empty_geometry_is_skipped_without_crash(client, tmp_path):
    zip_path = write_mixed_shapefile_zip(tmp_path / "mixed.zip")
    with zip_path.open("rb") as handle:
        response = client.post(
            "/api/files/",
            files={"file": ("mixed.zip", handle, "application/zip")},
        )
    assert response.status_code == 201
    measured = client.get(f"/api/files/{response.json()['id']}/measurements/")
    assert measured.status_code == 200
    features = measured.json()["features"]
    assert response.json()["feature_count"] == 1
    assert features[0]["geometry_type"] == "Point"
    assert features[0]["value"] is None


def test_missing_file_returns_404(client):
    response = client.get("/api/files/does-not-exist/")
    assert response.status_code == 404


def test_invalid_kml(client, tmp_path):
    bad = tmp_path / "bad.kml"
    bad.write_text("<not-kml", encoding="utf-8")
    with bad.open("rb") as handle:
        response = client.post("/api/files/", files={"file": ("bad.kml", handle, "application/xml")})
    assert response.status_code == 400
