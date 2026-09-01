#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
MASTER EXTRACTION & CLEANING PIPELINE ORCHESTRATOR
================================================================================

Runs all data extractions and cleaning sequentially:

  Phase 1: GEE Extraction (Sentinel-2, Sentinel-1, MODIS LST, Landsat 8/9, ERA5)
           → outputs/pixel_indices_database/raw/AWAM_GEE_*.parquet

  Phase 2: Earthdata Extraction (ECOSTRESS LST, NISAR Soil Moisture, NISAR Backscatter)
           → outputs/pixel_indices_database/raw/AWAM_Earthdata_*.parquet

  Phase 3: Data Cleaning & Validation Pipeline
           → outputs/pixel_indices_database/clean/AWAM_*_clean.parquet
           → outputs/pixel_indices_database/clean/cleaning_report.md

Usage:
  python run_all_extractions.py [--skip-gee] [--skip-earthdata] [--skip-clean]

Author: GeoAI / WWC Internship
================================================================================
"""

import sys
import os
import time
import argparse
import subprocess
from pathlib import Path

# Force UTF-8 output encoding for Windows terminal compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

EXTRACT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = EXTRACT_DIR.parent if EXTRACT_DIR.name == "EXTRACT" else EXTRACT_DIR
GEE_SCRIPT = EXTRACT_DIR / "gee_export_pixel_indices_database.py"
EARTHDATA_SCRIPT = EXTRACT_DIR / "earthdata_export_pixel_indices_database.py"
CLEAN_SCRIPT = EXTRACT_DIR / "clean_extracted_data.py"

RAW_DIR = SCRIPTS_DIR / "outputs" / "pixel_indices_database" / "raw"
CLEAN_DIR = SCRIPTS_DIR / "outputs" / "pixel_indices_database" / "clean"


def run_subscript(script_path, label, extra_args=None):
    """Execute a python script in a subprocess and stream logs in real-time."""
    print("\n" + "═" * 80)
    print(f"   STARTING PHASE: {label}")
    print(f"   Script: {script_path.name}")
    print("═" * 80 + "\n", flush=True)

    if not script_path.exists():
        print(f"  ❌ Error: Script not found at {script_path}", flush=True)
        return False

    t_start = time.perf_counter()

    # Pass -u flag for unbuffered stdout/stderr in child process
    cmd = [sys.executable, "-u", str(script_path)]
    if extra_args:
        cmd.extend(extra_args)
    child_env = {**os.environ, "PYTHONUNBUFFERED": "1"}

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=0,
            env=child_env,
        )

        while True:
            char = process.stdout.read(1)
            if not char and process.poll() is not None:
                break
            if char:
                sys.stdout.write(char)
                sys.stdout.flush()

        process.wait()

        elapsed = time.perf_counter() - t_start

        if process.returncode == 0:
            print(f"\n  ✅ {label} completed successfully in {elapsed:.1f} s", flush=True)
            return True
        else:
            print(f"\n  ❌ {label} failed with exit code {process.returncode} after {elapsed:.1f} s", flush=True)
            return False

    except Exception as e:
        print(f"\n  ❌ Failed to execute {script_path.name}: {e}", flush=True)
        return False


RASTER_SCRIPT = EXTRACT_DIR / "export_latest_rasters.py"


def find_max_existing_date(clean_dir):
    """Finds the safest start date across clean GeoParquet files to determine incremental delta start."""
    try:
        import pandas as pd
        file_maxes = []
        if clean_dir.exists():
            for f in clean_dir.glob("*.parquet"):
                try:
                    df = pd.read_parquet(f, columns=["date"])
                    if "date" in df.columns and not df["date"].empty:
                        f_max = pd.to_datetime(df["date"]).max()
                        file_maxes.append(f_max)
                except Exception:
                    pass
        if file_maxes:
            overall_max = max(file_maxes)
            # Only consider max dates within 30 days of the latest file to avoid being dragged back by dormant sensors
            recent_maxes = [d for d in file_maxes if (overall_max - d).days <= 30]
            safest_date = min(recent_maxes) if recent_maxes else overall_max
            return safest_date.strftime("%Y-%m-%d")
    except Exception as e:
        print(f"⚠️ Warning finding max date: {e}")
    return None




def main():
    parser = argparse.ArgumentParser(description="Master Orchestrator for AWAM Data Extraction & Cleaning Pipeline")
    parser.add_argument("--incremental", "-i", action="store_true", help="Incremental mode: only fetch new dates since max date in clean/")
    parser.add_argument("--start-date", type=str, default=None, help="Explicit start date YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=None, help="Explicit end date YYYY-MM-DD")
    parser.add_argument("--skip-gee", action="store_true", help="Skip GEE extraction phase")
    parser.add_argument("--skip-earthdata", action="store_true", help="Skip Earthdata extraction phase")
    parser.add_argument("--skip-clean", action="store_true", help="Skip data cleaning phase")
    parser.add_argument("--skip-rasters", action="store_true", help="Skip latest raster export phase")
    parser.add_argument("--nisar-only", action="store_true", help="Run only NISAR extractions (skip GEE and ECOSTRESS)")
    parser.add_argument("--backscatter-only", action="store_true", help="Run only NISAR GCOV Backscatter (skip GEE, ECOSTRESS, and Soil Moisture)")
    parser.add_argument("--stream", action="store_true", help="EXPERIMENTAL: stream NISAR granules over HTTPS instead of downloading them whole")
    args = parser.parse_args()

    if args.nisar_only or args.backscatter_only:
        args.skip_gee = True

    computed_start_date = args.start_date
    if args.incremental and not computed_start_date:
        max_date = find_max_existing_date(CLEAN_DIR)
        if max_date:
            computed_start_date = max_date
            print(f"  [INCREMENTAL MODE] Auto-detected max existing clean date: {max_date}. Extracting delta starting from {computed_start_date}.")

    banner = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║   MASTER DATA EXTRACTION & CLEANING ORCHESTRATOR — v2 GeoParquet           ║
║   Project AWAM — Tunisia                                                   ║
║   Mode: {'INCREMENTAL DELTA REFRESH' if args.incremental else 'FULL PERIOD EXTRACTION':<59s}║
║   Sentinel-2 · Sentinel-1 · MODIS · Landsat · ERA5 · ECOSTRESS · NISAR      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
    print(banner)
    t_global = time.perf_counter()

    success_gee = True
    success_earthdata = True
    success_clean = True
    success_rasters = True

    date_args = []
    if computed_start_date:
        date_args.extend(["--start-date", computed_start_date])
    if args.end_date:
        date_args.extend(["--end-date", args.end_date])

    # ── Phase 1: GEE Extractions ──
    if not args.skip_gee:
        success_gee = run_subscript(GEE_SCRIPT, "Phase 1: GEE Extractions", extra_args=date_args if date_args else None)
    else:
        print("\n  [Skipping Phase 1: GEE Extractions]")

    # ── Phase 2: Earthdata Extractions ──
    if not args.skip_earthdata:
        mode_flag = "--backscatter-only" if args.backscatter_only else ("--nisar-only" if args.nisar_only else None)
        extra = [f for f in [mode_flag, "--stream" if args.stream else None] if f]
        if date_args:
            extra.extend(date_args)
        success_earthdata = run_subscript(EARTHDATA_SCRIPT, "Phase 2: Earthdata Extractions", extra_args=extra or None)
    else:
        print("\n  [Skipping Phase 2: Earthdata Extractions]")

    # ── Phase 3: Data Cleaning ──
    if not args.skip_clean:
        clean_extra = ["--append"] if args.incremental else None
        success_clean = run_subscript(CLEAN_SCRIPT, "Phase 3: Data Cleaning & Validation", extra_args=clean_extra)
    else:
        print("\n  [Skipping Phase 3: Data Cleaning & Validation]")

    # ── Phase 4: Export Latest Rasters for UI ──
    if not args.skip_rasters and RASTER_SCRIPT.exists():
        success_rasters = run_subscript(RASTER_SCRIPT, "Phase 4: Export Latest Satellite Rasters & Manifest")
    else:
        print("\n  [Skipping Phase 4: Export Latest Satellite Rasters]")

    # ── Final Summary ──
    elapsed_total = time.perf_counter() - t_global

    print("\n" + "═" * 80)
    print("   FINAL PIPELINE SUMMARY REPORT")
    print("═" * 80)
    print(f"  Phase 1 (GEE Extractions)       : {'✅ SUCCESS' if success_gee else '❌ FAILED'}")
    print(f"  Phase 2 (Earthdata Extractions) : {'✅ SUCCESS' if success_earthdata else '❌ FAILED'}")
    print(f"  Phase 3 (Data Cleaning)         : {'✅ SUCCESS' if success_clean else '❌ FAILED'}")
    print(f"  Phase 4 (Latest Raster Export)  : {'✅ SUCCESS' if success_rasters else '❌ FAILED'}")
    print(f"  Total Duration                  : {elapsed_total:.1f} s\n")

    print("  RAW GEOPARQUET FILES (outputs/pixel_indices_database/raw/):")
    if RAW_DIR.exists():
        raw_files = sorted(list(RAW_DIR.glob("*.parquet")))
        if raw_files:
            for f in raw_files:
                size_mb = f.stat().st_size / (1024 * 1024)
                print(f"    • {f.name:<65s} {size_mb:>6.2f} MB")
        else:
            print("    (no files found)")
    else:
        print("    (directory not created)")

    print("\n  CLEAN GEOPARQUET FILES (outputs/pixel_indices_database/clean/):")
    if CLEAN_DIR.exists():
        clean_files = sorted(list(CLEAN_DIR.glob("*.parquet")))
        if clean_files:
            for f in clean_files:
                size_mb = f.stat().st_size / (1024 * 1024)
                print(f"    • {f.name:<65s} {size_mb:>6.2f} MB")
        else:
            print("    (no files found)")

        rep_file = CLEAN_DIR / "cleaning_report.md"
        if rep_file.exists():
            print(f"\n  📄 Cleaning Report: {rep_file}")
    else:
        print("    (directory not created)")

    print("\n═" * 80 + "\n")


if __name__ == "__main__":
    main()