#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
EARTHDATA PIXEL-LEVEL EXTRACTION — ECOSTRESS + NISAR (v2 GeoParquet)
================================================================================

Extracts per-pixel / per-parcel values from NASA Earthdata sources for ALL
pixels INSIDE parcel polygons (plus centroid fallback), across multiple
satellite products.

Data Sources & Variables:
  1. ECOSTRESS L2T LSTE V002 (~70 m):
     LST_ECOSTRESS_K, LST_ECOSTRESS_C, LST_ECOSTRESS_QC, emissivity,
     acquisition_time, day_night

  2. NISAR L3 SME2 (200 m):
     soil_moisture_vol, soil_moisture_qc, vegetation_water_content

  3. NISAR L2 GCOV (200 m):
     HH_gamma0_dB, HV_gamma0_dB, HV_HH_ratio, RVI_NISAR

Parcels: Makthar (6) + Sidi Mechreg (5) = 11 parcels
Output:  GeoParquet files per data source & site → outputs/pixel_indices_database/raw/

Author : GeoAI / WWC Internship
================================================================================
"""

# ──────────────────────────────────────────────────────────────────────────────
#  ENVIRONMENT & PROJ CONFLICT FIX
# ──────────────────────────────────────────────────────────────────────────────
import os
import sys
import argparse

# ── Fix PROJ conflicts: clear ALL PROJ env vars so GDAL uses its built-in fallback ──
# The pyproj bundled proj.db (VERSION_MINOR=4) is too old for rasterio's GDAL.
# Pointing PROJ_DATA to it causes silent CRS resolution failures (all values → NaN).
# Clearing both vars forces GDAL to use its own working PROJ data.
for _env in ["PROJ_LIB", "PROJ_DATA"]:
    if _env in os.environ:
        del os.environ[_env]

# Suppress noisy PROJ/GDAL warnings and third-party FutureWarnings
os.environ["CPL_LOG"] = "OFF"
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import logging
import traceback
import math
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, box

# Force UTF-8 output encoding for Windows terminal compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import earthaccess
except ImportError:
    print("ERROR: earthaccess not installed. Run: pip install earthaccess")
    sys.exit(1)

try:
    import h5py
except ImportError:
    print("ERROR: h5py not installed. Run: pip install h5py")
    sys.exit(1)

try:
    import rasterio
    from rasterio.mask import mask as rio_mask
    from rasterio.warp import transform as rio_transform
    HAS_RASTERIO = True
except ImportError:
    print("WARNING: rasterio not installed. Falling back to h5py-only mode.")
    HAS_RASTERIO = False


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                           CONFIGURATION                                    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

EXTRACT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = EXTRACT_DIR.parent if EXTRACT_DIR.name == "EXTRACT" else EXTRACT_DIR

# ── Parcel GeoJSON files ──
PARCELLES_DIR   = SCRIPTS_DIR / "parcelles_geojson"
GEOJSON_ALL     = PARCELLES_DIR / "AWAM_TERRAIN_ALL_ALL_Boundaries_20250501_20260828_v1.0.geojson"
GEOJSON_MAKTHAR = PARCELLES_DIR / "AWAM_TERRAIN_makthar_ALL_Boundaries_20250501_20260828_v1.0.geojson"
GEOJSON_SIDI    = PARCELLES_DIR / "AWAM_TERRAIN_sidi-mechreg_ALL_Boundaries_20250501_20260828_v1.0.geojson"

# ── Output directories ──
OUTPUT_DIR = SCRIPTS_DIR / "outputs" / "pixel_indices_database" / "raw"
CACHE_DIR  = SCRIPTS_DIR / "outputs" / "pixel_indices_database" / ".cache"
ENV_PATH = EXTRACT_DIR / ".env"
if not ENV_PATH.exists():
    ENV_PATH = SCRIPTS_DIR / ".env"


# ── Date range: May 2025 to latest date (today) ──
START_DATE = "2025-05-01"
END_DATE   = datetime.now().strftime("%Y-%m-%d")

# ── NISAR earliest availability ──
NISAR_START_DATE = "2026-06-17"

# ── Output version ──
OUTPUT_VERSION = "2"

# ── ECOSTRESS config ──
ECOSTRESS_SHORT_NAME = "ECO_L2T_LSTE"
ECOSTRESS_VERSION    = "002"
ECOSTRESS_RESOLUTION = 70   # meters

# ── NISAR concept IDs (ASF DAAC) ──
NISAR_CONCEPT_IDS = {
    "L3_SME2": "C2854344945-ASF",   # Soil Moisture 200m
    "L2_GCOV": "C2854338529-ASF",   # Geocoded Polarimetric Covariance
}

# ── Processing limits ──
MAX_GRANULES_PER_QUERY = 200

class FlushingStreamHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[FlushingStreamHandler(sys.stdout)]
)
logger = logging.getLogger("earthdata_pipeline")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║               1. ENVIRONMENT & AUTHENTICATION                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def load_env_file(path):
    """Load key=value pairs from .env file into os.environ."""
    path = Path(path)
    if path.exists():
        logger.info(f"Loading environment from: {path}")
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    os.environ[key] = val


def authenticate_earthdata():
    """Authenticate with NASA Earthdata using earthaccess."""
    load_env_file(ENV_PATH)
    logger.info("Authenticating with NASA Earthdata...")

    try:
        auth = earthaccess.login(strategy="environment")
        if auth.authenticated:
            logger.info("  ✓ Authenticated via environment variables (EARTHDATA_USERNAME)")
            return True
    except Exception as e:
        logger.debug(f"Environment auth attempt: {e}")

    try:
        auth = earthaccess.login(strategy="netrc")
        if auth.authenticated:
            logger.info("  ✓ Authenticated via ~/.netrc")
            return True
    except Exception as e:
        logger.debug(f"netrc auth attempt: {e}")

    try:
        auth = earthaccess.login(strategy="interactive")
        if auth.authenticated:
            logger.info("  ✓ Authenticated interactively")
            return True
    except Exception as e:
        logger.error(f"  ✗ Authentication failed: {e}")

    return False


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║               2. PARCEL LOADING & METADATA                                 ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def parse_culture_metadata(culture_str):
    """Standardize culture declaration and extract signal_partage boolean flag."""
    if not culture_str or pd.isna(culture_str):
        return "", False

    raw_str = str(culture_str).strip()
    if raw_str in ["Aucune", "Sol nu", "Other", "N/D", ""]:
        return raw_str, False

    raw_species = [s.strip() for s in raw_str.replace("+", "/").replace(",", "/").split("/")]
    valid_species = [s for s in raw_species if s and "weed" not in s.lower() and "advantis" not in s.lower()]

    return raw_str, len(valid_species) > 1


def load_parcels():
    """Load both GeoJSON files (Makthar + Sidi Mechreg), assign unique parcel_id and site."""
    parcels = []

    # ── Makthar ──
    if not GEOJSON_MAKTHAR.exists():
        raise FileNotFoundError(f"Missing parcel file: {GEOJSON_MAKTHAR}")
    gdf_m = gpd.read_file(str(GEOJSON_MAKTHAR))
    if gdf_m.crs and gdf_m.crs.to_epsg() != 4326:
        gdf_m = gdf_m.to_crs(epsg=4326)
    gdf_m["site"] = "makthar"

    if "culture" not in gdf_m.columns and "cult" in gdf_m.columns:
        gdf_m["culture"] = gdf_m["cult"]
    elif "culture" in gdf_m.columns and "cult" in gdf_m.columns:
        gdf_m["culture"] = gdf_m["culture"].fillna(gdf_m["cult"])
    if "area_h" not in gdf_m.columns and "area_ha" in gdf_m.columns:
        gdf_m["area_h"] = gdf_m["area_ha"]

    gdf_m["parcel_id"] = gdf_m.apply(lambda r: f"makthar_{r['name']}", axis=1)
    parcels.append(gdf_m)

    # ── Sidi Mechreg ──
    if not GEOJSON_SIDI.exists():
        raise FileNotFoundError(f"Missing parcel file: {GEOJSON_SIDI}")
    gdf_s = gpd.read_file(str(GEOJSON_SIDI))
    if gdf_s.crs and gdf_s.crs.to_epsg() != 4326:
        gdf_s = gdf_s.to_crs(epsg=4326)
    gdf_s["site"] = "sidi_mechreg"

    if "culture" not in gdf_s.columns and "cult" in gdf_s.columns:
        gdf_s["culture"] = gdf_s["cult"]
    elif "culture" in gdf_s.columns and "cult" in gdf_s.columns:
        gdf_s["culture"] = gdf_s["culture"].fillna(gdf_s["cult"])
    if "area_h" not in gdf_s.columns and "area_ha" in gdf_s.columns:
        gdf_s["area_h"] = gdf_s["area_ha"]

    gdf_s["parcel_id"] = gdf_s.apply(
        lambda r: f"sidi_mechreg_{str(r['name']).replace(' ', '_')}_{r['id']}", axis=1
    )
    parcels.append(gdf_s)

    gdf = pd.concat(parcels, ignore_index=True)
    logger.info(f"  ✓ {len(gdf)} parcels loaded across Makthar and Sidi Mechreg:")
    for _, r in gdf.iterrows():
        logger.info(f"    • [{r['site']}] {r['parcel_id']} — {r['culture']} ({r['area_h']:.3f} ha)")

    return gdf


def compute_bbox(gdf, buffer_deg=0.01):
    """Compute bounding box from GeoDataFrame with a small buffer."""
    bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
    return (
        bounds[0] - buffer_deg,
        bounds[1] - buffer_deg,
        bounds[2] + buffer_deg,
        bounds[3] + buffer_deg,
    )


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║               3. UTILITY FUNCTIONS                                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def _build_parcel_metadata(row):
    """Build standard metadata dict for a parcel row."""
    culture_decl, is_shared = parse_culture_metadata(row.get("culture", ""))
    return {
        "parcel_id":                 str(row["parcel_id"]),
        "name":                      str(row["name"]),
        "site":                      str(row["site"]),
        "culture":                   culture_decl,
        "culture_declaree_parcelle": culture_decl,
        "signal_partage":            bool(is_shared),
        "area_h":                    float(row["area_h"]),
    }


def save_geoparquet(rows, filename, output_dir, sensor_cols=None):
    """Save list of dicts to GeoParquet, filtering fully-empty sensor rows."""
    if not rows:
        print(f"  ⚠ No data to save for {filename}", flush=True)
        return None

    df = pd.DataFrame(rows)

    geometry = []
    for _, row in df.iterrows():
        lon = row.get("longitude")
        lat = row.get("latitude")
        if lon is not None and lat is not None and not pd.isna(lon) and not pd.isna(lat):
            geometry.append(Point(float(lon), float(lat)))
        else:
            geometry.append(None)

    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

    meta_cols = {"parcel_id", "name", "site", "culture", "culture_declaree_parcelle",
                 "signal_partage", "area_h", "date", "longitude", "latitude", "geometry"}
    if sensor_cols is None:
        sensor_cols = [c for c in gdf.columns if c not in meta_cols]

    n_before = len(gdf)
    if sensor_cols:
        gdf = gdf.dropna(subset=sensor_cols, how="all")
    n_dropped = n_before - len(gdf)
    if n_dropped > 0:
        print(f"  ↳ Dropped {n_dropped:,} fully-empty rows", flush=True)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / filename
    gdf.to_parquet(filepath, index=False)
    size_mb = filepath.stat().st_size / (1024 * 1024)
    n_parcels = gdf["parcel_id"].nunique() if "parcel_id" in gdf.columns else 0
    n_dates = gdf["date"].nunique() if "date" in gdf.columns else 0
    print(f"  ✓ {len(gdf):,} rows ({size_mb:.2f} MB, {n_parcels} parcels, {n_dates} dates) → {filepath.name}", flush=True)
    return filepath


def _cleanup_partial_downloads(cache_subdir):
    """Remove partial download files (earthaccess temp files) from cache directory."""
    cache_path = Path(cache_subdir)
    if not cache_path.exists():
        return 0
    removed = 0
    for f in cache_path.iterdir():
        if f.is_file() and f.name.startswith("partial_"):
            try:
                size_mb = f.stat().st_size / 1e6
                f.unlink(missing_ok=True)
                removed += 1
                logger.info(f"    Removed stale partial: {f.name} ({size_mb:.1f} MB)")
            except PermissionError:
                logger.warning(f"    Locked partial (skipped): {f.name}")
            except Exception:
                pass
    return removed


def _convert_to_kelvin(raw_val, src_raster=None):
    """Robust conversion of ECOSTRESS LST raw uint16/float values to Kelvin."""
    if raw_val is None or np.isnan(raw_val) or raw_val <= 0:
        return None

    raw_val = float(raw_val)

    # 1. Try scale + offset from raster metadata
    scale = 1.0
    offset = 0.0
    if src_raster and src_raster.scales and src_raster.scales[0] is not None and src_raster.scales[0] != 0:
        scale = src_raster.scales[0]
    if src_raster and src_raster.offsets and src_raster.offsets[0] is not None:
        offset = src_raster.offsets[0]

    val_meta = raw_val * scale + offset
    if 150.0 <= val_meta <= 370.0:
        return val_meta

    # 2. ECOSTRESS uint16 standard scale factor = 0.02
    val_scaled = raw_val * 0.02
    if 150.0 <= val_scaled <= 370.0:
        return val_scaled

    # 3. Value is directly in Kelvin
    if 150.0 <= raw_val <= 370.0:
        return raw_val

    return None


def _parse_date_from_filename(filename):
    """Extract YYYY-MM-DD string from filename.

    BUGFIX: this used to fall back to `datetime.now()` (today's date) when
    no date pattern could be matched, which silently mislabels a granule
    with the date the SCRIPT WAS RUN rather than the date it was ACQUIRED
    -- with no warning, so a bad match is indistinguishable from a real
    observation from today. If NASA changes a filename convention, or a
    granule is malformed, every row extracted from it silently gets
    "today" as its acquisition date.

    Now returns None on failure and logs a warning. Every caller MUST
    check for None and skip the granule instead of using it.
    """
    import re
    match = re.search(r'(\d{4})(\d{2})(\d{2})', filename)
    if match:
        y, m, d = match.groups()
        if 2020 <= int(y) <= 2030 and 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            return f"{y}-{m}-{d}"
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
    if match:
        return match.group(0)
    logger.warning(
        f"Could not parse an acquisition date from filename '{filename}' -- "
        f"granule SKIPPED (no fallback to today's date)."
    )
    return None


def _parse_time_from_filename(filename):
    """Extract HH:MM:SS string from filename."""
    import re
    match = re.search(r'T(\d{6})', filename)
    if match:
        t = match.group(1)
        return f"{t[:2]}:{t[2:4]}:{t[4:6]}"
    return None


def _infer_day_night(time_str, longitude):
    """Approximate day/night flag from the UTC acquisition time embedded in
    the filename and the pixel's longitude (local solar time ~= UTC +
    longitude/15 hours).

    BUGFIX: this field was documented ("acquisition_time, day_night") and
    extracted as a column, but was previously hard-coded to the literal
    string "unknown" for every single row -- i.e. it was never actually
    computed. This is a simple sun-elevation-free approximation (ECOSTRESS
    flies a non-sun-synchronous ISS orbit, so no fixed local overpass
    time); it does not account for season or latitude, but it is a real
    day/night estimate instead of a constant placeholder.
    """
    if not time_str:
        return "unknown"
    try:
        hh, mm, ss = (int(x) for x in time_str.split(":"))
        utc_hours = hh + mm / 60.0 + ss / 3600.0
        local_hours = (utc_hours + longitude / 15.0) % 24.0
        return "day" if 6.0 <= local_hours < 18.0 else "night"
    except Exception:
        return "unknown"


def search_ecostress(bbox, start_date, end_date):
    """Search for ECOSTRESS L2T LSTE granules covering the AOI."""
    logger.info(f"  Searching ECOSTRESS L2T_LSTE V002  bbox={bbox}")
    try:
        results = earthaccess.search_data(
            short_name=ECOSTRESS_SHORT_NAME,
            version=ECOSTRESS_VERSION,
            bounding_box=bbox,
            temporal=(start_date, end_date),
            count=MAX_GRANULES_PER_QUERY,
        )
        logger.info(f"  ✓ {len(results)} ECOSTRESS granules found")
        return results
    except Exception as e:
        logger.error(f"  ✗ ECOSTRESS search failed: {e}")
        return []


def download_granules(results, cache_subdir, max_files=None):
    """Download Earthdata granules to local cache directory."""
    if not results:
        return []

    dest = CACHE_DIR / cache_subdir
    dest.mkdir(parents=True, exist_ok=True)

    to_download = results[:max_files] if max_files else results
    logger.info(f"  Downloading {len(to_download)} granule(s) to {dest}…")

    try:
        files = earthaccess.download(to_download, str(dest))
        downloaded = [Path(f) for f in files]
        logger.info(f"  ✓ Downloaded {len(downloaded)} file(s)")
        return downloaded
    except Exception as e:
        logger.error(f"  ✗ Download failed: {e}")
        existing = list(dest.glob("*"))
        if existing:
            logger.info(f"  ↳ Using {len(existing)} existing cached file(s)")
            return existing
        return []


ECOSTRESS_L2T_BAND_SUFFIXES = [
    "LST", "LST_err", "QC", "EmisWB", "cloud", "water", "height", "view_zenith"
]

def _group_ecostress_files_by_granule(files):
    """Group GeoTIFF band files by granule prefix."""
    groups = {}
    for f in files:
        name = f.name
        if not name.endswith(".tif"):
            continue
        for suffix in ECOSTRESS_L2T_BAND_SUFFIXES:
            tag = f"_{suffix}.tif"
            if name.endswith(tag):
                prefix = name[: -len(tag)]
                groups.setdefault(prefix, {})[suffix] = f
                break
    return groups


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║               4. ECOSTRESS EXTRACTION PIPELINE                             ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def extract_ecostress_L2T_granule(band_files, parcels_gdf):
    """Extract LST values from L2T granule with guaranteed centroid fallback."""
    rows = []
    if "LST" not in band_files or not HAS_RASTERIO:
        return rows

    lst_path = band_files["LST"]
    date_str = _parse_date_from_filename(lst_path.name)
    if date_str is None:
        return rows
    time_str = _parse_time_from_filename(lst_path.name)
    companion_paths = {k: v for k, v in band_files.items() if k in ("QC", "EmisWB", "cloud") and v.exists()}

    try:
        with rasterio.open(str(lst_path)) as src_lst:
            if not src_lst.crs:
                return rows

            try:
                parcels_proj = parcels_gdf.to_crs(src_lst.crs)
            except Exception as e:
                logger.debug(f"Reprojection failed: {e}")
                return rows

            raster_extent = box(*src_lst.bounds)

            companion_src = {}
            for key, p in companion_paths.items():
                try:
                    companion_src[key] = rasterio.open(str(p))
                except Exception:
                    pass

            try:
                for idx_p, parcel in parcels_proj.iterrows():
                    # Spatial overlap check
                    if not parcel.geometry.intersects(raster_extent):
                        continue

                    meta = _build_parcel_metadata(parcel)
                    extracted_count = 0

                    # 1. Polygon mask extraction
                    try:
                        out_image, out_transform = rio_mask(
                            src_lst, [parcel.geometry], crop=True, all_touched=True, filled=False
                        )
                        lst_data = out_image[0]
                        valid_mask = ~np.ma.getmaskarray(lst_data) & ~np.isnan(lst_data) & (lst_data > 0)
                        if src_lst.nodata is not None:
                            valid_mask &= (lst_data != src_lst.nodata)

                        valid_rows, valid_cols = np.where(valid_mask)
                        if len(valid_rows) > 0:
                            xs, ys = [], []
                            for r, c in zip(valid_rows, valid_cols):
                                x, y = rasterio.transform.xy(out_transform, r, c)
                                xs.append(x)
                                ys.append(y)
                            pts_native = list(zip(xs, ys))
                            lon_arr, lat_arr = rio_transform(src_lst.crs, "EPSG:4326", xs, ys)

                            comp_values = {}
                            for key, csrc in companion_src.items():
                                try:
                                    comp_values[key] = [v[0] for v in csrc.sample(pts_native)]
                                except Exception:
                                    comp_values[key] = [None] * len(pts_native)

                            for i, (r, c) in enumerate(zip(valid_rows, valid_cols)):
                                raw_val = float(lst_data[r, c])
                                lst_k = _convert_to_kelvin(raw_val, src_lst)
                                if lst_k is None:
                                    continue

                                row = {**meta}
                                row.update({
                                    "date": date_str,
                                    "longitude": float(lon_arr[i]),
                                    "latitude": float(lat_arr[i]),
                                    "LST_ECOSTRESS_K": round(lst_k, 2),
                                    "LST_ECOSTRESS_C": round(lst_k - 273.15, 2),
                                    "LST_ECOSTRESS_QC": comp_values.get("QC", [None]*len(pts_native))[i],
                                    "emissivity": comp_values.get("EmisWB", [None]*len(pts_native))[i],
                                    "cloud_flag": comp_values.get("cloud", [None]*len(pts_native))[i],
                                    "acquisition_time": time_str,
                                    "day_night": _infer_day_night(time_str, float(lon_arr[i])),
                                })
                                rows.append(row)
                                extracted_count += 1
                    except Exception as e:
                        logger.debug(f"Polygon mask failed for {meta['parcel_id']}: {e}")

                    # 2. Centroid Fallback if no pixels extracted (small parcel or coarse res)
                    if extracted_count == 0:
                        try:
                            centroid = parcel.geometry.centroid
                            cx, cy = centroid.x, centroid.y
                            sampled = list(src_lst.sample([(cx, cy)]))[0][0]
                            if sampled is not None and not np.isnan(sampled) and sampled > 0:
                                if src_lst.nodata is None or sampled != src_lst.nodata:
                                    raw_val = float(sampled)
                                    lst_k = _convert_to_kelvin(raw_val, src_lst)
                                    if lst_k is not None:
                                        lon_c, lat_c = rio_transform(src_lst.crs, "EPSG:4326", [cx], [cy])
                                        comp_values = {}
                                        for key, csrc in companion_src.items():
                                            try:
                                                comp_values[key] = list(csrc.sample([(cx, cy)]))[0][0]
                                            except Exception:
                                                comp_values[key] = None

                                        row = {**meta}
                                        row.update({
                                            "date": date_str,
                                            "longitude": float(lon_c[0]),
                                            "latitude": float(lat_c[0]),
                                            "LST_ECOSTRESS_K": round(lst_k, 2),
                                            "LST_ECOSTRESS_C": round(lst_k - 273.15, 2),
                                            "LST_ECOSTRESS_QC": comp_values.get("QC"),
                                            "emissivity": comp_values.get("EmisWB"),
                                            "cloud_flag": comp_values.get("cloud"),
                                            "acquisition_time": time_str,
                                            "day_night": _infer_day_night(time_str, float(lon_c[0])),
                                        })
                                        rows.append(row)
                        except Exception as e:
                            logger.debug(f"Centroid fallback failed for {meta['parcel_id']}: {e}")

            finally:
                for csrc in companion_src.values():
                    csrc.close()
    except Exception as e:
        logger.error(f"Error opening granule {lst_path.name}: {e}")

    return rows


def cleanup_cache(cache_subdir=None):
    """Remove temporary cached files."""
    import shutil
    target_dir = (CACHE_DIR / cache_subdir) if cache_subdir else CACHE_DIR
    if target_dir.exists():
        try:
            shutil.rmtree(target_dir, ignore_errors=True)
        except Exception as e:
            logger.debug(f"Cache cleanup warning: {e}")


def process_ecostress(parcels_gdf, bbox=None):
    """Full ECOSTRESS pipeline: search site-by-site → download → extract → return rows."""
    print("\n  ── ECOSTRESS L2T LSTE V002 (~70 m) ──", flush=True)

    results = []
    # Search per site (Makthar & Sidi Mechreg) to ensure tight bounding box
    for site_name, site_gdf in parcels_gdf.groupby("site"):
        site_bbox = compute_bbox(site_gdf, buffer_deg=0.01)
        logger.info(f"  Searching ECOSTRESS for site '{site_name}' bbox={site_bbox}")
        site_results = search_ecostress(site_bbox, START_DATE, END_DATE)
        results.extend(site_results)

    # Deduplicate granules by concept/granule id
    seen_ids = set()
    unique_results = []
    for r in results:
        gid = r.get("meta", {}).get("concept-id") or r.get("umm", {}).get("GranuleUR")
        if gid and gid not in seen_ids:
            seen_ids.add(gid)
            unique_results.append(r)
        elif not gid:
            unique_results.append(r)

    logger.info(f"  ✓ {len(unique_results)} unique ECOSTRESS granules found across sites")

    if not unique_results:
        logger.info("  ⚠ No ECOSTRESS granules found for this region/period")
        return []

    files = download_granules(unique_results, "ecostress")
    if not files:
        logger.info("  ⚠ No ECOSTRESS files downloaded")
        return []

    groups = _group_ecostress_files_by_granule(files)
    logger.info(f"  {len(files)} fichiers .tif -> {len(groups)} granules (bandes regroupées)")

    all_rows = []
    for i, (prefix, band_files) in enumerate(groups.items()):
        print(f"    [{i+1}/{len(groups)}] Processing granule {prefix}…", flush=True)
        if "LST" not in band_files:
            logger.warning(f"  ⚠ Pas de bande LST pour ce granule, ignoré.")
        else:
            rows = extract_ecostress_L2T_granule(band_files, parcels_gdf)
            all_rows.extend(rows)

        for fpath in band_files.values():
            try:
                fpath.unlink(missing_ok=True)
            except Exception:
                pass

    cleanup_cache("ecostress")
    logger.info(f"  ✓ ECOSTRESS total: {len(all_rows)} pixel records")
    return all_rows


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║               5. NISAR SOIL MOISTURE & BACKSCATTER EXTRACTION                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def _discover_hdf5_datasets(filepath):
    """Recursively discover all dataset paths inside an HDF5 file.
    Accepts a local path (str/Path) or an already-open file-like stream object."""
    datasets = []
    def visitor(name, obj):
        if isinstance(obj, h5py.Dataset):
            datasets.append("/" + name)
    try:
        source = str(filepath) if isinstance(filepath, (str, Path)) else filepath
        with h5py.File(source, "r") as f:
            f.visititems(visitor)
    except Exception as e:
        logger.error(f"Error reading HDF5 datasets from {filepath}: {e}")
    return datasets


def _get_nisar_coordinate_info(f, all_datasets):
    """
    Find coordinates (x/y or lon/lat) and CRS from NISAR HDF5 file.
    Returns dict with keys: 'type' ('projected' or 'geographic'), 'x', 'y', 'epsg', 'transformer'
    """
    x_path = next((ds for ds in all_datasets if ds.endswith("/xCoordinates") or "/xCoordinates" in ds), None)
    y_path = next((ds for ds in all_datasets if ds.endswith("/yCoordinates") or "/yCoordinates" in ds), None)
    proj_path = next((ds for ds in all_datasets if ds.endswith("/projection") or "/projection" in ds), None)

    lat_path = next((ds for ds in all_datasets if "latitude" in ds.lower() and "bounds" not in ds.lower()), None)
    lon_path = next((ds for ds in all_datasets if "longitude" in ds.lower() and "bounds" not in ds.lower()), None)

    if x_path and y_path:
        x_arr = f[x_path][:]
        y_arr = f[y_path][:]
        epsg = 4326
        if proj_path:
            try:
                val = f[proj_path][()]
                epsg = int(val) if isinstance(val, (int, np.integer, str)) and str(val).isdigit() else 4326
            except Exception:
                epsg = 4326

        import pyproj
        transformer = pyproj.Transformer.from_crs(epsg, 4326, always_xy=True)
        return {
            "type": "projected",
            "x": x_arr,
            "y": y_arr,
            "epsg": epsg,
            "transformer": transformer,
            "x_path": x_path,
            "y_path": y_path
        }
    elif lat_path and lon_path:
        lat_arr = f[lat_path][:]
        lon_arr = f[lon_path][:]
        return {
            "type": "geographic",
            "lat": lat_arr,
            "lon": lon_arr,
            "lat_path": lat_path,
            "lon_path": lon_path
        }
    return None


def extract_nisar_soil_moisture(filepath, parcels_gdf, stream_name=None):
    """Extract NISAR L3 Soil Moisture values from HDF5 file with polygon + centroid fallback.
    filepath: local path, OR an open file-like stream object (pass stream_name in that case)."""
    rows = []
    is_stream = not isinstance(filepath, (str, Path))
    if is_stream:
        h5_source = filepath
        name_for_parsing = stream_name or "unknown_nisar_sme2.h5"
    else:
        filepath = Path(filepath)
        if not filepath.exists():
            return rows
        h5_source = str(filepath)
        name_for_parsing = filepath.name

    date_str = _parse_date_from_filename(name_for_parsing)
    if date_str is None:
        return rows

    try:
        all_datasets = _discover_hdf5_datasets(h5_source)
        with h5py.File(h5_source, "r") as f:
            sm_path = next((ds for ds in all_datasets if "soilmoisture" in ds.lower().replace("_", "") and "quality" not in ds.lower() and "flag" not in ds.lower() and "uncertainty" not in ds.lower()), None)
            qc_path = next((ds for ds in all_datasets if ("quality" in ds.lower() or "flag" in ds.lower()) and "soil" in ds.lower()), None)
            if not qc_path:
                qc_path = next((ds for ds in all_datasets if "retrievalqualityflag" in ds.lower().replace("_", "")), None)
            vwc_path = next((ds for ds in all_datasets if "vegetationwater" in ds.lower().replace("_", "")), None)

            # BUGFIX: qc_path can legitimately be None (product naming
            # changed, dataset missing from this granule). The old code
            # silently substituted an all-zero array when that happened --
            # 0 is the "recommended / good quality" code, so every pixel
            # from a granule with NO quality layer at all was treated
            # downstream as having PASSED quality control, when in fact no
            # quality control was ever read. Warn loudly and mark the
            # column as unavailable (None) instead of fabricating "good".
            if not qc_path:
                logger.warning(
                    f"No soil-moisture QC dataset found in {name_for_parsing} -- "
                    f"soil_moisture_qc will be recorded as unavailable (None), "
                    f"NOT fabricated as 0/'good'."
                )

            if not sm_path:
                return rows

            coord_info = _get_nisar_coordinate_info(f, all_datasets)
            if not coord_info:
                return rows

            sm_ds = f[sm_path]
            fill_val = sm_ds.attrs.get("_FillValue", sm_ds.attrs.get("fill_value", -9999))

            if coord_info["type"] == "projected":
                epsg = coord_info["epsg"]
                x_arr = coord_info["x"]
                y_arr = coord_info["y"]
                transformer = coord_info["transformer"]

                parcels_utm = parcels_gdf.to_crs(epsg=epsg)
                y_descending = y_arr[0] > y_arr[-1]

                for _, parcel in parcels_utm.iterrows():
                    meta = _build_parcel_metadata(parcel)
                    geom = parcel.geometry
                    minx, miny, maxx, maxy = geom.bounds

                    if maxx < x_arr.min() or minx > x_arr.max():
                        continue
                    if maxy < min(y_arr[0], y_arr[-1]) or miny > max(y_arr[0], y_arr[-1]):
                        continue

                    c_min = max(0, np.searchsorted(x_arr, minx, side='left') - 1)
                    c_max = min(len(x_arr) - 1, np.searchsorted(x_arr, maxx, side='right') + 1)

                    if y_descending:
                        r_min = max(0, np.searchsorted(-y_arr, -maxy, side='left') - 1)
                        r_max = min(len(y_arr) - 1, np.searchsorted(-y_arr, -miny, side='right') + 1)
                    else:
                        r_min = max(0, np.searchsorted(y_arr, miny, side='left') - 1)
                        r_max = min(len(y_arr) - 1, np.searchsorted(y_arr, maxy, side='right') + 1)

                    sub_sm = sm_ds[r_min:r_max+1, c_min:c_max+1]
                    # None (not a fake all-good array) when no QC dataset exists -- see warning above.
                    sub_qc = f[qc_path][r_min:r_max+1, c_min:c_max+1] if qc_path else None
                    sub_vwc = f[vwc_path][r_min:r_max+1, c_min:c_max+1] if vwc_path else np.full_like(sub_sm, np.nan)

                    sub_x = x_arr[c_min:c_max+1]
                    sub_y = y_arr[r_min:r_max+1]
                    sub_xx, sub_yy = np.meshgrid(sub_x, sub_y)

                    extracted_count = 0
                    for r_i in range(sub_sm.shape[0]):
                        for c_i in range(sub_sm.shape[1]):
                            val = float(sub_sm[r_i, c_i])
                            if np.isnan(val) or val == fill_val or val < 0:
                                continue
                            px_x = float(sub_xx[r_i, c_i])
                            px_y = float(sub_yy[r_i, c_i])
                            if geom.contains(Point(px_x, px_y)) or geom.intersects(Point(px_x, px_y)):
                                px_lon, px_lat = transformer.transform(px_x, px_y)
                                row = {**meta}
                                row.update({
                                    "date": date_str,
                                    "longitude": px_lon,
                                    "latitude": px_lat,
                                    "soil_moisture_vol": val,
                                    "soil_moisture_qc": int(sub_qc[r_i, c_i]) if sub_qc is not None else None,
                                    "vegetation_water_content": float(sub_vwc[r_i, c_i]) if not np.isnan(sub_vwc[r_i, c_i]) else None,
                                })
                                rows.append(row)
                                extracted_count += 1

                    if extracted_count == 0:
                        centroid = geom.centroid
                        dist = (sub_xx - centroid.x)**2 + (sub_yy - centroid.y)**2
                        valid_mask = ~np.isnan(sub_sm) & (sub_sm != fill_val) & (sub_sm >= 0)
                        dist[~valid_mask] = np.nan
                        if not np.all(np.isnan(dist)):
                            best_r, best_c = np.unravel_index(np.nanargmin(dist), dist.shape)
                            px_lon, px_lat = transformer.transform(sub_xx[best_r, best_c], sub_yy[best_r, best_c])
                            row = {**meta}
                            row.update({
                                "date": date_str,
                                "longitude": px_lon,
                                "latitude": px_lat,
                                "soil_moisture_vol": float(sub_sm[best_r, best_c]),
                                "soil_moisture_qc": int(sub_qc[best_r, best_c]) if sub_qc is not None else None,
                                "vegetation_water_content": float(sub_vwc[best_r, best_c]) if not np.isnan(sub_vwc[best_r, best_c]) else None,
                            })
                            rows.append(row)

            elif coord_info["type"] == "geographic":
                lat_arr = coord_info["lat"]
                lon_arr = coord_info["lon"]
                sm_data = sm_ds[:]
                # None (not a fake all-good array) when no QC dataset exists -- see warning above.
                qc_data = f[qc_path][:] if qc_path else None
                vwc_data = f[vwc_path][:] if vwc_path else np.full_like(sm_data, np.nan)

                if lat_arr.ndim == 1 and lon_arr.ndim == 1:
                    lon_grid, lat_grid = np.meshgrid(lon_arr, lat_arr)
                else:
                    lon_grid, lat_grid = lon_arr, lat_arr

                valid_mask = (sm_data != fill_val) & ~np.isnan(sm_data.astype(float)) & (sm_data >= 0)

                for _, parcel in parcels_gdf.iterrows():
                    meta = _build_parcel_metadata(parcel)
                    geom = parcel.geometry
                    minx, miny, maxx, maxy = geom.bounds

                    bbox_mask = (lon_grid >= minx) & (lon_grid <= maxx) & (lat_grid >= miny) & (lat_grid <= maxy)
                    cand_indices = np.argwhere(bbox_mask & valid_mask)
                    extracted_count = 0

                    for idx in cand_indices:
                        r, c = idx[0], idx[1]
                        px_lon = float(lon_grid[r, c])
                        px_lat = float(lat_grid[r, c])
                        if geom.contains(Point(px_lon, px_lat)) or geom.intersects(Point(px_lon, px_lat)):
                            row = {**meta}
                            row.update({
                                "date": date_str,
                                "longitude": px_lon,
                                "latitude": px_lat,
                                "soil_moisture_vol": float(sm_data[r, c]),
                                "soil_moisture_qc": int(qc_data[r, c]) if qc_data is not None else None,
                                "vegetation_water_content": float(vwc_data[r, c]) if not np.isnan(vwc_data[r, c]) else None,
                            })
                            rows.append(row)
                            extracted_count += 1

                    if extracted_count == 0:
                        centroid = geom.centroid
                        dist = (lon_grid - centroid.x)**2 + (lat_grid - centroid.y)**2
                        dist[~valid_mask] = np.nan
                        if not np.all(np.isnan(dist)):
                            min_idx = np.unravel_index(np.nanargmin(dist), dist.shape)
                            r, c = min_idx[0], min_idx[1]
                            row = {**meta}
                            row.update({
                                "date": date_str,
                                "longitude": float(lon_grid[r, c]),
                                "latitude": float(lat_grid[r, c]),
                                "soil_moisture_vol": float(sm_data[r, c]),
                                "soil_moisture_qc": int(qc_data[r, c]) if qc_data is not None else None,
                                "vegetation_water_content": float(vwc_data[r, c]) if not np.isnan(vwc_data[r, c]) else None,
                            })
                            rows.append(row)

    except Exception as e:
        logger.error(f"Error processing NISAR SME2 {name_for_parsing}: {e}")

    return rows


def extract_nisar_backscatter(filepath, parcels_gdf, stream_name=None):
    """Extract NISAR L2 GCOV Backscatter values (HH, HV, ratio, RVI) with polygon + centroid fallback.
    filepath: local path, OR an open file-like stream object (pass stream_name in that case)."""
    rows = []
    is_stream = not isinstance(filepath, (str, Path))
    if is_stream:
        h5_source = filepath
        name_for_parsing = stream_name or "unknown_nisar_gcov.h5"
    else:
        filepath = Path(filepath)
        if not filepath.exists():
            return rows
        h5_source = str(filepath)
        name_for_parsing = filepath.name

    date_str = _parse_date_from_filename(name_for_parsing)
    if date_str is None:
        return rows

    try:
        all_datasets = _discover_hdf5_datasets(h5_source)
        with h5py.File(h5_source, "r") as f:
            hh_path = next((ds for ds in all_datasets if ds.endswith("/HH") or "/HH" in ds or ds.endswith("/HHHH") or "/HHHH" in ds), None)
            hv_path = next((ds for ds in all_datasets if ds.endswith("/HV") or "/HV" in ds or ds.endswith("/HVHV") or "/HVHV" in ds), None)

            if not hh_path:
                return rows

            coord_info = _get_nisar_coordinate_info(f, all_datasets)
            if not coord_info:
                return rows

            hh_ds = f[hh_path]
            hv_ds = f[hv_path] if hv_path else None

            if coord_info["type"] == "projected":
                epsg = coord_info["epsg"]
                x_arr = coord_info["x"]
                y_arr = coord_info["y"]
                transformer = coord_info["transformer"]

                parcels_utm = parcels_gdf.to_crs(epsg=epsg)
                y_descending = y_arr[0] > y_arr[-1]

                for _, parcel in parcels_utm.iterrows():
                    meta = _build_parcel_metadata(parcel)
                    geom = parcel.geometry
                    minx, miny, maxx, maxy = geom.bounds

                    if maxx < x_arr.min() or minx > x_arr.max():
                        continue
                    if maxy < min(y_arr[0], y_arr[-1]) or miny > max(y_arr[0], y_arr[-1]):
                        continue

                    c_min = max(0, np.searchsorted(x_arr, minx, side='left') - 1)
                    c_max = min(len(x_arr) - 1, np.searchsorted(x_arr, maxx, side='right') + 1)

                    if y_descending:
                        r_min = max(0, np.searchsorted(-y_arr, -maxy, side='left') - 1)
                        r_max = min(len(y_arr) - 1, np.searchsorted(-y_arr, -miny, side='right') + 1)
                    else:
                        r_min = max(0, np.searchsorted(y_arr, miny, side='left') - 1)
                        r_max = min(len(y_arr) - 1, np.searchsorted(y_arr, maxy, side='right') + 1)

                    sub_hh = hh_ds[r_min:r_max+1, c_min:c_max+1]
                    sub_hv = hv_ds[r_min:r_max+1, c_min:c_max+1] if hv_ds is not None else None

                    sub_x = x_arr[c_min:c_max+1]
                    sub_y = y_arr[r_min:r_max+1]
                    sub_xx, sub_yy = np.meshgrid(sub_x, sub_y)

                    extracted_count = 0
                    for r_i in range(sub_hh.shape[0]):
                        for c_i in range(sub_hh.shape[1]):
                            hh_lin = float(sub_hh[r_i, c_i])
                            if np.isnan(hh_lin) or hh_lin <= 0:
                                continue
                            px_x = float(sub_xx[r_i, c_i])
                            px_y = float(sub_yy[r_i, c_i])
                            if geom.contains(Point(px_x, px_y)) or geom.intersects(Point(px_x, px_y)):
                                px_lon, px_lat = transformer.transform(px_x, px_y)
                                hv_lin = float(sub_hv[r_i, c_i]) if sub_hv is not None else np.nan
                                hh_db = 10 * math.log10(hh_lin) if hh_lin > 0 else None
                                hv_db = 10 * math.log10(hv_lin) if (not np.isnan(hv_lin) and hv_lin > 0) else None
                                ratio = (hv_lin / hh_lin) if (not np.isnan(hv_lin) and hh_lin > 0) else None
                                rvi = None
                                if not np.isnan(hv_lin) and (hh_lin + hv_lin) > 0:
                                    q = hv_lin / (hh_lin + hv_lin)
                                    # BUGFIX: 4*q*(1-q) is NOT the published dual-pol RVI
                                    # formula. The standard formula for dual-pol (co+cross)
                                    # intensity data (Trudel et al. 2012; Nasirzadehdizaji
                                    # et al. 2019; used operationally for S1 VV/VH and
                                    # applicable the same way to NISAR HH/HV) is simply
                                    # RVI = 4*q. The true polarimetric DpRVI (Mandal et al.
                                    # 2020) is a DIFFERENT, more complex index requiring the
                                    # full 2x2 covariance matrix eigenvalues from SLC data,
                                    # which this pipeline does not have (GCOV gives power
                                    # values only) -- so it cannot be computed here at all.
                                    rvi = float(np.clip(4 * q, 0, 4))

                                row = {**meta}
                                row.update({
                                    "date": date_str,
                                    "longitude": px_lon,
                                    "latitude": px_lat,
                                    "HH_gamma0_dB": round(hh_db, 2) if hh_db is not None else None,
                                    "HV_gamma0_dB": round(hv_db, 2) if hv_db is not None else None,
                                    "HV_HH_ratio": round(ratio, 4) if ratio is not None else None,
                                    "RVI_NISAR": round(rvi, 4) if rvi is not None else None,
                                })
                                rows.append(row)
                                extracted_count += 1

                    if extracted_count == 0:
                        centroid = geom.centroid
                        dist = (sub_xx - centroid.x)**2 + (sub_yy - centroid.y)**2
                        valid_mask = ~np.isnan(sub_hh) & (sub_hh > 0)
                        dist[~valid_mask] = np.nan
                        if not np.all(np.isnan(dist)):
                            best_r, best_c = np.unravel_index(np.nanargmin(dist), dist.shape)
                            px_lon, px_lat = transformer.transform(sub_xx[best_r, best_c], sub_yy[best_r, best_c])
                            hh_lin = float(sub_hh[best_r, best_c])
                            hv_lin = float(sub_hv[best_r, best_c]) if sub_hv is not None else np.nan
                            hh_db = 10 * math.log10(hh_lin) if hh_lin > 0 else None
                            hv_db = 10 * math.log10(hv_lin) if (not np.isnan(hv_lin) and hv_lin > 0) else None
                            ratio = (hv_lin / hh_lin) if (not np.isnan(hv_lin) and hh_lin > 0) else None
                            rvi = None
                            if not np.isnan(hv_lin) and (hh_lin + hv_lin) > 0:
                                q = hv_lin / (hh_lin + hv_lin)
                                # BUGFIX: 4*q*(1-q) is NOT the published dual-pol RVI
                                # formula. The standard formula for dual-pol (co+cross)
                                # intensity data (Trudel et al. 2012; Nasirzadehdizaji
                                # et al. 2019; used operationally for S1 VV/VH and
                                # applicable the same way to NISAR HH/HV) is simply
                                # RVI = 4*q. The true polarimetric DpRVI (Mandal et al.
                                # 2020) is a DIFFERENT, more complex index requiring the
                                # full 2x2 covariance matrix eigenvalues from SLC data,
                                # which this pipeline does not have (GCOV gives power
                                # values only) -- so it cannot be computed here at all.
                                rvi = float(np.clip(4 * q, 0, 4))

                            row = {**meta}
                            row.update({
                                "date": date_str,
                                "longitude": px_lon,
                                "latitude": px_lat,
                                "HH_gamma0_dB": round(hh_db, 2) if hh_db is not None else None,
                                "HV_gamma0_dB": round(hv_db, 2) if hv_db is not None else None,
                                "HV_HH_ratio": round(ratio, 4) if ratio is not None else None,
                                "RVI_NISAR": round(rvi, 4) if rvi is not None else None,
                            })
                            rows.append(row)

            elif coord_info["type"] == "geographic":
                lat_arr = coord_info["lat"]
                lon_arr = coord_info["lon"]
                hh_data = hh_ds[:]
                hv_data = hv_ds[:] if hv_ds is not None else None

                if lat_arr.ndim == 1 and lon_arr.ndim == 1:
                    lon_grid, lat_grid = np.meshgrid(lon_arr, lat_arr)
                else:
                    lon_grid, lat_grid = lon_arr, lat_arr

                valid_mask = ~np.isnan(hh_data.astype(float)) & (hh_data > 0)

                for _, parcel in parcels_gdf.iterrows():
                    meta = _build_parcel_metadata(parcel)
                    geom = parcel.geometry
                    minx, miny, maxx, maxy = geom.bounds

                    bbox_mask = (lon_grid >= minx) & (lon_grid <= maxx) & (lat_grid >= miny) & (lat_grid <= maxy)
                    cand_indices = np.argwhere(bbox_mask & valid_mask)
                    extracted_count = 0

                    for idx in cand_indices:
                        r, c = idx[0], idx[1]
                        px_lon = float(lon_grid[r, c])
                        px_lat = float(lat_grid[r, c])
                        if geom.contains(Point(px_lon, px_lat)) or geom.intersects(Point(px_lon, px_lat)):
                            hh_lin = float(hh_data[r, c])
                            hv_lin = float(hv_data[r, c]) if hv_data is not None else np.nan
                            hh_db = 10 * math.log10(hh_lin) if hh_lin > 0 else None
                            hv_db = 10 * math.log10(hv_lin) if (not np.isnan(hv_lin) and hv_lin > 0) else None
                            ratio = (hv_lin / hh_lin) if (not np.isnan(hv_lin) and hh_lin > 0) else None
                            rvi = None
                            if not np.isnan(hv_lin) and (hh_lin + hv_lin) > 0:
                                q = hv_lin / (hh_lin + hv_lin)
                                # BUGFIX: 4*q*(1-q) is NOT the published dual-pol RVI
                                # formula. The standard formula for dual-pol (co+cross)
                                # intensity data (Trudel et al. 2012; Nasirzadehdizaji
                                # et al. 2019; used operationally for S1 VV/VH and
                                # applicable the same way to NISAR HH/HV) is simply
                                # RVI = 4*q. The true polarimetric DpRVI (Mandal et al.
                                # 2020) is a DIFFERENT, more complex index requiring the
                                # full 2x2 covariance matrix eigenvalues from SLC data,
                                # which this pipeline does not have (GCOV gives power
                                # values only) -- so it cannot be computed here at all.
                                rvi = float(np.clip(4 * q, 0, 4))

                            row = {**meta}
                            row.update({
                                "date": date_str,
                                "longitude": px_lon,
                                "latitude": px_lat,
                                "HH_gamma0_dB": round(hh_db, 2) if hh_db is not None else None,
                                "HV_gamma0_dB": round(hv_db, 2) if hv_db is not None else None,
                                "HV_HH_ratio": round(ratio, 4) if ratio is not None else None,
                                "RVI_NISAR": round(rvi, 4) if rvi is not None else None,
                            })
                            rows.append(row)
                            extracted_count += 1

                    if extracted_count == 0:
                        centroid = geom.centroid
                        dist = (lon_grid - centroid.x)**2 + (lat_grid - centroid.y)**2
                        dist[~valid_mask] = np.nan
                        if not np.all(np.isnan(dist)):
                            min_idx = np.unravel_index(np.nanargmin(dist), dist.shape)
                            r, c = min_idx[0], min_idx[1]
                            hh_lin = float(hh_data[r, c])
                            hv_lin = float(hv_data[r, c]) if hv_data is not None else np.nan
                            hh_db = 10 * math.log10(hh_lin) if hh_lin > 0 else None
                            hv_db = 10 * math.log10(hv_lin) if (not np.isnan(hv_lin) and hv_lin > 0) else None
                            ratio = (hv_lin / hh_lin) if (not np.isnan(hv_lin) and hh_lin > 0) else None
                            rvi = None
                            if not np.isnan(hv_lin) and (hh_lin + hv_lin) > 0:
                                q = hv_lin / (hh_lin + hv_lin)
                                # BUGFIX: 4*q*(1-q) is NOT the published dual-pol RVI
                                # formula. The standard formula for dual-pol (co+cross)
                                # intensity data (Trudel et al. 2012; Nasirzadehdizaji
                                # et al. 2019; used operationally for S1 VV/VH and
                                # applicable the same way to NISAR HH/HV) is simply
                                # RVI = 4*q. The true polarimetric DpRVI (Mandal et al.
                                # 2020) is a DIFFERENT, more complex index requiring the
                                # full 2x2 covariance matrix eigenvalues from SLC data,
                                # which this pipeline does not have (GCOV gives power
                                # values only) -- so it cannot be computed here at all.
                                rvi = float(np.clip(4 * q, 0, 4))

                            row = {**meta}
                            row.update({
                                "date": date_str,
                                "longitude": float(lon_grid[r, c]),
                                "latitude": float(lat_grid[r, c]),
                                "HH_gamma0_dB": round(hh_db, 2) if hh_db is not None else None,
                                "HV_gamma0_dB": round(hv_db, 2) if hv_db is not None else None,
                                "HV_HH_ratio": round(ratio, 4) if ratio is not None else None,
                                "RVI_NISAR": round(rvi, 4) if rvi is not None else None,
                            })
                            rows.append(row)

    except Exception as e:
        logger.error(f"Error processing NISAR GCOV {name_for_parsing}: {e}")

    return rows

# ── EXPERIMENTAL: stream a granule via HTTPS instead of downloading it whole ──
# Pattern taken from NASA's own MAAP tutorial for NISAR GCOV:
# https://docs.maap-project.org/en/stable/science/NISAR/NISAR_access.html
# Since our extraction functions already read only a small windowed slice
# (x/y bbox around the parcels) rather than the full array, opening the file
# this way means only the HDF5 chunks touching that window are ever fetched
# over the network — no local .h5 file, no multi-GB download. This is NOT
# tested against a live Earthdata endpoint in development; test on 1-2
# granules with --stream before trusting it for a full run. If it errors,
# the caller falls back to a normal download for that granule.
def _open_granule_https_stream(gran):
    """Returns (file_like_object, filename) for streamed reads, or (None, None) on failure."""
    try:
        https_link = gran.data_links()[0]
        filename = https_link.rsplit("/", 1)[-1]
        fs_https = earthaccess.get_fsspec_https_session()
        file_obj = fs_https.open(https_link, mode="rb", cache_type="blockcache", block_size=8 * 1024 * 1024)
        return file_obj, filename
    except Exception as e:
        logger.warning(f"    Streaming open failed ({e}), will fall back to normal download")
        return None, None


def search_nisar(bbox, product_key, start_date=None, end_date=None):
    """Search for ALL available NISAR granules by concept_id across the full period."""
    if start_date is None:
        start_date = NISAR_START_DATE
    if end_date is None:
        end_date = END_DATE

    concept_id = NISAR_CONCEPT_IDS.get(product_key)
    if not concept_id:
        logger.error(f"  Unknown NISAR product key: {product_key}")
        return []

    logger.info(f"  Searching ALL NISAR {product_key} granules (concept_id={concept_id})")
    logger.info(f"  Date range: {start_date} → {end_date}, bbox={bbox}")

    try:
        results = earthaccess.search_data(
            concept_id=concept_id,
            bounding_box=bbox,
            temporal=(start_date, end_date),
            count=MAX_GRANULES_PER_QUERY,  # Search ALL available dates
        )
        logger.info(f"  ✓ {len(results)} NISAR {product_key} granules found across all dates")
        return results
    except Exception as e:
        logger.error(f"  ✗ NISAR {product_key} search failed: {e}")
        return []


def process_nisar_soil_moisture(parcels_gdf, bbox=None, stream_mode=False):
    """Full NISAR Soil Moisture pipeline: process ALL dates (1 granule at a time to save disk space).
    stream_mode=True: EXPERIMENTAL — open each granule over HTTPS and read only the small
    windowed slice needed, without ever downloading the full file. Falls back to a normal
    download for any granule where streaming fails."""
    print("\n  ── NISAR L3 SME2 Soil Moisture (200 m) — ALL DATES ──" + (" [STREAMING]" if stream_mode else ""))
    dest = CACHE_DIR / "nisar_sm"
    dest.mkdir(parents=True, exist_ok=True)

    # Clean up any stale partial downloads from previous interrupted runs
    n_cleaned = _cleanup_partial_downloads(dest)
    if n_cleaned:
        logger.info(f"  Removed {n_cleaned} stale partial download(s) from nisar_sm/")

    results = []
    for site_name, site_gdf in parcels_gdf.groupby("site"):
        site_bbox = compute_bbox(site_gdf, buffer_deg=0.005)
        res = search_nisar(site_bbox, "L3_SME2")
        results.extend(res)

    # Deduplicate granules
    seen_ids = set()
    unique_results = []
    for r in results:
        gid = r.get("meta", {}).get("concept-id") or r.get("umm", {}).get("GranuleUR")
        if gid and gid not in seen_ids:
            seen_ids.add(gid)
            unique_results.append(r)

    if not unique_results:
        logger.info("  No NISAR L3_SME2 granules found (data from June 2026 only)")
        return []

    logger.info(f"  Processing {len(unique_results)} granules "
                f"({'streaming, no download' if stream_mode else 'sequential 1-by-1 download & instant deletion'})")

    all_rows = []

    for i, gran in enumerate(unique_results):
        print(f"    [{i+1}/{len(unique_results)}] Processing granule {i+1}...", flush=True)

        if stream_mode:
            file_obj, fname = _open_granule_https_stream(gran)
            if file_obj is not None:
                try:
                    rows = extract_nisar_soil_moisture(file_obj, parcels_gdf, stream_name=fname)
                    all_rows.extend(rows)
                    logger.info(f"    Streamed {fname}: {len(rows)} records (no local file written)")
                except Exception as e:
                    logger.error(f"    Streaming extraction failed for granule {i+1}: {e}")
                finally:
                    try:
                        file_obj.close()
                    except Exception:
                        pass
                continue
            # else: fall through to normal download below

        try:
            downloaded = earthaccess.download([gran], str(dest))
            if downloaded:
                fpath = Path(downloaded[0])
                size_gb = fpath.stat().st_size / 1e9 if fpath.exists() else 0
                logger.info(f"    Downloaded {fpath.name} ({size_gb:.2f} GB)")
                rows = extract_nisar_soil_moisture(fpath, parcels_gdf)
                all_rows.extend(rows)
                logger.info(f"    Extracted {len(rows)} records, deleting file...")
                # Instant cleanup: delete Heavy HDF5 immediately so disk space is never filled
                try:
                    fpath.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"    Failed granule {i+1}: {e}")

    cleanup_cache("nisar_sm")
    logger.info(f"  NISAR Soil Moisture total across ALL dates: {len(all_rows)} records")
    return all_rows


def process_nisar_backscatter(parcels_gdf, bbox=None, stream_mode=False):
    """Full NISAR Backscatter pipeline: process ALL dates (1 granule at a time to save disk space).
    stream_mode=True: EXPERIMENTAL — see process_nisar_soil_moisture docstring."""
    print("\n  -- NISAR L2 GCOV Backscatter (200 m) -- ALL DATES --" + (" [STREAMING]" if stream_mode else ""))
    dest = CACHE_DIR / "nisar_gcov"
    dest.mkdir(parents=True, exist_ok=True)

    # Clean up any stale PARTIAL downloads from previous interrupted runs (safe: these
    # are never complete/usable). Complete .h5 files already in the cache are intentionally
    # left alone here: earthaccess.download() below will detect and reuse them by itself
    # ("File ... already downloaded"), and they'll be processed exactly once in the main
    # loop. Pre-processing them here too (as an earlier version of this function did) causes
    # DOUBLE extraction: once here, then again in the main loop once earthaccess re-downloads
    # the file that this block just deleted — producing duplicate rows in the final parquet.
    n_cleaned = _cleanup_partial_downloads(dest)
    if n_cleaned:
        logger.info(f"  Removed {n_cleaned} stale partial download(s) from nisar_gcov/")

    all_rows = []

    # Now search and deduplicate
    results = []
    for site_name, site_gdf in parcels_gdf.groupby("site"):
        site_bbox = compute_bbox(site_gdf, buffer_deg=0.005)
        res = search_nisar(site_bbox, "L2_GCOV")
        results.extend(res)

    # Deduplicate granules
    seen_ids = set()
    unique_results = []
    for r in results:
        gid = r.get("meta", {}).get("concept-id") or r.get("umm", {}).get("GranuleUR")
        if gid and gid not in seen_ids:
            seen_ids.add(gid)
            unique_results.append(r)

    if not unique_results:
        logger.info("  No NISAR L2_GCOV granules found (data from June 2026 only)")
        return all_rows

    logger.info(f"  Processing {len(unique_results)} granules "
                f"({'streaming, no download' if stream_mode else 'sequential 1-by-1 download & instant deletion'})")

    for i, gran in enumerate(unique_results):
        print(f"    [{i+1}/{len(unique_results)}] Processing granule {i+1}...", flush=True)

        if stream_mode:
            file_obj, fname = _open_granule_https_stream(gran)
            if file_obj is not None:
                try:
                    rows = extract_nisar_backscatter(file_obj, parcels_gdf, stream_name=fname)
                    all_rows.extend(rows)
                    logger.info(f"    Streamed {fname}: {len(rows)} records (no local file written)")
                except Exception as e:
                    logger.error(f"    Streaming extraction failed for granule {i+1}: {e}")
                finally:
                    try:
                        file_obj.close()
                    except Exception:
                        pass
                continue
            # else: fall through to normal download below

        try:
            downloaded = earthaccess.download([gran], str(dest))
            if downloaded:
                fpath = Path(downloaded[0])
                size_gb = fpath.stat().st_size / 1e9 if fpath.exists() else 0
                logger.info(f"    Downloaded {fpath.name} ({size_gb:.2f} GB)")
                rows = extract_nisar_backscatter(fpath, parcels_gdf)
                all_rows.extend(rows)
                logger.info(f"    Extracted {len(rows)} records, deleting {size_gb:.2f} GB file...")
                # Instant cleanup: delete Heavy HDF5 immediately so disk space is never filled
                try:
                    fpath.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"    Failed granule {i+1}: {e}")

    cleanup_cache("nisar_gcov")
    logger.info(f"  NISAR Backscatter total across ALL dates: {len(all_rows)} records")
    return all_rows


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║               6. MAIN ENTRY POINT                                          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def main():
    global START_DATE, END_DATE
    import argparse
    parser = argparse.ArgumentParser(description="Earthdata Extractions (ECOSTRESS + NISAR)")
    parser.add_argument("--start-date", type=str, default=START_DATE, help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=END_DATE, help="End date YYYY-MM-DD")
    parser.add_argument("--nisar-only", action="store_true", help="Only run NISAR extractions (skip ECOSTRESS)")
    parser.add_argument("--ecostress-only", action="store_true", help="Only run ECOSTRESS extractions (skip NISAR)")
    parser.add_argument("--backscatter-only", action="store_true", help="Only run NISAR GCOV Backscatter (skip ECOSTRESS and Soil Moisture)")
    parser.add_argument("--soil-moisture-only", action="store_true", help="Only run NISAR SME2 Soil Moisture (skip ECOSTRESS and Backscatter)")
    parser.add_argument("--stream", action="store_true",
                         help="EXPERIMENTAL: open NISAR granules over HTTPS and read only the small "
                              "windowed slice needed, without downloading the full file. Falls back "
                              "to a normal download per-granule if streaming fails. Test on a small "
                              "run before trusting it for the full period.")
    args, _ = parser.parse_known_args()

    if args.start_date:
        START_DATE = args.start_date
    if args.end_date:
        END_DATE = args.end_date

    if args.backscatter_only or args.soil_moisture_only:
        args.nisar_only = True

    t0 = datetime.now()
    print("=" * 80)
    print(" EARTHDATA PIXEL-LEVEL SPATIAL DATABASE EXTRACTION PIPELINE (v2 GeoParquet)")
    print(f" Period : {START_DATE} → {END_DATE}")
    if args.nisar_only:
        print(" Mode   : NISAR ONLY")
    elif args.ecostress_only:
        print(" Mode   : ECOSTRESS ONLY")
    print("=" * 80)

    # 1. Load parcels across Makthar and Sidi Mechreg
    parcels_gdf = load_parcels()
    bbox = compute_bbox(parcels_gdf)

    # 2. Authenticate
    if not authenticate_earthdata():
        logger.error("Authentication failed. Cannot proceed.")
        sys.exit(1)

    eco_rows = []
    n_eco = 0
    # 3. Process ECOSTRESS LST
    if not args.nisar_only:
        eco_rows = process_ecostress(parcels_gdf, bbox)
        n_eco = len(eco_rows)
        if eco_rows:
            eco_df = pd.DataFrame(eco_rows)
            for site_name, site_rows in eco_df.groupby("site"):
                fname = f"AWAM_Earthdata_{site_name.replace('_', '-')}_ALL_ECOSTRESS-LST_{START_DATE.replace('-', '')}_{END_DATE.replace('-', '')}_v{OUTPUT_VERSION}.parquet"
                save_geoparquet(site_rows.to_dict("records"), fname, OUTPUT_DIR)

    sm_rows = []
    n_sm = 0
    bs_rows = []
    n_bs = 0
    if not args.ecostress_only:
        # 4. Process NISAR Soil Moisture
        if not args.backscatter_only:
            sm_rows = process_nisar_soil_moisture(parcels_gdf, bbox, stream_mode=args.stream)
            n_sm = len(sm_rows)
            if sm_rows:
                sm_df = pd.DataFrame(sm_rows)
                for site_name, site_rows in sm_df.groupby("site"):
                    fname = f"AWAM_Earthdata_{site_name.replace('_', '-')}_ALL_NISAR-SoilMoisture_{NISAR_START_DATE.replace('-', '')}_{END_DATE.replace('-', '')}_v{OUTPUT_VERSION}.parquet"
                    save_geoparquet(site_rows.to_dict("records"), fname, OUTPUT_DIR)

        # 5. Process NISAR Backscatter
        if not args.soil_moisture_only:
            bs_rows = process_nisar_backscatter(parcels_gdf, bbox, stream_mode=args.stream)
            n_bs = len(bs_rows)
            if bs_rows:
                bs_df = pd.DataFrame(bs_rows)
                for site_name, site_rows in bs_df.groupby("site"):
                    fname = f"AWAM_Earthdata_{site_name.replace('_', '-')}_ALL_NISAR-Backscatter_{NISAR_START_DATE.replace('-', '')}_{END_DATE.replace('-', '')}_v{OUTPUT_VERSION}.parquet"
                    save_geoparquet(site_rows.to_dict("records"), fname, OUTPUT_DIR)

    elapsed = (datetime.now() - t0).total_seconds()
    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  ✅  EARTHDATA EXTRACTION COMPLETE                                         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  📂  {str(OUTPUT_DIR):<73s}║
║                                                                            ║
║  ECOSTRESS LST          — {n_eco:>7,} pixel records                          ║
║  NISAR Soil Moisture    — {n_sm:>7,} pixel records                          ║
║  NISAR Backscatter      — {n_bs:>7,} pixel records                          ║
║                                                                            ║
║  ⏱  Total time: {elapsed:>8.1f} s                                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

if __name__ == "__main__":
    main()