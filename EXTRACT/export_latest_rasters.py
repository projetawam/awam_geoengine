#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
EXPORT LATEST SATELLITE RASTERS & MANIFEST (GeoTIFF UI Export & Cloudinary Archive)
================================================================================

Exports cropped GeoTIFF raster images for the MOST RECENT acquisition date of
ALL indices analyzed in gee_export_pixel_indices_database.py over site polygons.

Smart Download & Archiving Logic:
  - Auto-checks if the raster for the latest date already exists on disk.
    If already existing, skips redundant GEE network re-downloading.
  - Retains all historical versions: when a newer image is fetched, older
    versions are automatically moved to outputs/archive_rasters/ (for Cloudinary sync)
    instead of being deleted.

Cloud-Aware Date Selection (S2 / Landsat):
  - Whole-scene metadata (CLOUDY_PIXEL_PERCENTAGE, CLOUD_COVER) can hide a
    fully-clouded parcel inside an otherwise-clear tile, so it is NOT used
    to decide which date to keep.
  - Instead, for each of the most recent MAX_DATES_TO_CHECK acquisition dates
    (newest first), the actual cloud fraction is computed directly over the
    site's AOI (SCL band for S2, QA_PIXEL bits for Landsat). The first date
    with less than CLOUD_THRESHOLD % cloud cover ON THE AOI is used.
  - Override the default (20%) with --cloud-threshold when running the script.

Naming pattern:
  AWAM_[SOURCE]_[SITE]_[PARCEL_ID]_[DATATYPE]_[STARTDATE]_[ENDDATE]_v[VERSION].[EXT]

Outputs:
  outputs/latest_rasters/AWAM_*.tif
  outputs/archive_rasters/AWAM_*.tif (Archived rasters for Cloudinary storage)
  outputs/latest_rasters/manifest_latest_rasters.json

