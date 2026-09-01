#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
UNIFIED GROUND-TO-SATELLITE VARI EXTRACTION & CALIBRATION PIPELINE
================================================================================

Master end-to-end pipeline:
1. (Optional) Runs the full extraction pipeline (GEE + Earthdata + Cleaning).
2. Scans IMAGES_RAW/ for new or updated .dng ground photos.
3. Extracts pure plant VARI, soil VARI, and plant canopy cover.
4. Handles multi-plantation intercropped parcels via species-weighted unmixing.
5. Recalibrates Sentinel-2 satellite pixels using clean GeoParquet database.
6. Runs automated verification tests and prints a comprehensive calibration report.

Usage:
  python scripts/VARI_CALIBRATION/run_vari_pipeline.py                  # Run ground extraction + calibration
  python scripts/VARI_CALIBRATION/run_vari_pipeline.py --skip-ground    # Skip DNG photo processing (re-calibrate only)
  python scripts/VARI_CALIBRATION/run_vari_pipeline.py --run-extractions # Run full data extraction before calibration
================================================================================
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path

# Force UTF-8 output encoding for Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent if SCRIPT_DIR.name == "VARI_CALIBRATION" else SCRIPT_DIR
ROOT_DIR = SCRIPTS_DIR.parent

# Sub-script execution paths
RUN_EXTRACTIONS_SCRIPT = SCRIPTS_DIR / "EXTRACT" / "run_all_extractions.py"
EXTRACT_GROUND_SCRIPT  = SCRIPT_DIR / "extract_raw_images_vari.py"
CALIBRATE_S2_SCRIPT    = SCRIPT_DIR / "calibrate_sentinel2_vari.py"


def run_step(script_path, description):
    """Run a pipeline sub-script with unbuffered real-time output."""
    print(f"\n" + "=" * 80, flush=True)
    print(f" STEP: {description}", flush=True)
    print("=" * 80, flush=True)

    if not script_path.exists():
        print(f"  ❌ Script not found: {script_path}", flush=True)
        return False

    child_env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    cmd = [sys.executable, "-u", str(script_path)]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=0,
        cwd=str(ROOT_DIR),
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

    if process.returncode != 0:
        print(f"\n  ❌ Failed executing {description}", flush=True)
        return False
    print(f"\n  ✅ Finished {description}", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Unified VARI Extraction & Satellite Calibration Pipeline"
    )
    parser.add_argument(
        "--run-extractions", action="store_true",
        help="Run full data extraction pipeline (GEE + Earthdata + Cleaning) before calibration"
    )
    parser.add_argument(
        "--skip-ground", action="store_true",
        help="Skip Step 1 (ground photo DNG processing) and only re-run calibration"
    )
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════════════════════════════════════╗", flush=True)
    print("║   UNIFIED VARI EXTRACTION & SATELLITE CALIBRATION PIPELINE                   ║", flush=True)
    print("╚══════════════════════════════════════════════════════════════════════════════╝", flush=True)

    # Step 0 (Optional): Run full data extraction pipeline
    if args.run_extractions:
        success0 = run_step(
            RUN_EXTRACTIONS_SCRIPT,
            "0. Full Data Extraction Pipeline (GEE + Earthdata + Cleaning)"
        )
        if not success0:
            return

    # Step 1: Extract ground-truth VARI metrics from RAW DNG photos
    if not args.skip_ground:
        success1 = run_step(
            EXTRACT_GROUND_SCRIPT,
            "1. Ground Photo RAW DNG Processing & VARI Extraction"
        )
        if not success1:
            return

    # Step 2: Calibrate Sentinel-2 satellite pixels using ground truth
    success2 = run_step(
        CALIBRATE_S2_SCRIPT,
        "2. Sentinel-2 Sub-Pixel Unmixing & Satellite Calibration"
    )
    if not success2:
        return

    print("\n" + "═" * 80, flush=True)
    print(" 🎉 UNIFIED VARI CALIBRATION PIPELINE COMPLETED SUCCESSFULLY", flush=True)
    print("═" * 80, flush=True)


if __name__ == "__main__":
    main()
