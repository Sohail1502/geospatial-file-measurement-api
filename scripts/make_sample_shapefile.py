"""Generate sample_data/survey.zip for local API trials."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.helpers import write_shapefile_zip


if __name__ == "__main__":
    out = ROOT / "sample_data" / "survey.zip"
    write_shapefile_zip(out)
    print(f"Wrote {out}")
