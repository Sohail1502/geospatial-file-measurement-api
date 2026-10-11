import zipfile
from pathlib import Path

import shapefile
from shapely.geometry import Polygon, mapping


SAMPLE_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Survey Point</name>
      <Point>
        <coordinates>77.5946,12.9716,0</coordinates>
      </Point>
    </Placemark>
    <Placemark>
      <name>Runway Axis</name>
      <ExtendedData>
        <Data name="id"><value>line-1</value></Data>
      </ExtendedData>
      <LineString>
        <coordinates>
          77.5900,12.9700,0
          77.6000,12.9700,0
        </coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>Apron</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.5900,12.9700,0
              77.5910,12.9700,0
              77.5910,12.9710,0
              77.5900,12.9710,0
              77.5900,12.9700,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>
"""


def write_kml(path: Path) -> Path:
    path.write_text(SAMPLE_KML, encoding="utf-8")
    return path


def write_shapefile_zip(path: Path) -> Path:
    work = path.parent / "shp_src"
    work.mkdir(exist_ok=True)
    shp_path = work / "survey"

    writer = shapefile.Writer(str(shp_path), shapeType=shapefile.POLYGON)
    writer.field("id", "C", size=20)
    writer.field("name", "C", size=40)
    polygon = Polygon(
        [
            (77.5900, 12.9700),
            (77.5910, 12.9700),
            (77.5910, 12.9710),
            (77.5900, 12.9710),
            (77.5900, 12.9700),
        ]
    )
    writer.poly(mapping(polygon)["coordinates"])
    writer.record("poly-1", "Apron")
    writer.close()

    prj = (
        'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
        'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]]'
    )
    (work / "survey.prj").write_text(prj, encoding="utf-8")

    with zipfile.ZipFile(path, "w") as zf:
        for file in work.glob("survey.*"):
            zf.write(file, arcname=file.name)
    return path


def write_mixed_shapefile_zip(path: Path) -> Path:
    work = path.parent / "mixed_src"
    work.mkdir(exist_ok=True)
    shp_path = work / "mixed"

    writer = shapefile.Writer(str(shp_path), shapeType=shapefile.POINT)
    writer.field("id", "C", size=20)
    writer.null()
    writer.record("empty-1")
    writer.point(77.5946, 12.9716)
    writer.record("point-1")
    writer.close()

    prj = (
        'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
        'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]]'
    )
    (work / "mixed.prj").write_text(prj, encoding="utf-8")

    with zipfile.ZipFile(path, "w") as zf:
        for file in work.glob("mixed.*"):
            zf.write(file, arcname=file.name)
    return path
