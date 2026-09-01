#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
GEE PIXEL-LEVEL SPATIAL INDICES DATABASE — EXPORT PIPELINE (v2 GeoParquet)
================================================================================

Extracts per-pixel index values for ALL pixels INSIDE parcel polygons across
multiple satellite sources, from May 2025 to August 2026.

Data Sources & Indices:
  1. Sentinel-2 L2A (10–20 m):
     NDVI, SAVI, MSAVI, EVI, NDRE, CI_RedEdge, VARI, NDWI, NDMI,
     BSI, Carbonate_SWIR, NDSI_soil, SI_soil, fCover (SL2P NN)

  2. Sentinel-1 GRD (10 m):
     VV_dB, VH_dB, VH_VV_ratio, DpRVIc

  3. MODIS LST (1 km → parcel-level):
     LST_K, SMI, CWSI_proxy

  4. Landsat 8/9 Thermal (100 m → 30 m):
     LST_Landsat_K, LST_Landsat_C, NDVI_Landsat

  5. AgERA5 / ERA5-Land (~11 km → parcel-level):
     Tmin_C, Tmax_C, GDD_cumul, frost_risk

Parcels: Makthar (6) + Sidi Mechreg (5) = 11 parcels
Output:  GeoParquet files per data source & site → outputs/pixel_indices_database/raw/