Author: GeoAI / WWC Internship
================================================================================
"""

import sys
import os
import json
import time
import io
import math
import argparse
import shutil
import urllib.request
import zipfile
from pathlib import Path
from datetime import datetime, timezone

# Force UTF-8 encoding for Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

EXTRACT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = EXTRACT_DIR.parent if EXTRACT_DIR.name == "EXTRACT" else EXTRACT_DIR
RASTER_OUTPUT_DIR = SCRIPTS_DIR / "outputs" / "latest_rasters"
ARCHIVE_OUTPUT_DIR = SCRIPTS_DIR / "outputs" / "archive_rasters"
MANIFEST_FILE = RASTER_OUTPUT_DIR / "manifest_latest_rasters.json"

PARCELLES_DIR   = SCRIPTS_DIR / "parcelles_geojson"
GEOJSON_ALL     = PARCELLES_DIR / "AWAM_TERRAIN_ALL_ALL_Boundaries_20250501_20260828_v1.0.geojson"
GEOJSON_MAKTHAR = PARCELLES_DIR / "AWAM_TERRAIN_makthar_ALL_Boundaries_20250501_20260828_v1.0.geojson"
GEOJSON_SIDI    = PARCELLES_DIR / "AWAM_TERRAIN_sidi-mechreg_ALL_Boundaries_20250501_20260828_v1.0.geojson"

VERSION = "1.0"

# Maximum cloud cover (%) tolerated, measured ACTUALLY over the site's AOI
# (not the whole-scene/tile metadata, which can hide localized clouds sitting
# right over the parcel while the rest of the tile is clear).
CLOUD_THRESHOLD = 20
# How many of the most recent acquisition dates to check before giving up.
MAX_DATES_TO_CHECK = 10

# Load .env variables
ENV_PATH = EXTRACT_DIR / ".env"
if not ENV_PATH.exists():
    ENV_PATH = SCRIPTS_DIR / ".env"

if ENV_PATH.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH)
    except ImportError:
        pass

GEE_PROJECT = os.getenv("GEE_PROJECT", "awam-504508")

# ── SL2P fCover Neural Network parameters ──
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


def ensure_output_dirs():
    """Ensures output directories for latest rasters and archived rasters exist."""
    RASTER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def build_filename(source, site, parcel_id, datatype, start_date, end_date, version=VERSION, ext="tif"):
    """
    Constructs standardized raster filename:
    AWAM_[SOURCE]_[SITE]_[PARCEL_ID]_[DATATYPE]_[STARTDATE]_[ENDDATE]_v[VERSION].[EXT]
    """
    clean_site = site.replace("-", "_").lower()
    s_date = start_date.replace("-", "")
    e_date = end_date.replace("-", "")
    return f"AWAM_{source}_{clean_site}_{parcel_id}_{datatype}_{s_date}_{e_date}_v{version}.{ext}"


def prepare_raster_download(source, site, parcel_id, datatype, date_str):
    """
    Smart Check & Archiving Logic:
    1. Checks if the exact raster for this date already exists and is non-empty.
       If it exists, return (out_path, False) to SKIP GEE download.
    2. If a newer date is being downloaded and an older raster for the same
       (source, site, parcel_id, datatype) exists in latest_rasters/, move the
       older raster to archive_rasters/ (for Cloudinary sync) instead of deleting it.
    """
    ensure_output_dirs()
    out_name = build_filename(source, site, parcel_id, datatype, date_str, date_str)
    out_path = RASTER_OUTPUT_DIR / out_name
    archive_path = ARCHIVE_OUTPUT_DIR / out_name

    # 1. Exact match check
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path, False

    if archive_path.exists() and archive_path.stat().st_size > 0:
        # Copy back to latest_rasters if present in archive
        try:
            shutil.copy2(archive_path, out_path)
            return out_path, False
        except Exception:
            pass

    # 2. Archive older versions matching (source, site, parcel_id, datatype)
    clean_site = site.replace("-", "_").lower()
    prefix = f"AWAM_{source}_{clean_site}_{parcel_id}_{datatype}_"
    for old_file in list(RASTER_OUTPUT_DIR.glob(f"{prefix}*.tif")):
        if old_file.name != out_name:
            dest = ARCHIVE_OUTPUT_DIR / old_file.name
            try:
                shutil.move(str(old_file), str(dest))
                print(f"\n       📦 Ancien raster archivé : {old_file.name} -> archive_rasters/")
            except Exception as e:
                print(f"\n       ⚠️ Erreur lors de l'archivage de {old_file.name} : {e}")

    return out_path, True


def load_parcels_bounds():
    """Reads parcel GeoJSON files to extract bounding boxes and metadata per site."""
    try:
        import geopandas as gpd
        sites = {}
        for site_name, path in [("makthar", GEOJSON_MAKTHAR), ("sidi-mechreg", GEOJSON_SIDI)]:
            if path.exists():
                gdf = gpd.read_file(path)
                bounds = list(gdf.total_bounds)  # [minx, miny, maxx, maxy]
                sites[site_name] = {
                    "bounds": bounds,
                    "num_parcels": len(gdf),
                    "geojson": str(path),
                }
        return sites
    except Exception as e:
        print(f"⚠️ Warning loading GeoJSON bounds: {e}")
        return {}


def download_geotiff(image, geometry, scale, output_path):
    """Downloads an ee.Image directly as a GeoTIFF using GEE URL API."""
    import ee
    try:
        url = image.getDownloadURL({
            'region': geometry,
            'scale': scale,
            'crs': 'EPSG:4326',
            'format': 'GEO_TIFF'
        })
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            content = resp.read()

        # Handle zip format if returned by GEE
        if content.startswith(b'PK'):
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                for name in z.namelist():
                    if name.endswith('.tif') or name.endswith('.tiff'):
                        with open(output_path, 'wb') as f:
                            f.write(z.read(name))
                        return True
        else:
            with open(output_path, 'wb') as f:
                f.write(content)
            return True
    except Exception as e:
        print(f"\n     ✗ Erreur lors du téléchargement de {output_path.name} : {e}")
        return False


def get_aoi_cloud_percentage(cloud_mask, geometry, scale):
    """
    Computes the REAL % of cloudy pixels within `geometry`, from a boolean
    cloud_mask image (1 = cloud/shadow, 0 = clear). This is what actually
    matters for the exported crop, unlike whole-scene metadata properties
    like CLOUDY_PIXEL_PERCENTAGE or CLOUD_COVER.
    """
    import ee
    stats = (
        cloud_mask.rename("cloud")
        .reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=scale,
            maxPixels=1e9,
            bestEffort=True,
            tileScale=4,
        )
        .getInfo()
    )
    frac = stats.get("cloud")
    if frac is None:
        # No valid pixels found (e.g. totally masked/off-swath over the AOI)
        return 100.0
    return round(frac * 100, 2)


def s2_cloud_mask(image):
    """Boolean cloud/shadow/cirrus mask for Sentinel-2 SR, from the SCL band."""
    scl = image.select("SCL")
    return (
        scl.eq(3)   # cloud shadow
        .Or(scl.eq(8))   # cloud, medium probability
        .Or(scl.eq(9))   # cloud, high probability
        .Or(scl.eq(10))  # thin cirrus
    )


def landsat_cloud_mask(image):
    """Boolean cloud/shadow/cirrus mask for Landsat C2 L2, from QA_PIXEL bits."""
    qa = image.select("QA_PIXEL")
    cloud = qa.bitwiseAnd(1 << 3).neq(0)
    shadow = qa.bitwiseAnd(1 << 4).neq(0)
    cirrus = qa.bitwiseAnd(1 << 2).neq(0)
    return cloud.Or(shadow).Or(cirrus)


def find_latest_clear_date(base_collection, geometry, cloud_mask_fn, scale,
                            cloud_threshold=CLOUD_THRESHOLD, max_dates_to_check=MAX_DATES_TO_CHECK):
    """
    Walks backward through the most recent acquisition dates of `base_collection`
    (already filtered by bounds, NOT by date) and returns the first date whose
    ACTUAL cloud cover measured inside `geometry` is below `cloud_threshold`.

    Returns: (date_str, mosaic_image, first_image_of_day, cloud_pct)
             or (None, None, None, None) if nothing qualifies.
    """
    import ee

    sorted_col = base_collection.sort("system:time_start", False).limit(50)
    timestamps = sorted_col.aggregate_array("system:time_start").getInfo()

    seen_dates = []
    for t in timestamps:
        d = datetime.fromtimestamp(t / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if d not in seen_dates:
            seen_dates.append(d)
        if len(seen_dates) >= max_dates_to_check:
            break

    for date_str in seen_dates:
        d_start = ee.Date(date_str)
        d_end = d_start.advance(1, "day")
        day_col = base_collection.filterDate(d_start, d_end)
        mosaic = day_col.mosaic()

        cloud_pct = get_aoi_cloud_percentage(cloud_mask_fn(mosaic), geometry, scale)
        print(f"       …vérification {date_str} : {cloud_pct:.1f}% de nuages sur la zone d'intérêt")

        if cloud_pct < cloud_threshold:
            first_of_day = ee.Image(day_col.sort("system:time_start", False).first())
            return date_str, mosaic, first_of_day, cloud_pct

    return None, None, None, None


def compute_s2_all_indices(image):
    """Computes all S2 indices matching database pipeline."""
    import ee
    scl = image.select("SCL")
    clear = (scl.eq(4).Or(scl.eq(5)).Or(scl.eq(2)).Or(scl.eq(6)).Or(scl.eq(7)).Or(scl.eq(11)))
    img = image.updateMask(clear).divide(10000.0)

    b2, b3, b4, b5 = img.select("B2"), img.select("B3"), img.select("B4"), img.select("B5")
    b7, b8, b11, b12 = img.select("B7"), img.select("B8"), img.select("B11"), img.select("B12")

    indices = {
        "RGB": img.select(["B4", "B3", "B2"]),
        "NDVI": b8.subtract(b4).divide(b8.add(b4)).rename("NDVI"),
        "SAVI": b8.subtract(b4).divide(b8.add(b4).add(0.428)).multiply(1.428).rename("SAVI"),
        "MSAVI": (b8.multiply(2).add(1).subtract((b8.multiply(2).add(1).pow(2).subtract(b8.subtract(b4).multiply(8))).sqrt())).divide(2).rename("MSAVI"),
        "EVI": b8.subtract(b4).multiply(2.5).divide(b8.add(b4.multiply(6)).subtract(b2.multiply(7.5)).add(1)).rename("EVI"),
        "NDRE": b8.subtract(b5).divide(b8.add(b5)).rename("NDRE"),
        "CI_RedEdge": b7.divide(b5).subtract(1).rename("CI_RedEdge"),
        "VARI": b3.subtract(b4).divide(b3.add(b4).subtract(b2)).rename("VARI"),
        "NDWI": b3.subtract(b8).divide(b3.add(b8)).rename("NDWI"),
        "NDMI": b8.subtract(b11).divide(b8.add(b11)).rename("NDMI"),
        "BSI": (b11.add(b4)).subtract(b8.add(b2)).divide((b11.add(b4)).add(b8.add(b2))).rename("BSI"),
        "Carbonate_SWIR": b11.divide(b12).rename("Carbonate_SWIR"),
        "NDSI_soil": b4.subtract(b11).divide(b4.add(b11)).rename("NDSI_soil"),
        "SI_soil": b4.multiply(b11).sqrt().rename("SI_soil"),
    }

    # SL2P fCover calculation
    coeffs = SL2P_FCOVER_COEFFS
    refl = img.select(SNAP_BANDS).toFloat()

    sun_zenith  = ee.Number(image.get("MEAN_SOLAR_ZENITH_ANGLE"))
    sun_azimuth = ee.Number(image.get("MEAN_SOLAR_AZIMUTH_ANGLE"))
    view_zenith = ee.List([image.get(f"MEAN_INCIDENCE_ZENITH_ANGLE_{b}") for b in SNAP_BANDS]).reduce(ee.Reducer.mean())
    view_azimuth = ee.List([image.get(f"MEAN_INCIDENCE_AZIMUTH_ANGLE_{b}") for b in SNAP_BANDS]).reduce(ee.Reducer.mean())

    deg2rad = math.pi / 180.0
    cos_vz  = ee.Number(view_zenith).multiply(deg2rad).cos()
    cos_sz  = sun_zenith.multiply(deg2rad).cos()
    cos_raz = sun_azimuth.subtract(ee.Number(view_azimuth)).multiply(deg2rad).cos()

    angle_img = ee.Image.constant([cos_vz, cos_sz, cos_raz]).rename(["cos_view_zenith", "cos_sun_zenith", "cos_rel_azimuth"]).toFloat()
    input_img = refl.addBands(angle_img).select(BAND_ORDER)

    norm_bands = []
    for i, band_name in enumerate(BAND_ORDER):
        b = input_img.select([band_name])
        nmin, nmax = coeffs["norm_min"][i], coeffs["norm_max"][i]
        norm_bands.append(b.subtract(nmin).divide(nmax - nmin).multiply(2).subtract(1).rename(f"n{i}"))
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

    out_denorm = out.add(1).multiply(0.5).multiply(coeffs["denorm_max"] - coeffs["denorm_min"]).add(coeffs["denorm_min"])
    indices["fCover"] = out_denorm.max(0).min(1).rename("fCover")

    return indices


def generate_manifest(dry_run=False):
    """Generates or updates manifest_latest_rasters.json metadata file."""
    ensure_output_dirs()
    sites_info = load_parcels_bounds()
    tif_files = list(RASTER_OUTPUT_DIR.glob("*.tif"))
    archive_files = list(ARCHIVE_OUTPUT_DIR.glob("*.tif"))
    
    raster_entries = []
    for tif in tif_files:
        raster_entries.append({
            "filename": tif.name,
            "path": str(tif),
            "size_bytes": tif.stat().st_size,
            "modified_time": datetime.fromtimestamp(tif.stat().st_mtime).isoformat(),
        })

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "status": "DRY_RUN" if dry_run else "LIVE",
        "naming_convention": "AWAM_[SOURCE]_[SITE]_[PARCEL_ID]_[DATATYPE]_[STARTDATE]_[ENDDATE]_v[VERSION].[EXT]",
        "version": VERSION,
        "raster_dir": str(RASTER_OUTPUT_DIR),
        "archive_dir": str(ARCHIVE_OUTPUT_DIR),
        "sites": sites_info,
        "rasters_count": len(raster_entries),
        "archived_rasters_count": len(archive_files),
        "rasters": raster_entries,
    }

    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"  ✅ Manifeste généré : {MANIFEST_FILE}")
    return manifest


def export_latest_rasters(dry_run=False, cloud_threshold=CLOUD_THRESHOLD):
    """Main routine to export latest cropped rasters via Earth Engine."""
    print("\n" + "=" * 80)
    print(" 🛰️ EXPORT DES RASTERS SATELLITES LES PLUS RÉCENTS (GeoTIFF & MANIFEST)")
    print("================================================================================\n")
    print(f" 🌤️ Seuil de nuages toléré sur la zone d'intérêt : {cloud_threshold}%\n")

    ensure_output_dirs()

    if dry_run:
        print("  [DRY-RUN] Mode vérification actif. Pas de téléchargement GEE.")
        return generate_manifest(dry_run=True)

    try:
        import ee
        ee.Initialize(project=GEE_PROJECT)
        print(f"  ✓ Google Earth Engine initialisé (Projet: {GEE_PROJECT}).\n")
    except Exception as e:
        print(f"  ⚠️ GEE non disponible ou non authentifié ({e}). Génération du manifeste seul.")
        return generate_manifest(dry_run=True)

    sites_info = load_parcels_bounds()
    parcel_id = "ALL"

    for site_name, s_info in sites_info.items():
        bbox = s_info["bounds"]
        # Buffer de 300m pour englober largement toutes les parcelles
        ee_geom = ee.Geometry.Rectangle(bbox).buffer(300).bounds()
        print(f"  📍 Site '{site_name}'...")

        # A. SENTINEL-2 (SOURCE = S2)
        try:
            s2_base_col = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(ee_geom)

            s2_date, s2_mosaic, first_s2, s2_cloud_pct = find_latest_clear_date(
                s2_base_col, ee_geom, s2_cloud_mask, scale=10, cloud_threshold=cloud_threshold
            )

            if s2_date is None:
                print(f"     ⚠️ Aucune image Sentinel-2 avec moins de {cloud_threshold}% de nuages sur la zone "
                      f"trouvée parmi les {MAX_DATES_TO_CHECK} dates les plus récentes.")
            else:
                print(f"     [Sentinel-2] Date retenue : {s2_date} ({s2_cloud_pct:.1f}% de nuages sur la zone)")

                latest_s2_raw = ee.Image(s2_mosaic.copyProperties(first_s2))
                s2_indices = compute_s2_all_indices(latest_s2_raw)

                for idx_name, img_band in s2_indices.items():
                    out_path, should_download = prepare_raster_download("S2", site_name, parcel_id, idx_name, s2_date)
                    print(f"       • {out_path.name}...", end=" ", flush=True)
                    if not should_download:
                        print("⏩ Déjà à jour (Téléchargement GEE sauté)")
                    else:
                        if download_geotiff(img_band, ee_geom, scale=10, output_path=out_path):
                            print("✓ Téléchargé avec succès")
        except Exception as e_s2:
            print(f"     ⚠️ Erreur Sentinel-2 : {e_s2}")

        # B. SENTINEL-1 (SOURCE = S1)
        try:
            s1_col = (
                ee.ImageCollection("COPERNICUS/S1_GRD")
                .filterBounds(ee_geom)
                .filter(ee.Filter.eq("instrumentMode", "IW"))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
                .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
                .sort("system:time_start", False)
            )
            first_s1 = s1_col.first()
            s1_date = ee.Date(first_s1.get("system:time_start")).format("YYYY-MM-dd").getInfo()
            print(f"     [Sentinel-1] Date la plus récente : {s1_date}")

            s1_date_start = ee.Date(s1_date)
            s1_date_end = s1_date_start.advance(1, "day")
            latest_s1 = (
                ee.ImageCollection("COPERNICUS/S1_GRD")
                .filterBounds(ee_geom)
                .filterDate(s1_date_start, s1_date_end)
                .filter(ee.Filter.eq("instrumentMode", "IW"))
                .mosaic()
            )

            vv = latest_s1.select("VV")
            vh = latest_s1.select("VH")
            vv_lin = ee.Image(10).pow(vv.divide(10))
            vh_lin = ee.Image(10).pow(vh.divide(10))

            s1_bands = {
                "VV_dB": vv.focalMedian(3, "square", "pixels").rename("VV_dB"),
                "VH_dB": vh.focalMedian(3, "square", "pixels").rename("VH_dB"),
                "VH_VV_ratio": vh_lin.divide(vv_lin).rename("VH_VV_ratio"),
                "DpRVIc": vh_lin.divide(vv_lin.add(vh_lin)).multiply(4).rename("DpRVIc"),
            }

            for s1_name, img_band in s1_bands.items():
                out_path, should_download = prepare_raster_download("S1", site_name, parcel_id, s1_name, s1_date)
                print(f"       • {out_path.name}...", end=" ", flush=True)
                if not should_download:
                    print("⏩ Déjà à jour (Téléchargement GEE sauté)")
                else:
                    if download_geotiff(img_band, ee_geom, scale=10, output_path=out_path):
                        print("✓ Téléchargé avec succès")
        except Exception as e_s1:
            print(f"     ⚠️ Erreur Sentinel-1 : {e_s1}")

        # C. LANDSAT 8/9 (SOURCE = LANDSAT)
        try:
            l8_base = ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterBounds(ee_geom)
            l9_base = ee.ImageCollection("LANDSAT/LC09/C02/T1_L2").filterBounds(ee_geom)
            landsat_base_col = l8_base.merge(l9_base)

            ls_date, latest_ls, first_ls, ls_cloud_pct = find_latest_clear_date(
                landsat_base_col, ee_geom, landsat_cloud_mask, scale=30, cloud_threshold=cloud_threshold
            )

            if ls_date is None:
                print(f"     ⚠️ Aucune image Landsat 8/9 avec moins de {cloud_threshold}% de nuages sur la zone "
                      f"trouvée parmi les {MAX_DATES_TO_CHECK} dates les plus récentes.")
            else:
                # Mask clouds, shadows, and fill pixels using QA_PIXEL
                qa = latest_ls.select("QA_PIXEL")
                qa_mask = (
                    qa.bitwiseAnd(1 << 0).eq(0)   # not fill
                    .And(qa.bitwiseAnd(1 << 1).eq(0))  # not dilated cloud
                    .And(qa.bitwiseAnd(1 << 3).eq(0))  # not cloud
                    .And(qa.bitwiseAnd(1 << 4).eq(0))  # not cloud shadow
                )
                masked_ls = latest_ls.updateMask(qa_mask)

                lst_c = masked_ls.select("ST_B10").multiply(0.00341802).add(149.0).subtract(273.15).rename("LST_C")
                sr_b4 = masked_ls.select("SR_B4").multiply(0.0000275).add(-0.2)
                sr_b5 = masked_ls.select("SR_B5").multiply(0.0000275).add(-0.2)

                # Valid reflectance mask to avoid division by near-zero outside swath/on fill
                valid_sr = sr_b4.gt(0).And(sr_b5.gt(0)).And(sr_b5.add(sr_b4).abs().gt(0.0001))
                ndvi_raw = sr_b5.subtract(sr_b4).divide(sr_b5.add(sr_b4))
                ndvi_ls = ndvi_raw.updateMask(valid_sr).clamp(-1.0, 1.0).rename("NDVI")

                for ls_name, img_band in [("LST_C", lst_c), ("NDVI", ndvi_ls)]:
                    out_path, should_download = prepare_raster_download("LANDSAT", site_name, parcel_id, ls_name, ls_date)
                    print(f"       • {out_path.name}...", end=" ", flush=True)
                    if not should_download:
                        print("⏩ Déjà à jour (Téléchargement GEE sauté)")
                    else:
                        if download_geotiff(img_band, ee_geom, scale=30, output_path=out_path):
                            print("✓ Téléchargé avec succès")
        except Exception as e_ls:
            print(f"     ⚠️ Erreur Landsat : {e_ls}")

        # D. MODIS (SOURCE = MODIS)
        try:
            modis_col = (
                ee.ImageCollection("MODIS/061/MOD11A1")
                .filterBounds(ee_geom)
                .sort("system:time_start", False)
            )
            first_modis = modis_col.first()
            mod_date = ee.Date(first_modis.get("system:time_start")).format("YYYY-MM-dd").getInfo()
            print(f"     [MODIS] Date la plus récente : {mod_date}")

            mod_date_start = ee.Date(mod_date)
            mod_date_end = mod_date_start.advance(1, "day")
            latest_modis = modis_col.filterDate(mod_date_start, mod_date_end).mosaic()

            modis_lst_c = latest_modis.select("LST_Day_1km").multiply(0.02).subtract(273.15).rename("LST_C")
            out_path, should_download = prepare_raster_download("MODIS", site_name, parcel_id, "LST_C", mod_date)
            print(f"       • {out_path.name}...", end=" ", flush=True)
            if not should_download:
                print("⏩ Déjà à jour (Téléchargement GEE sauté)")
            else:
                if download_geotiff(modis_lst_c, ee_geom, scale=1000, output_path=out_path):
                    print("✓ Téléchargé avec succès")
        except Exception as e_mod:
            print(f"     ⚠️ Erreur MODIS : {e_mod}")

        print()

    manifest = generate_manifest(dry_run=False)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export latest cropped satellite rasters following AWAM naming convention with Cloudinary archiving")
    parser.add_argument("--dry-run", action="store_true", help="Run without GEE network downloads")
    parser.add_argument(
        "--cloud-threshold", type=float, default=CLOUD_THRESHOLD,
        help=f"Max cloud cover %% tolerated, measured over the site AOI itself (default: {CLOUD_THRESHOLD})"
    )
    args = parser.parse_args()

    export_latest_rasters(dry_run=args.dry_run, cloud_threshold=args.cloud_threshold)