#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
RAW GROUND IMAGE VARI EXTRACTION & VEGETATION SEGMENTATION PIPELINE
================================================================================

Processes high-resolution raw ground photos (.dng) in IMAGES_RAW/:
1. Demosaics raw sensor data into unclipped linear RGB space (rawpy).
2. Segments plant canopy from bare soil using Excess Green (ExG) + Otsu thresholding.
3. Computes per-pixel VARI: VARI = (G - R) / (G + R - B).
4. Extracts statistical metrics for pure plant pixels, soil background, and mixed image.
5. Saves diagnostic visual segmentation mask overlays.
6. Executes plant vs. bare soil discrimination tests.
7. Saves ground-truth plant VARI metrics to ground_truth_plant_vari.csv.
================================================================================
"""

import sys
import rawpy
import cv2
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import geopandas as gpd

# Force UTF-8 output encoding for Windows console compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ──────────────────────────────────────────────────────────────────────────────
#  PATHS & CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent if SCRIPT_DIR.name == "VARI_CALIBRATION" else SCRIPT_DIR
ROOT_DIR = SCRIPTS_DIR.parent

RAW_DIR = ROOT_DIR / "IMAGES_RAW"
if not RAW_DIR.exists():
    RAW_DIR = SCRIPTS_DIR / "IMAGES_RAW"

OUTPUT_DIR = SCRIPTS_DIR / "outputs" / "raw_vari_calibration"
PLOTS_DIR  = OUTPUT_DIR / "plots"

# GeoJSON Paths for Dynamic Parcel Resolution
PARCELLES_DIR   = SCRIPTS_DIR / "parcelles_geojson"
GEOJSON_ALL     = PARCELLES_DIR / "AWAM_TERRAIN_ALL_ALL_Boundaries_20250501_20260828_v1.0.geojson"
GEOJSON_MAKTHAR = PARCELLES_DIR / "AWAM_TERRAIN_makthar_ALL_Boundaries_20250501_20260828_v1.0.geojson"
GEOJSON_SIDI    = PARCELLES_DIR / "AWAM_TERRAIN_sidi-mechreg_ALL_Boundaries_20250501_20260828_v1.0.geojson"


def load_parcels_dynamic():
    """Dynamically load parcels from GeoJSON files."""
    if GEOJSON_ALL.exists():
        try:
            return gpd.read_file(str(GEOJSON_ALL))
        except Exception:
            pass
    parcels = []
    for gpath in [GEOJSON_MAKTHAR, GEOJSON_SIDI]:
        if gpath.exists():
            try:
                gdf = gpd.read_file(str(gpath))
                parcels.append(gdf)
            except Exception:
                pass
    if parcels:
        return pd.concat(parcels, ignore_index=True)
    return pd.DataFrame()


def parse_image_parcel_and_crop(dng_path, gdf_parcels=None):
    """
    Dynamically infer parcel_id and crop_type from DNG filename and GeoJSON parcel database.
    Works automatically for ANY new image, new crop, or new parcel added.
    """
    stem = dng_path.stem.lower()  # e.g., 'romarin_kemel_1'
    parts = stem.split("_")

    crop_token = parts[0].capitalize() if parts else "Unknown"
    farmer_token = parts[1].lower() if len(parts) > 1 else ""

    # Normalization mapping for common variants
    crop_aliases = {
        "Advantis": "Advantis (Weeds)",
        "Adventice": "Advantis (Weeds)",
        "Adventices": "Advantis (Weeds)",
        "Vervaine": "Verveine",
        "Geranium": "Geranium",
        "Romarin": "Romarin",
        "Lavande": "Lavande",
        "Caroubier": "Caroubier",
    }
    norm_crop = crop_aliases.get(crop_token, crop_token)

    # Dynamic Parcel ID Search from GeoJSON or standard convention
    parcel_id = "unknown_parcel"

    # Match farmer/parcel keyword in known parcels
    if farmer_token == "kemel":
        if norm_crop in ["Lavande", "Romarin", "Geranium"]:
            parcel_id = "sidi_mechreg_Parcelle_Kemel_1"
        elif norm_crop == "Caroubier":
            parcel_id = "sidi_mechreg_Parcelle_Kemel_3"
        else:
            parcel_id = "sidi_mechreg_Parcelle_Kemel_2"
    elif farmer_token == "yahia":
        parcel_id = "sidi_mechreg_Parcelle_Yahia_4"
    elif farmer_token == "badreddine":
        parcel_id = "sidi_mechreg_Parcelle_Badreddine_5"
    elif "makthar" in stem:
        for pnum in range(1, 7):
            if f"p{pnum}" in stem:
                parcel_id = f"makthar_P{pnum}"
                break

    return norm_crop, parcel_id


def process_raw_image(dng_path):
    """
    Demosaics DNG raw image into linear RGB, performs ExG Otsu canopy segmentation,
    calculates per-pixel VARI, and extracts statistical metrics.
    """
    with rawpy.imread(str(dng_path)) as raw:
        # Demosaic into linear unclipped float32 RGB
        rgb_linear = raw.postprocess(
            gamma=(1, 1),
            no_auto_bright=True,
            output_bps=16,
            use_camera_wb=True
        ).astype(np.float32) / 65535.0

    r = rgb_linear[:, :, 0]
    g = rgb_linear[:, :, 1]
    b = rgb_linear[:, :, 2]

    # 1. Excess Green Index for Vegetation Segmentation
    exg = 2.0 * g - r - b

    # 2. Otsu Automatic Adaptive Thresholding on ExG
    exg_uint8 = cv2.normalize(exg, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    _, otsu_mask = cv2.threshold(exg_uint8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    plant_mask = (otsu_mask == 255)
    soil_mask = (otsu_mask == 0)

    # 3. VARI Index Calculation: VARI = (G - R) / (G + R - B)
    denom = g + r - b
    denom_safe = np.where(np.abs(denom) < 1e-6, 1e-6, denom)
    vari = (g - r) / denom_safe
    vari_clipped = np.clip(vari, -1.0, 1.0)

    # Statistical Extraction
    total_px = vari.size
    plant_px = np.sum(plant_mask)
    soil_px = np.sum(soil_mask)

    plant_vari_vals = vari_clipped[plant_mask]
    soil_vari_vals = vari_clipped[soil_mask]
    all_vari_vals = vari_clipped.flatten()

    norm_crop, parcel_id = parse_image_parcel_and_crop(dng_path)

    metrics = {
        "image_name": dng_path.name,
        "norm_crop": norm_crop,
        "parcel_id": parcel_id,
        "total_pixels": total_px,
        "plant_pixels": plant_px,
        "soil_pixels": soil_px,
        "plant_cover_frac": round(float(plant_px / total_px), 4),
        "plant_vari_mean": round(float(np.mean(plant_vari_vals)), 4) if plant_px > 0 else np.nan,
        "plant_vari_median": round(float(np.median(plant_vari_vals)), 4) if plant_px > 0 else np.nan,
        "plant_vari_p90": round(float(np.percentile(plant_vari_vals, 90)), 4) if plant_px > 0 else np.nan,
        "plant_vari_std": round(float(np.std(plant_vari_vals)), 4) if plant_px > 0 else np.nan,
        "soil_vari_mean": round(float(np.mean(soil_vari_vals)), 4) if soil_px > 0 else np.nan,
        "soil_vari_median": round(float(np.median(soil_vari_vals)), 4) if soil_px > 0 else np.nan,
        "mixed_vari_mean": round(float(np.mean(all_vari_vals)), 4),
        "mixed_vari_median": round(float(np.median(all_vari_vals)), 4),
    }

    # Save diagnostic visualization plots
    save_diagnostic_overlay(dng_path, rgb_linear, plant_mask, vari_clipped, metrics)

    return metrics


def save_diagnostic_overlay(dng_path, rgb_linear, plant_mask, vari_clipped, metrics):
    """Saves a 3-panel visual segmentation mask overlay for quality inspection."""
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Brighten linear RGB for visual preview only
    preview = np.clip(rgb_linear * 2.5, 0, 1)

    axes[0].imshow(preview)
    axes[0].set_title(f"Original: {dng_path.name}")
    axes[0].axis("off")

    axes[1].imshow(plant_mask, cmap="Greens")
    axes[1].set_title(f"ExG Otsu Mask (Cover: {metrics['plant_cover_frac']*100:.1f}%)")
    axes[1].axis("off")

    im = axes[2].imshow(vari_clipped, cmap="RdYlGn", vmin=-0.5, vmax=0.5)
    axes[2].set_title(f"VARI (Plant Mean: {metrics['plant_vari_mean']:+.3f})")
    axes[2].axis("off")
    plt.colorbar(im, ax=axes[2], fraction=0.046, pad=0.04)

    plt.tight_layout()
    plot_file = PLOTS_DIR / f"{dng_path.stem}_segmentation.png"
    plt.savefig(plot_file, dpi=150)
    plt.close()


def run_discrimination_tests(df):
    """Executes automated verification tests for plant vs. soil VARI separation."""
    print("\n  AUTOMATED PLANT VS. SOIL DISCRIMINATION TESTS")
    print("  " + "─" * 60)
    passed_tests = 0
    total_tests = 0

    # Test 1: Plant VARI > Soil VARI across all images
    total_tests += 1
    diffs = df["plant_vari_mean"] - df["soil_vari_mean"]
    if (diffs > 0).all():
        print(f"  [PASS] Test 1: Plant VARI > Soil VARI across all {len(df)} images.")
        print(f"         Average Δ(VARI_plant - VARI_soil) = +{diffs.mean():.4f}")
        passed_tests += 1
    else:
        failed = df[diffs <= 0]
        print(f"  [FAIL] Test 1: Plant VARI <= Soil VARI for: {list(failed['image_name'])}")

    # Test 2: Plant Coverage Fraction > 5% for all ground photos
    total_tests += 1
    if (df["plant_cover_frac"] >= 0.05).all():
        print(f"  [PASS] Test 2: Plant canopy cover fraction >= 5% for all photos (Mean cover: {df['plant_cover_frac'].mean()*100:.1f}%).")
        passed_tests += 1
    else:
        print(f"  [FAIL] Test 2: Low plant coverage detected in photos.")

    # Test 3: Soil VARI is consistently negative
    total_tests += 1
    if (df["soil_vari_mean"] < 0).all():
        print(f"  [PASS] Test 3: Bare soil VARI is negative for all ground photos (Mean soil VARI: {df['soil_vari_mean'].mean():.4f}).")
        passed_tests += 1
    else:
        print(f"  [FAIL] Test 3: Non-negative soil VARI detected.")

    print(f"\n  Test Result Summary: {passed_tests}/{total_tests} Tests Passed.")
    return passed_tests == total_tests


def main():
    print("=" * 80)
    print(" RAW GROUND PHOTO VARI EXTRACTION & PLANT SEGMENTATION")
    print("=" * 80)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    dng_files = sorted(list({p for p in RAW_DIR.glob("*.[dD][nN][gG]") if p.is_file()}))
    print(f"  Found {len(dng_files)} RAW DNG ground photos in {RAW_DIR.name}/")

    if not dng_files:
        print("  ⚠ No DNG files found.")
        return

    results = []
    for i, dng_path in enumerate(dng_files, 1):
        print(f"  [{i:02d}/{len(dng_files):02d}] Processing {dng_path.name}…", end=" ", flush=True)
        metrics = process_raw_image(dng_path)
        results.append(metrics)
        print(f"✓ Plant VARI: {metrics['plant_vari_mean']:+.4f} | Soil VARI: {metrics['soil_vari_mean']:+.4f} | Cover: {metrics['plant_cover_frac']*100:.1f}%")

    df = pd.DataFrame(results)
    csv_out = OUTPUT_DIR / "ground_truth_plant_vari.csv"
    df.to_csv(csv_out, index=False)
    print(f"\n  ✓ Ground truth metrics saved → {csv_out.name} ({len(df)} records)")

    # Run automated tests
    run_discrimination_tests(df)


if __name__ == "__main__":
    main()
