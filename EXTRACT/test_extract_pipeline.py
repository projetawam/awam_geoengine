#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
TEST SUITE FOR SPATIAL EXTRACTION & CLEANING PIPELINE (scripts/EXTRACT)
================================================================================

Validates:
  1. Environment configuration (.env) & credentials loading
  2. Spatial geometries (GeoJSON parcels EPSG:4326)
  3. GeoParquet database integrity & date coverage (clean/*.parquet)
  4. Incremental start date discovery algorithm (find_max_existing_date)
  5. Non-destructive deduplication & cleaning logic (dedup_smart)
  6. Raster manifest generation & UI metadata schema (export_latest_rasters)

Author: GeoAI / WWC Internship
================================================================================
"""

import os
import sys
import json
import pytest
import pandas as pd
import geopandas as gpd
from pathlib import Path

EXTRACT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = EXTRACT_DIR.parent if EXTRACT_DIR.name == "EXTRACT" else EXTRACT_DIR

# Add scripts and EXTRACT directories to sys.path
for p in [str(EXTRACT_DIR), str(SCRIPTS_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import run_all_extractions as rae
import clean_extracted_data as ced
import export_latest_rasters as elr


def test_env_file_location_and_vars():
    """Verify that .env is located in scripts/EXTRACT/.env and contains required keys."""
    env_extract = EXTRACT_DIR / ".env"
    env_scripts = SCRIPTS_DIR / ".env"
    
    assert env_extract.exists() or env_scripts.exists(), "No .env file found in EXTRACT/ or scripts/"
    
    target_env = env_extract if env_extract.exists() else env_scripts
    content = target_env.read_text(encoding="utf-8")
    
    assert "GEE_PROJECT" in content, ".env missing GEE_PROJECT"
    assert "EARTHDATA_USERNAME" in content, ".env missing EARTHDATA_USERNAME"
    assert "EARTHDATA_PASSWORD" in content, ".env missing EARTHDATA_PASSWORD"


def test_geojson_parcels_exist_and_valid():
    """Verify GeoJSON parcel geometries exist in parcelles_geojson, parse correctly, and have 11 total parcels."""
    parcelles_dir = SCRIPTS_DIR / "parcelles_geojson"
    all_path = parcelles_dir / "AWAM_TERRAIN_ALL_ALL_Boundaries_20250501_20260828_v1.0.geojson"
    makthar_path = parcelles_dir / "AWAM_TERRAIN_makthar_ALL_Boundaries_20250501_20260828_v1.0.geojson"
    sidi_path = parcelles_dir / "AWAM_TERRAIN_sidi-mechreg_ALL_Boundaries_20250501_20260828_v1.0.geojson"
    
    assert parcelles_dir.exists(), f"parcelles_geojson directory missing: {parcelles_dir}"
    assert all_path.exists(), f"Master ALL GeoJSON missing: {all_path}"
    assert makthar_path.exists(), f"Makthar GeoJSON missing: {makthar_path}"
    assert sidi_path.exists(), f"Sidi Mechreg GeoJSON missing: {sidi_path}"
    
    gdf_all = gpd.read_file(all_path)
    gdf_m = gpd.read_file(makthar_path)
    gdf_s = gpd.read_file(sidi_path)
    
    assert len(gdf_all) == 11, f"Expected 11 parcels for ALL, found {len(gdf_all)}"
    assert len(gdf_m) == 6, f"Expected 6 parcels for Makthar, found {len(gdf_m)}"
    assert len(gdf_s) == 5, f"Expected 5 parcels for Sidi Mechreg, found {len(gdf_s)}"
    assert gdf_all.crs is not None, "ALL GeoJSON has no CRS"
    assert gdf_m.crs is not None, "Makthar GeoJSON has no CRS"
    assert gdf_s.crs is not None, "Sidi Mechreg GeoJSON has no CRS"


def test_clean_geoparquet_integrity():
    """Scan all clean GeoParquet files to verify they are uncorrupted and cover dates up to August 2026."""
    clean_dir = SCRIPTS_DIR / "outputs" / "pixel_indices_database" / "clean"
    assert clean_dir.exists(), f"Clean database directory missing: {clean_dir}"
    
    parquet_files = sorted(list(clean_dir.glob("*.parquet")))
    assert len(parquet_files) >= 10, f"Expected at least 10 clean parquet files, found {len(parquet_files)}"
    
    for f in parquet_files:
        gdf = gpd.read_parquet(f)
        assert not gdf.empty, f"Clean parquet file is empty: {f.name}"
        assert "parcel_id" in gdf.columns, f"Missing 'parcel_id' column in {f.name}"
        assert "date" in gdf.columns, f"Missing 'date' column in {f.name}"
        
        max_date = pd.to_datetime(gdf["date"]).max()
        assert max_date >= pd.Timestamp("2026-01-01"), f"Outdated parquet file {f.name}: max date {max_date}"


def test_incremental_date_calculation():
    """Verify find_max_existing_date() logic calculates a valid YYYY-MM-DD incremental start date."""
    clean_dir = SCRIPTS_DIR / "outputs" / "pixel_indices_database" / "clean"
    start_date = rae.find_max_existing_date(clean_dir)
    
    assert start_date is not None, "find_max_existing_date returned None"
    assert len(start_date) == 10, f"Invalid date format: {start_date}"
    assert start_date.startswith("2026-"), f"Unexpected start date year: {start_date}"


def test_dedup_smart_logic():
    """Verify dedup_smart() drops exact duplicates and averages conflicting observations."""
    dummy_data = pd.DataFrame({
        "parcel_id": ["P1", "P1", "P1"],
        "date": ["2026-08-15", "2026-08-15", "2026-08-15"],
        "NDVI": [0.50, 0.50, 0.60],  # row 0 & 1 are exact duplicates; row 2 conflicts
        "geometry": [None, None, None]
    })
    
    gdf_dummy = gpd.GeoDataFrame(dummy_data)
    key_cols = ["parcel_id", "date"]
    
    clean_gdf, n_exact, n_merged = ced.dedup_smart(gdf_dummy, key_cols)
    
    assert len(clean_gdf) == 1, "dedup_smart failed to merge rows sharing same key"
    assert clean_gdf.iloc[0]["NDVI"] == pytest.approx(0.55, abs=0.001), "dedup_smart averaging incorrect"



def test_manifest_raster_export_generation():
    """Verify generate_manifest() creates manifest_latest_rasters.json with valid UI schema and archive path."""
    manifest = elr.generate_manifest(dry_run=True)
    
    assert manifest is not None, "generate_manifest returned None"
    assert "generated_at" in manifest, "Missing 'generated_at' in manifest"
    assert "sites" in manifest, "Missing 'sites' in manifest"
    assert "archive_dir" in manifest, "Missing 'archive_dir' in manifest"
    assert "archived_rasters_count" in manifest, "Missing 'archived_rasters_count' in manifest"
    assert "makthar" in manifest["sites"], "Missing 'makthar' site in manifest"
    assert "sidi-mechreg" in manifest["sites"], "Missing 'sidi-mechreg' site in manifest"
    assert manifest["sites"]["makthar"]["num_parcels"] == 6
    assert manifest["sites"]["sidi-mechreg"]["num_parcels"] == 5
    
    manifest_path = SCRIPTS_DIR / "outputs" / "latest_rasters" / "manifest_latest_rasters.json"
    assert manifest_path.exists(), f"Manifest file not created on disk: {manifest_path}"


def test_prepare_raster_download_smart_skipping(tmp_path):
    """Verify prepare_raster_download() skips GEE network call if raster for exact date already exists."""
    elr.ensure_output_dirs()
    
    # Create a dummy existing raster for date 2026-08-20
    test_name = elr.build_filename("S2", "makthar", "ALL", "TEST_NDVI", "2026-08-20", "2026-08-20")
    test_path = elr.RASTER_OUTPUT_DIR / test_name
    test_path.write_bytes(b"DUMMY_TIFF_CONTENT")
    
    try:
        out_path, should_download = elr.prepare_raster_download("S2", "makthar", "ALL", "TEST_NDVI", "2026-08-20")
        assert not should_download, "prepare_raster_download failed to skip download for existing image"
        assert out_path == test_path
    finally:
        if test_path.exists():
            test_path.unlink()


def test_prepare_raster_download_archiving(tmp_path):
    """Verify prepare_raster_download() moves older raster to outputs/archive_rasters/ when a newer date is fetched."""
    elr.ensure_output_dirs()
    
    # Create an old raster for date 2026-08-10
    old_name = elr.build_filename("S2", "makthar", "ALL", "TEST_ARCHIVE", "2026-08-10", "2026-08-10")
    old_path = elr.RASTER_OUTPUT_DIR / old_name
    old_path.write_bytes(b"OLD_RASTER_DATA")
    
    archive_dest = elr.ARCHIVE_OUTPUT_DIR / old_name
    new_name = elr.build_filename("S2", "makthar", "ALL", "TEST_ARCHIVE", "2026-08-25", "2026-08-25")
    new_path = elr.RASTER_OUTPUT_DIR / new_name
    
    try:
        out_path, should_download = elr.prepare_raster_download("S2", "makthar", "ALL", "TEST_ARCHIVE", "2026-08-25")
        assert should_download, "prepare_raster_download should request download for new date"
        assert archive_dest.exists(), "Older raster was not moved to outputs/archive_rasters/"
        assert not old_path.exists(), "Older raster still remains in latest_rasters/ after archiving"
    finally:
        if new_path.exists():
            new_path.unlink()
        if old_path.exists():
            old_path.unlink()
        if archive_dest.exists():
            archive_dest.unlink()