GEE Project : awam-504508
Author      : GeoAI / WWC Internship
================================================================================
"""

# ──────────────────────────────────────────────────────────────────────────────
#  IMPORTS
# ──────────────────────────────────────────────────────────────────────────────
import os
import sys
import argparse

# ── Fix PROJ_LIB / PROJ_DATA environment variables (PostgreSQL/PostGIS conflicts) ──
for _env in ["PROJ_LIB", "PROJ_DATA"]:
    if _env in os.environ and ("PostgreSQL" in os.environ[_env] or "postgis" in os.environ[_env].lower()):
        del os.environ[_env]

try:
    import pyproj
    _p_dir = pyproj.datadir.get_data_dir()
    if _p_dir and os.path.exists(_p_dir):
        os.environ["PROJ_DATA"] = _p_dir
        os.environ["PROJ_LIB"] = _p_dir
except Exception:
    pass

import ee
import geopandas as gpd
import pandas as pd
import numpy as np
import json
import time
import traceback
import math
from pathlib import Path
from datetime import datetime, timedelta
from shapely.geometry import Point

# Force UTF-8 output encoding for Windows terminal compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

EXTRACT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = EXTRACT_DIR.parent if EXTRACT_DIR.name == "EXTRACT" else EXTRACT_DIR

# ── Load .env environment variables ──
ENV_PATH = EXTRACT_DIR / ".env"
if not ENV_PATH.exists():
    ENV_PATH = SCRIPTS_DIR / ".env"

if ENV_PATH.exists():

    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                os.environ[key] = val


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                           CONFIGURATION                                    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

PROJECT_ID = os.getenv("GEE_PROJECT", "awam-504508")

# ── Parcel GeoJSON files ──
PARCELLES_DIR   = SCRIPTS_DIR / "parcelles_geojson"
GEOJSON_ALL     = PARCELLES_DIR / "AWAM_TERRAIN_ALL_ALL_Boundaries_20250501_20260828_v1.0.geojson"
GEOJSON_MAKTHAR = PARCELLES_DIR / "AWAM_TERRAIN_makthar_ALL_Boundaries_20250501_20260828_v1.0.geojson"
GEOJSON_SIDI    = PARCELLES_DIR / "AWAM_TERRAIN_sidi-mechreg_ALL_Boundaries_20250501_20260828_v1.0.geojson"

# ── Output directory ──
OUTPUT_DIR = SCRIPTS_DIR / "outputs" / "pixel_indices_database" / "raw"

# ── Date range ──
START_DATE = "2025-05-01"
END_DATE   = datetime.now().strftime("%Y-%m-%d")

# ── Output version ──
OUTPUT_VERSION = "2"

# ── Sentinel-2 parameters ──
S2_COLLECTION   = "COPERNICUS/S2_SR_HARMONIZED"
MAX_CLOUD_PCT   = 60        # scene-level cloud filter
S2_SCALE        = 10_000    # DN → reflectance divisor
SAVI_L          = 0.428     # Soil brightness correction factor
PIXEL_SCALE_S2  = 10        # 10 m native resolution for sampling

# ── Sentinel-1 parameters ──
S1_COLLECTION   = "COPERNICUS/S1_GRD"
PIXEL_SCALE_S1  = 10

# ── MODIS LST parameters ──
MODIS_LST_COLLECTION = "MODIS/061/MOD11A1"
PIXEL_SCALE_LST      = 1000    # 1 km

# ── Landsat 8/9 parameters ──
LANDSAT8_COLLECTION = "LANDSAT/LC08/C02/T1_L2"
LANDSAT9_COLLECTION = "LANDSAT/LC09/C02/T1_L2"
PIXEL_SCALE_LANDSAT = 30       # 30 m resampled thermal/optical

# ── AgERA5 parameters ──
AGERA5_COLLECTION = "ECMWF/ERA5_LAND/DAILY_AGGR"
PIXEL_SCALE_AGERA = 11132   # ~11 km

# ── Processing parameters ──
BATCH_SIZE_IMAGES = 5   # process N images per batch to avoid timeouts
MAX_RETRIES       = 3   # retry on GEE compute errors
RETRY_DELAY       = 10  # seconds between retries

# ── fCover SL2P Neural Network coefficients (SNAP v2.1, Weiss & Baret 2016) ──
SNAP_BANDS = ["B3", "B4", "B5", "B6", "B7", "B8A", "B11", "B12"]
BAND_ORDER = SNAP_BANDS + ["cos_view_zenith", "cos_sun_zenith", "cos_rel_azimuth"]

SL2P_FCOVER_COEFFS = dict(
    norm_min=[0, 0, 0, 0.00663797254225, 0.0139727270189, 0.0266901380821,
              0.0163880741923, 0, 0.918595400582, 0.342022871159, -0.999999982118],
    norm_max=[0.253061520472, 0.290393577911, 0.305398915249, 0.608900395798,
              0.753827384323, 0.782011770669, 0.493761397883, 0.49302598446,
              0.999999999991, 0.936206429175, 0.99999999891],
    w1=[
        [-0.156854264841, 0.124234528462, 0.235625516229, -1.8323910258, -0.217188969888, 5.06933958064, -0.887578008155, -1.0808468167, -0.0323167041864, -0.224476137359, -0.195523962947],
        [-0.220824927842, 1.28595395487, 0.703139486363, -1.34481216665, -1.96881267559, -1.45444681639, 1.02737560043, -0.12494641532, 0.0802762437265, -0.198705918577, 0.108527100527],
        [-0.409688743281, 1.08858884766, 0.36284522554, 0.0369390509705, -0.348012590003, -2.0035261881, 0.0410357601757, 1.22373853174, -0.0124082778287, -0.282223364524, 0.0994993117557],
        [-0.188970957866, -0.0358621840833, 0.00551248528107, 1.35391570802, -0.739689896116, -2.21719530107, 0.313216124198, 1.5020168915, 1.21530490195, -0.421938358618, 1.48852484547],
        [2.49293993709, -4.40511331388, -1.91062012624, -0.703174115575, -0.215104721138, -0.972151494818, -0.930752241278, 1.2143441876, -0.521665460192, -0.445755955598, 0.344111873777],
    ],
    b1=[-1.45261652206, -1.70417477557, 1.02168965849, -0.498002810205, -3.88922154789],
    w2=[0.23080586765, -0.333655484884, -0.499418292325, 0.0472484396749, -0.0798516540739],
    b2=-0.0967998147811,
    denorm_min=0.000181230723879,
    denorm_max=0.999638214715,
    out_tolerance=-0.1,
    out_min=0,
    out_max=1,
    indom_min=[0, 0, 0, 0, 0.00397272701894, 0.0166901380821, 0.00638807419226, 0],
    indom_max=[0.263061520472, 0.300393577911, 0.315398915249, 0.618900395798, 0.763827384323, 0.792011770669, 0.503761397883, 0.50302598446],
)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                      1. GEE INITIALISATION                                 ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def initialize_gee():
    """Authenticate and initialise Google Earth Engine with fallback."""
    projects_to_try = [
        os.getenv("GEE_PROJECT"),
        PROJECT_ID,
    ]
    projects_to_try = [p for p in projects_to_try if p]

    for proj in projects_to_try:
        try:
            ee.Initialize(project=proj)
            print(f"  ✓ GEE ready — project {proj}")
            return
        except Exception as e:
            print(f"  ⚠ GEE init with project '{proj}' failed: {e}")

    print("  ⟳ Attempting GEE authentication...")
    try:
        ee.Authenticate()
        for proj in projects_to_try:
            try:
                ee.Initialize(project=proj)
                print(f"  ✓ GEE ready — project {proj}")
                return
            except Exception:
                pass
    except Exception as e:
        print(f"  ✗ GEE authentication failed: {e}")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    2. PARCEL LOADING & EE CONVERSION                       ║
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
    """Load both GeoJSON files, assign unique parcel_id, return merged GDF + ee.FC."""
    parcels = []

    # ── Makthar ──
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

    print(f"  ✓ {len(gdf)} parcels loaded:")
    for _, r in gdf.iterrows():
        print(f"    • {r['parcel_id']} — {r['culture']} ({r['area_h']:.3f} ha)")

    return gdf


def gdf_to_ee_fc(gdf, site_filter=None):
    """Convert GeoDataFrame to ee.FeatureCollection (polygons only)."""
    if site_filter:
        gdf = gdf[gdf["site"] == site_filter]

    features = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom.geom_type == "MultiPolygon":
            coords = []
            for poly in geom.geoms:
                ring = [[c[0], c[1]] for c in poly.exterior.coords]
                coords.append([ring])
            ee_geom = ee.Geometry.MultiPolygon(coords)
        else:
            ring = [[c[0], c[1]] for c in geom.exterior.coords]
            ee_geom = ee.Geometry.Polygon([ring])

        culture_decl, is_shared = parse_culture_metadata(row["culture"])
        feat = ee.Feature(ee_geom, {
            "parcel_id":                 str(row["parcel_id"]),
            "name":                      str(row["name"]),
            "site":                      str(row["site"]),
            "culture":                   culture_decl,
            "culture_declaree_parcelle": culture_decl,
            "signal_partage":            bool(is_shared),
            "area_h":                    float(row["area_h"]),
        })
        features.append(feat)

    return ee.FeatureCollection(features)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                3. SENTINEL-2: CLOUD MASK & SPECTRAL INDICES                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def mask_clouds_s2(image):
    """Mask clouds/shadows using SCL. Returns reflectance in [0, 1]."""
    scl = image.select("SCL")
    clear = (scl.eq(4)       # vegetation
             .Or(scl.eq(5))  # bare soil
             .Or(scl.eq(2))  # dark features / soil shadow (empêche le rejet du sol nu très sec)
             .Or(scl.eq(6))  # water
             .Or(scl.eq(7))  # unclassified
             .Or(scl.eq(11)))  # snow/ice
    return ee.Image(image.updateMask(clear)
                      .divide(S2_SCALE)
                      .copyProperties(image))


def add_s2_indices(image):
    """Compute all Sentinel-2 spectral indices and add as bands."""
    b2  = image.select("B2")
    b3  = image.select("B3")
    b4  = image.select("B4")
    b5  = image.select("B5")
    b7  = image.select("B7")
    b8  = image.select("B8")
    b11 = image.select("B11")
    b12 = image.select("B12")

    ndvi = b8.subtract(b4).divide(b8.add(b4)).rename("NDVI")

    L = SAVI_L
    savi = (b8.subtract(b4)
              .divide(b8.add(b4).add(L))
              .multiply(1 + L)
              .rename("SAVI"))

    msavi_term = b8.multiply(2).add(1)
    msavi_sqrt = (msavi_term.pow(2)
                  .subtract(b8.subtract(b4).multiply(8))
                  .sqrt())
    msavi = msavi_term.subtract(msavi_sqrt).divide(2).rename("MSAVI")

    evi = (b8.subtract(b4).multiply(2.5)
             .divide(b8.add(b4.multiply(6)).subtract(b2.multiply(7.5)).add(1))
             .rename("EVI"))

    ndre = b8.subtract(b5).divide(b8.add(b5)).rename("NDRE")
    ci_re = b7.divide(b5).subtract(1).rename("CI_RedEdge")
    vari = (b3.subtract(b4)
              .divide(b3.add(b4).subtract(b2))
              .rename("VARI"))

    ndwi = b3.subtract(b8).divide(b3.add(b8)).rename("NDWI")
    ndmi = b8.subtract(b11).divide(b8.add(b11)).rename("NDMI")

    bsi = ((b11.add(b4)).subtract(b8.add(b2))
           .divide((b11.add(b4)).add(b8.add(b2)))
           .rename("BSI"))

    carb = b11.divide(b12).rename("Carbonate_SWIR")
    ndsi = b4.subtract(b11).divide(b4.add(b11)).rename("NDSI_soil")
    si = b4.multiply(b11).sqrt().rename("SI_soil")

    return image.addBands([
        ndvi, savi, msavi, evi, ndre, ci_re, vari,
        ndwi, ndmi,
        bsi, carb, ndsi, si,
    ])


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                   4. fCover (SL2P NEURAL NETWORK)                          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def compute_fcover_ee(image):
    """Compute fCover using the SNAP SL2P neural network, server-side."""
    coeffs = SL2P_FCOVER_COEFFS
    refl = image.select(SNAP_BANDS).toFloat()

    sun_zenith  = ee.Number(image.get("MEAN_SOLAR_ZENITH_ANGLE"))
    sun_azimuth = ee.Number(image.get("MEAN_SOLAR_AZIMUTH_ANGLE"))
    view_zenith = ee.List(
        [image.get(f"MEAN_INCIDENCE_ZENITH_ANGLE_{b}") for b in SNAP_BANDS]
    ).reduce(ee.Reducer.mean())
    view_azimuth = ee.List(
        [image.get(f"MEAN_INCIDENCE_AZIMUTH_ANGLE_{b}") for b in SNAP_BANDS]
    ).reduce(ee.Reducer.mean())

    deg2rad = math.pi / 180.0
    cos_vz  = ee.Number(view_zenith).multiply(deg2rad).cos()
    cos_sz  = sun_zenith.multiply(deg2rad).cos()
    cos_raz = sun_azimuth.subtract(ee.Number(view_azimuth)).multiply(deg2rad).cos()

    angle_img = (ee.Image.constant([cos_vz, cos_sz, cos_raz])
                 .rename(["cos_view_zenith", "cos_sun_zenith", "cos_rel_azimuth"])
                 .toFloat())

    input_img = refl.addBands(angle_img).select(BAND_ORDER)

    norm_bands = []
    for i, band_name in enumerate(BAND_ORDER):
        b = input_img.select([band_name])
        nmin, nmax = coeffs["norm_min"][i], coeffs["norm_max"][i]
        n = b.subtract(nmin).divide(nmax - nmin).multiply(2).subtract(1)
        norm_bands.append(n.rename(f"n{i}"))
    norm_img = ee.Image.cat(norm_bands)

    hidden_bands = []
    for i in range(5):
        w, b = coeffs["w1"][i], coeffs["b1"][i]
        acc = ee.Image.constant(b)
        for j in range(11):
            acc = acc.add(norm_img.select([f"n{j}"]).multiply(w[j]))
        hidden_bands.append(acc.tanh().rename(f"h{i}"))
    hidden_img = ee.Image.cat(hidden_bands)

    out = ee.Image.constant(coeffs["b2"])
    for i in range(5):
        out = out.add(hidden_img.select([f"h{i}"]).multiply(coeffs["w2"][i]))

    dmin, dmax = coeffs["denorm_min"], coeffs["denorm_max"]
    out_denorm = out.add(1).multiply(0.5).multiply(dmax - dmin).add(dmin)

    valid_input = ee.Image.constant(1)
    for i in range(8):
        b = input_img.select([BAND_ORDER[i]])
        ok = b.gte(coeffs["indom_min"][i]).And(b.lte(coeffs["indom_max"][i]))
        valid_input = valid_input.And(ok)

    tol  = coeffs["out_tolerance"]
    omin = coeffs["out_min"]
    omax = coeffs["out_max"]
    valid_output = out_denorm.gte(omin + tol).And(out_denorm.lte(omax - tol))
    out_clamped  = out_denorm.max(omin).min(omax)

    final_mask = valid_input.And(valid_output)
    fcover = out_clamped.updateMask(final_mask).rename("fCover")

    return fcover


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║              5. SENTINEL-2 PIPELINE: PROCESS & EXTRACT PIXELS              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def _get_s2_image_list(aoi):
    """Get list of Sentinel-2 image IDs in the date range."""
    coll = (ee.ImageCollection(S2_COLLECTION)
            .filterDate(START_DATE, END_DATE)
            .filterBounds(aoi)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD_PCT))
            .sort("system:time_start"))

    info = coll.aggregate_array("system:index").getInfo()
    dates = coll.aggregate_array("system:time_start").getInfo()
    print(f"  ✓ {len(info)} Sentinel-2 images found in range")
    return info, dates


def process_s2_batch(image_ids, parcels_fc, batch_label=""):
    """Process a batch of Sentinel-2 images → pixel-level index extraction."""
    all_rows = []

    for idx, img_id in enumerate(image_ids):
        date_label = ""
        try:
            img_raw = ee.Image(f"{S2_COLLECTION}/{img_id}")

            ts = img_raw.get("system:time_start").getInfo()
            date_label = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")

            print(f"    [{batch_label} {idx+1}/{len(image_ids)}] {date_label} ({img_id[-15:]})…",
                  end=" ", flush=True)

            img = mask_clouds_s2(img_raw)
            img = add_s2_indices(img)

            fcover = compute_fcover_ee(img)
            img = img.addBands(fcover)

            index_bands = [
                "NDVI", "SAVI", "MSAVI", "EVI", "NDRE", "CI_RedEdge", "VARI",
                "NDWI", "NDMI",
                "BSI", "Carbonate_SWIR", "NDSI_soil", "SI_soil",
                "fCover",
            ]
            img_indices = img.select(index_bands)

            samples = img_indices.sampleRegions(
                collection=parcels_fc,
                scale=PIXEL_SCALE_S2,
                geometries=True,
            )

            result = _getinfo_with_retry(samples)

            if result and "features" in result:
                n_px = len(result["features"])
                for feat in result["features"]:
                    props = feat["properties"]
                    coords = _extract_coords(feat.get("geometry", {}))

                    row = {
                        "parcel_id": props.get("parcel_id", ""),
                        "name":      props.get("name", ""),
                        "site":      props.get("site", ""),
                        "culture":   props.get("culture", ""),
                        "culture_declaree_parcelle": props.get("culture_declaree_parcelle", props.get("culture", "")),
                        "signal_partage": props.get("signal_partage", False),
                        "area_h":    props.get("area_h", None),
                        "date":      date_label,
                        "longitude": coords[0],
                        "latitude":  coords[1],
                    }
                    for band in index_bands:
                        row[band] = props.get(band, None)
                    all_rows.append(row)

                print(f"✓ {n_px} pixels")
            else:
                print("⚠ no valid pixels")

        except Exception as exc:
            print(f"✗ {date_label or img_id}: {exc}")
            traceback.print_exc()

    return all_rows


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                    6. SENTINEL-1 SAR INDICES                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def _get_s1_image_list(aoi):
    """Get Sentinel-1 GRD images (IW, descending, VV+VH)."""
    coll = (ee.ImageCollection(S1_COLLECTION)
            .filterDate(START_DATE, END_DATE)
            .filterBounds(aoi)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
            .sort("system:time_start"))

    info = coll.aggregate_array("system:index").getInfo()
    dates = coll.aggregate_array("system:time_start").getInfo()
    print(f"  ✓ {len(info)} Sentinel-1 images found in range")
    return info, dates


def add_s1_indices(image):
    """Compute SAR-derived indices from Sentinel-1 GRD."""
    vv = image.select("VV")
    vh = image.select("VH")

    vv_lin = ee.Image(10).pow(vv.divide(10)).rename("VV_lin")
    vh_lin = ee.Image(10).pow(vh.divide(10)).rename("VH_lin")

    vh_vv_ratio = vh_lin.divide(vv_lin).rename("VH_VV_ratio")

    # BUGFIX: q*(1-q)*4 is NOT the published dual-pol RVI formula, and is
    # NOT the true polarimetric DpRVI either. The standard dual-pol RVI for
    # intensity data (Trudel et al. 2012; Nasirzadehdizaji et al. 2019;
    # the formula used in the Sentinel Hub "Radar Vegetation Index for
    # Dual Polarimetric" custom script) is simply RVI = 4*VH/(VV+VH) = 4*q.
    # The real DpRVI (Mandal et al. 2020, Remote Sensing of Environment
    # 247:111954) is a different index built from the degree of
    # polarization and the eigenvalues of the 2x2 covariance matrix, which
    # requires SLC data -- GRD amplitude data (as used here) cannot
    # produce it. Column kept as "DpRVIc" for backward compatibility with
    # existing files, but it now holds the standard RVI(v) = 4*VH/(VV+VH).
    q = vh_lin.divide(vv_lin.add(vh_lin))
    dprvic = q.multiply(4).rename("DpRVIc")

    vv_filt = vv.focalMedian(3, "square", "pixels").rename("VV_dB")
    vh_filt = vh.focalMedian(3, "square", "pixels").rename("VH_dB")

    return ee.Image.cat([vv_filt, vh_filt, vh_vv_ratio, dprvic])


def process_s1_batch(image_ids, parcels_fc, batch_label=""):
    """Process a batch of Sentinel-1 images → pixel-level extraction."""
    all_rows = []

    for idx, img_id in enumerate(image_ids):
        date_label = ""
        try:
            img_raw = ee.Image(f"{S1_COLLECTION}/{img_id}")
            ts = img_raw.get("system:time_start").getInfo()
            date_label = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")

            print(f"    [{batch_label} {idx+1}/{len(image_ids)}] {date_label}…",
                  end=" ", flush=True)

            img_indices = add_s1_indices(img_raw)
            index_bands = ["VV_dB", "VH_dB", "VH_VV_ratio", "DpRVIc"]

            samples = img_indices.select(index_bands).sampleRegions(
                collection=parcels_fc,
                scale=PIXEL_SCALE_S1,
                geometries=True,
            )

            result = _getinfo_with_retry(samples)

            if result and "features" in result:
                n_px = len(result["features"])
                for feat in result["features"]:
                    props = feat["properties"]
                    coords = _extract_coords(feat.get("geometry", {}))
                    row = {
                        "parcel_id": props.get("parcel_id", ""),
                        "name":      props.get("name", ""),
                        "site":      props.get("site", ""),
                        "culture":   props.get("culture", ""),
                        "culture_declaree_parcelle": props.get("culture_declaree_parcelle", props.get("culture", "")),
                        "signal_partage": props.get("signal_partage", False),
                        "area_h":    props.get("area_h", None),
                        "date":      date_label,
                        "longitude": coords[0],
                        "latitude":  coords[1],
                    }
                    for band in index_bands:
                        row[band] = props.get(band, None)
                    all_rows.append(row)
                print(f"✓ {n_px} pixels")
            else:
                print("⚠ no data")

        except Exception as exc:
            print(f"✗ {date_label or img_id}: {exc}")
            traceback.print_exc()

    return all_rows


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                   7. MODIS LST (LST / SMI / CWSI)                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def process_lst(parcels_fc, aoi):
    """Extract MODIS Terra LST values per parcel (1 km resolution)."""
    print("  → Querying MODIS Terra LST (MOD11A1) with 1500m centroid buffer sampling…")

    buffered_fc = parcels_fc.map(
        lambda f: f.setGeometry(f.geometry().centroid(1).buffer(1500))
    )

    coll = (ee.ImageCollection(MODIS_LST_COLLECTION)
            .filterDate(START_DATE, END_DATE)
            .filterBounds(aoi)
            .select(["LST_Day_1km", "QC_Day"])
            .sort("system:time_start"))

    n_images = coll.size().getInfo()
    print(f"  ✓ {n_images} MODIS LST images found")

    if n_images == 0:
        print("  ⚠ No MODIS LST data found")
        return []

    img_list = coll.toList(n_images)
    all_rows = []

    for i in range(n_images):
        try:
            img = ee.Image(img_list.get(i))
            ts = img.get("system:time_start").getInfo()
            date_label = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")

            if i % 30 == 0:
                print(f"    [{i+1}/{n_images}] {date_label}…", flush=True)

            lst_k = img.select("LST_Day_1km").multiply(0.02).rename("LST_K")

            stats = lst_k.reduceRegions(
                collection=buffered_fc,
                reducer=ee.Reducer.mean(),
                scale=PIXEL_SCALE_LST,
            )

            result = _getinfo_with_retry(stats)
            if result and "features" in result:
                for feat in result["features"]:
                    props = feat["properties"]
                    lst_val = props.get("mean", None)
                    coords = _extract_coords(feat.get("geometry", {}))
                    row = {
                        "parcel_id": props.get("parcel_id", ""),
                        "name":      props.get("name", ""),
                        "site":      props.get("site", ""),
                        "culture":   props.get("culture", ""),
                        "culture_declaree_parcelle": props.get("culture_declaree_parcelle", props.get("culture", "")),
                        "signal_partage": props.get("signal_partage", False),
                        "area_h":    props.get("area_h", None),
                        "date":      date_label,
                        "longitude": coords[0],
                        "latitude":  coords[1],
                        "LST_K":     lst_val,
                    }
                    all_rows.append(row)

        except Exception as exc:
            if i % 30 == 0:
                print(f"    ✗ MODIS LST image {i}: {exc}")

    print(f"  ✓ {len(all_rows)} LST records extracted")

    if all_rows:
        df = pd.DataFrame(all_rows)
        if "LST_K" in df.columns and df["LST_K"].notna().any():
            # BUGFIX: SMI and CWSI_proxy used to be computed from the
            # min/max/quantiles of the ENTIRE per-parcel time series
            # (i.e. using observations from AFTER each row's own date).
            # That makes every value non-causal, and worse, UNSTABLE: the
            # SMI/CWSI_proxy already written for May 2025 silently changes
            # every time this script is re-run with more recent dates,
            # because the reference min/max/quantiles shift. Using an
            # EXPANDING (causal) window means each row's SMI/CWSI_proxy
            # only depends on data up to and including its own date, so
            # a value already written never changes again on a later run.
            df = df.sort_values(["parcel_id", "date"]).reset_index(drop=True)
            df["SMI"] = np.nan
            df["CWSI_proxy"] = np.nan

            for pid, idx in df.groupby("parcel_id").groups.items():
                sub = df.loc[idx, "LST_K"]

                exp_max = sub.expanding(min_periods=2).max()
                exp_min = sub.expanding(min_periods=2).min()
                denom = exp_max - exp_min
                smi = (exp_max - sub) / denom
                smi[denom == 0] = np.nan
                df.loc[idx, "SMI"] = smi

                # Same >5 observations requirement as before, but evaluated
                # causally: CWSI_proxy only "switches on" once a parcel has
                # accumulated enough history, at the point in time where
                # that happens -- not retroactively for the whole series.
                exp_count = sub.expanding(min_periods=1).count()
                lst_wet = sub.expanding(min_periods=6).quantile(0.05)
                lst_dry = sub.expanding(min_periods=6).quantile(0.95)
                denom_c = lst_dry - lst_wet
                cwsi = ((sub - lst_wet) / denom_c).clip(0, 1)
                cwsi[(exp_count <= 5) | (denom_c == 0)] = np.nan
                df.loc[idx, "CWSI_proxy"] = cwsi

        return df.to_dict("records")

    return all_rows


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                   8. LANDSAT 8/9 THERMAL & OPTICAL                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def _get_landsat_image_list(aoi):
    """Get list of Landsat 8 and 9 collection 2 level 2 images."""
    l8 = (ee.ImageCollection(LANDSAT8_COLLECTION)
          .filterDate(START_DATE, END_DATE)
          .filterBounds(aoi)
          .filter(ee.Filter.lt("CLOUD_COVER", MAX_CLOUD_PCT)))

    l9 = (ee.ImageCollection(LANDSAT9_COLLECTION)
          .filterDate(START_DATE, END_DATE)
          .filterBounds(aoi)
          .filter(ee.Filter.lt("CLOUD_COVER", MAX_CLOUD_PCT)))

    merged = l8.merge(l9).sort("system:time_start")

    ids = merged.aggregate_array("system:id").getInfo()
    dates = merged.aggregate_array("system:time_start").getInfo()
    print(f"  ✓ {len(ids)} Landsat 8/9 images found in range")
    return ids, dates


def mask_clouds_landsat(image):
    """Mask clouds and shadows using QA_PIXEL band for Landsat C2 L2."""
    qa = image.select("QA_PIXEL")
    cloud_shadow_bit_mask = 1 << 4
    cloud_bit_mask = 1 << 3
    dilated_cloud_bit_mask = 1 << 1

    mask = (qa.bitwiseAnd(cloud_shadow_bit_mask).eq(0)
            .And(qa.bitwiseAnd(cloud_bit_mask).eq(0))
            .And(qa.bitwiseAnd(dilated_cloud_bit_mask).eq(0)))

    return image.updateMask(mask)


def add_landsat_thermal(image):
    """Compute LST_Landsat_K, LST_Landsat_C, and NDVI_Landsat."""
    st_b10 = image.select("ST_B10").multiply(0.00341802).add(149.0)
    lst_k = st_b10.rename("LST_Landsat_K")
    lst_c = st_b10.subtract(273.15).rename("LST_Landsat_C")

    sr_b4 = image.select("SR_B4").multiply(0.0000275).add(-0.2)
    sr_b5 = image.select("SR_B5").multiply(0.0000275).add(-0.2)
    ndvi = sr_b5.subtract(sr_b4).divide(sr_b5.add(sr_b4)).rename("NDVI_Landsat")

    return image.addBands([lst_k, lst_c, ndvi])


def process_landsat_batch(image_ids, parcels_fc, batch_label=""):
    """Process a batch of Landsat 8/9 images → pixel-level extraction."""
    all_rows = []

    for idx, img_id in enumerate(image_ids):
        date_label = ""
        try:
            img_raw = ee.Image(img_id)
            ts = img_raw.get("system:time_start").getInfo()
            date_label = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")

            print(f"    [{batch_label} {idx+1}/{len(image_ids)}] {date_label} ({img_id.split('/')[-1]})…",
                  end=" ", flush=True)

            img = mask_clouds_landsat(img_raw)
            img = add_landsat_thermal(img)

            index_bands = ["LST_Landsat_K", "LST_Landsat_C", "NDVI_Landsat"]
            img_indices = img.select(index_bands)

            samples = img_indices.sampleRegions(
                collection=parcels_fc,
                scale=PIXEL_SCALE_LANDSAT,
                geometries=True,
            )

            result = _getinfo_with_retry(samples)

            if result and "features" in result:
                n_px = len(result["features"])
                for feat in result["features"]:
                    props = feat["properties"]
                    coords = _extract_coords(feat.get("geometry", {}))

                    row = {
                        "parcel_id": props.get("parcel_id", ""),
                        "name":      props.get("name", ""),
                        "site":      props.get("site", ""),
                        "culture":   props.get("culture", ""),
                        "culture_declaree_parcelle": props.get("culture_declaree_parcelle", props.get("culture", "")),
                        "signal_partage": props.get("signal_partage", False),
                        "area_h":    props.get("area_h", None),
                        "date":      date_label,
                        "longitude": coords[0],
                        "latitude":  coords[1],
                    }
                    for band in index_bands:
                        row[band] = props.get(band, None)
                    all_rows.append(row)

                print(f"✓ {n_px} pixels")
            else:
                print("⚠ no valid pixels")

        except Exception as exc:
            print(f"✗ {date_label or img_id}: {exc}")
            traceback.print_exc()

    return all_rows


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                   9. AgERA5 / ERA5-LAND METEOROLOGICAL DATA                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def process_agera5(parcels_fc, aoi):
    """Extract daily Tmin, Tmax from ERA5-Land and compute GDD + frost risk."""
    print("  → Querying ERA5-Land daily aggregates (centroid point sampling)…")

    coll = (ee.ImageCollection(AGERA5_COLLECTION)
            .filterDate(START_DATE, END_DATE)
            .filterBounds(aoi)
            .sort("system:time_start"))

    n_images = coll.size().getInfo()
    print(f"  ✓ {n_images} ERA5-Land daily records found")

    if n_images == 0:
        print("  ⚠ No ERA5-Land data found")
        return []

    buffered_fc = parcels_fc.map(
        lambda f: f.setGeometry(f.geometry().centroid(1).buffer(55000))
    )

    img_list = coll.toList(n_images)
    all_rows = []
    # BUGFIX: was keyed by parcel_id only, so GDD accumulated continuously
    # across the ENTIRE extraction window (May 2025 -> today, 16+ months)
    # with no seasonal reset -- not meaningful agronomically, where GDD is
    # normally reset each growing season/calendar year. Now keyed by
    # (parcel_id, year), so it resets on Jan 1st. Base temperature is 10°C
    # (already used below); adjust per-crop if you have real planting dates.
    gdd_accum = {}

    for i in range(n_images):
        try:
            img = ee.Image(img_list.get(i))
            ts = img.get("system:time_start").getInfo()
            date_label = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")

            if i % 30 == 0:
                print(f"    [{i+1}/{n_images}] {date_label}…", flush=True)

            tmin_img = img.select("temperature_2m_min").subtract(273.15).rename("Tmin_C")
            tmax_img = img.select("temperature_2m_max").subtract(273.15).rename("Tmax_C")
            precip_img = img.select("total_precipitation_sum").multiply(1000.0).rename("precip_mm")

            meteo_img = ee.Image.cat([tmin_img, tmax_img, precip_img])

            stats = meteo_img.reduceRegions(
                collection=buffered_fc,
                reducer=ee.Reducer.mean(),
                scale=PIXEL_SCALE_AGERA,
            )

            result = _getinfo_with_retry(stats)

            if result and "features" in result:
                for feat in result["features"]:
                    props = feat["properties"]
                    pid = props.get("parcel_id", "")
                    tmin = props.get("Tmin_C", None)
                    tmax = props.get("Tmax_C", None)
                    precip_val = props.get("precip_mm", None)
                    coords = _extract_coords(feat.get("geometry", {}))

                    gdd_day = 0.0
                    frost = 0
                    if tmin is not None and tmax is not None:
                        gdd_day = max(0, (tmax + tmin) / 2 - 10)
                        frost = 1 if tmin < 0 else 0

                    gdd_key = (pid, date_label[:4])  # resets each calendar year
                    if gdd_key not in gdd_accum:
                        gdd_accum[gdd_key] = 0.0
                    gdd_accum[gdd_key] += gdd_day

                    row = {
                        "parcel_id": pid,
                        "name":      props.get("name", ""),
                        "site":      props.get("site", ""),
                        "culture":   props.get("culture", ""),
                        "culture_declaree_parcelle": props.get("culture_declaree_parcelle", props.get("culture", "")),
                        "signal_partage": props.get("signal_partage", False),
                        "area_h":    props.get("area_h", None),
                        "date":      date_label,
                        "longitude": coords[0],
                        "latitude":  coords[1],
                        "Tmin_C":    round(tmin, 2) if tmin is not None else None,
                        "Tmax_C":    round(tmax, 2) if tmax is not None else None,
                        "precip_mm": round(precip_val, 2) if precip_val is not None else None,
                        "GDD_cumul": round(gdd_accum[gdd_key], 2),
                        "frost_risk": frost,
                    }
                    all_rows.append(row)

        except Exception as exc:
            if i % 30 == 0:
                print(f"    ✗ ERA5 day {i}: {exc}")

    print(f"  ✓ {len(all_rows)} AgERA5 records extracted")
    return all_rows


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                       10. UTILITY FUNCTIONS                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def _getinfo_with_retry(ee_object, max_retries=MAX_RETRIES):
    """Call getInfo() with retry logic for transient GEE errors."""
    for attempt in range(max_retries):
        try:
            return ee_object.getInfo()
        except ee.ee_exception.EEException as e:
            err_msg = str(e)
            if "Computation timed out" in err_msg or "Too many" in err_msg:
                if attempt < max_retries - 1:
                    wait = RETRY_DELAY * (attempt + 1)
                    print(f"\n      ⟳ GEE timeout, retrying in {wait}s (attempt {attempt+2}/{max_retries})…",
                          end=" ", flush=True)
                    time.sleep(wait)
                else:
                    raise
            else:
                raise
    return None


def _extract_coords(geom):
    """Extract lon, lat from a GeoJSON geometry (point or polygon centroid)."""
    if not geom:
        return (None, None)

    gtype = geom.get("type", "")
    coords = geom.get("coordinates", [])

    if gtype == "Point" and len(coords) >= 2:
        return (coords[0], coords[1])
    elif gtype == "Polygon" and coords:
        ring = coords[0]
        n = len(ring)
        if n > 0:
            cx = sum(c[0] for c in ring) / n
            cy = sum(c[1] for c in ring) / n
            return (cx, cy)
    return (None, None)


def build_output_filename(source, site, parcel_id, datatype, start_date, end_date,
                          version=OUTPUT_VERSION):
    """Build AWAM-format output filename for GeoParquet files."""
    s = start_date.replace("-", "")
    e = end_date.replace("-", "")
    site_clean = site.replace("_", "-")
    return f"AWAM_{source}_{site_clean}_{parcel_id}_{datatype}_{s}_{e}_v{version}.parquet"


def save_geoparquet(rows, filename, output_dir, sensor_cols=None):
    """Save list of dicts to GeoParquet (*.parquet) with Point geometry."""
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
        print(f"  ↳ Dropped {n_dropped:,} fully-empty rows (cloud gaps / no sensor data)", flush=True)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / filename
    gdf.to_parquet(filepath, index=False)
    size_mb = filepath.stat().st_size / (1024 * 1024)
    n_parcels = gdf["parcel_id"].nunique() if "parcel_id" in gdf.columns else 0
    n_dates = gdf["date"].nunique() if "date" in gdf.columns else 0
    print(f"  ✓ {len(gdf):,} rows ({size_mb:.2f} MB, {n_parcels} parcels, {n_dates} dates) → {filepath.name}", flush=True)
    return filepath


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                              11. MAIN                                      ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def main():
    global START_DATE, END_DATE
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="GEE Spatial Indices Database Export")
    parser.add_argument("--start-date", type=str, default=START_DATE, help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=END_DATE, help="End date YYYY-MM-DD")
    args = parser.parse_args()

    START_DATE = args.start_date
    END_DATE = args.end_date

    banner = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║   GEE PIXEL-LEVEL SPATIAL INDICES DATABASE — v2 GeoParquet                 ║
║   Makthar & Sidi Mechreg — Tunisia                                         ║
║   Window: {START_DATE} → {END_DATE:<48s}║
║   Sentinel-2 · Sentinel-1 · MODIS LST · Landsat 8/9 · ERA5-Land            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
    print(banner)
    t_global = time.perf_counter()

    # ── 1. Initialize GEE ──
    print("[1/7] GEE Initialization")
    initialize_gee()

    # ── 2. Load parcels ──
    print("\n[2/7] Loading parcels")
    gdf = load_parcels()
    ee_fc = gdf_to_ee_fc(gdf)
    aoi = ee_fc.geometry().bounds()
    sites = gdf["site"].unique().tolist()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n  Output directory: {OUTPUT_DIR}")

    # ── 3. Sentinel-2 spectral indices ──
    print("\n" + "=" * 80)
    print("[3/7] SENTINEL-2 — Spectral, Vegetation, Water, Soil Indices + fCover")
    print("=" * 80)

    s2_ids, s2_dates = _get_s2_image_list(aoi)
    s2_all_rows = []

    n_batches = math.ceil(len(s2_ids) / BATCH_SIZE_IMAGES)
    for b in range(n_batches):
        start = b * BATCH_SIZE_IMAGES
        end   = min(start + BATCH_SIZE_IMAGES, len(s2_ids))
        batch_ids = s2_ids[start:end]
        batch_label = f"S2 batch {b+1}/{n_batches}"

        print(f"\n  {batch_label} ({len(batch_ids)} images)")
        rows = process_s2_batch(batch_ids, ee_fc, batch_label=batch_label)
        s2_all_rows.extend(rows)

    for site in sites:
        site_rows = [r for r in s2_all_rows if r.get("site") == site]
        fname = build_output_filename("GEE", site, "ALL", "S2-Indices", START_DATE, END_DATE)
        save_geoparquet(site_rows, fname, OUTPUT_DIR)

    # ── 4. Sentinel-1 SAR indices ──
    print("\n" + "=" * 80)
    print("[4/7] SENTINEL-1 — SAR Backscatter & DpRVIc (Soil Moisture Proxy)")
    print("=" * 80)

    s1_ids, s1_dates = _get_s1_image_list(aoi)
    s1_all_rows = []

    n_batches_s1 = math.ceil(len(s1_ids) / BATCH_SIZE_IMAGES)
    for b in range(n_batches_s1):
        start = b * BATCH_SIZE_IMAGES
        end   = min(start + BATCH_SIZE_IMAGES, len(s1_ids))
        batch_ids = s1_ids[start:end]
        batch_label = f"S1 batch {b+1}/{n_batches_s1}"

        print(f"\n  {batch_label} ({len(batch_ids)} images)")
        rows = process_s1_batch(batch_ids, ee_fc, batch_label=batch_label)
        s1_all_rows.extend(rows)

    for site in sites:
        site_rows = [r for r in s1_all_rows if r.get("site") == site]
        fname = build_output_filename("GEE", site, "ALL", "S1-SAR", START_DATE, END_DATE)
        save_geoparquet(site_rows, fname, OUTPUT_DIR)

    # ── 5. MODIS LST ──
    print("\n" + "=" * 80)
    print("[5/7] MODIS LST — LST, SMI, CWSI Proxy")
    print("=" * 80)

    s3_rows = process_lst(ee_fc, aoi)
    for site in sites:
        site_rows = [r for r in s3_rows if r.get("site") == site]
        fname = build_output_filename("GEE", site, "ALL", "MODIS-LST", START_DATE, END_DATE)
        save_geoparquet(site_rows, fname, OUTPUT_DIR)

    # ── 6. Landsat 8/9 Thermal ──
    print("\n" + "=" * 80)
    print("[6/7] LANDSAT 8/9 — Thermal LST & Optical NDVI")
    print("=" * 80)

    l89_ids, l89_dates = _get_landsat_image_list(aoi)
    landsat_rows = []

    n_batches_l89 = math.ceil(len(l89_ids) / BATCH_SIZE_IMAGES)
    for b in range(n_batches_l89):
        start = b * BATCH_SIZE_IMAGES
        end   = min(start + BATCH_SIZE_IMAGES, len(l89_ids))
        batch_ids = l89_ids[start:end]
        batch_label = f"Landsat batch {b+1}/{n_batches_l89}"

        print(f"\n  {batch_label} ({len(batch_ids)} images)")
        rows = process_landsat_batch(batch_ids, ee_fc, batch_label=batch_label)
        landsat_rows.extend(rows)

    for site in sites:
        site_rows = [r for r in landsat_rows if r.get("site") == site]
        fname = build_output_filename("GEE", site, "ALL", "Landsat-Thermal", START_DATE, END_DATE)
        save_geoparquet(site_rows, fname, OUTPUT_DIR)

    # ── 7. AgERA5 meteorological data ──
    print("\n" + "=" * 80)
    print("[7/7] ERA5-LAND — Temperature, GDD, Frost Risk")
    print("=" * 80)

    agera5_rows = process_agera5(ee_fc, aoi)
    for site in sites:
        site_rows = [r for r in agera5_rows if r.get("site") == site]
        fname = build_output_filename("GEE", site, "ALL", "ERA5-Meteo", START_DATE, END_DATE)
        save_geoparquet(site_rows, fname, OUTPUT_DIR)

    # ── Summary ──
    elapsed = time.perf_counter() - t_global
    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  ✅  GEE EXPORT COMPLETE                                                    ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  📂  {str(OUTPUT_DIR):<73s}║
║                                                                            ║
║  Sentinel-2 Indices    — {len(s2_all_rows):>8,} rows                             ║
║  Sentinel-1 SAR        — {len(s1_all_rows):>8,} rows                             ║
║  MODIS Thermal LST     — {len(s3_rows):>8,} rows                             ║
║  Landsat Thermal       — {len(landsat_rows):>8,} rows                             ║
║  ERA5-Land Meteo       — {len(agera5_rows):>8,} rows                             ║
║                                                                            ║
║  ⏱  Total time: {elapsed:>8.1f} s                                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

    print("  OUTPUT FILES")
    print("  " + "─" * 60)
    if OUTPUT_DIR.exists():
        for f in sorted(OUTPUT_DIR.glob("AWAM_GEE_*.parquet")):
            gdf_check = gpd.read_parquet(f)
            n_parcels = gdf_check["parcel_id"].nunique() if "parcel_id" in gdf_check.columns else 0
            n_dates = gdf_check["date"].nunique() if "date" in gdf_check.columns else 0
            print(f"  {f.name}")
            print(f"    → {len(gdf_check):>8,} rows  {n_parcels:>2} parcels  {n_dates:>4} dates")
    print()


if __name__ == "__main__":
    main()