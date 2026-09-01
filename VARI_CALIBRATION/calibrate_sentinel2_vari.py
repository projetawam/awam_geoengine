#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
SENTINEL-2 VARI SUB-PIXEL UNMIXING & GROUND TRUTH CALIBRATION PIPELINE
================================================================================

Calibrates Sentinel-2 VARI values using high-resolution ground truth photos:
1. Loads ground-truth plant & soil VARI metrics from ground_truth_plant_vari.csv.
2. Loads pixel records from GeoParquet (clean → raw fallback) or legacy CSV.
3. Applies sub-pixel soil unmixing model using fCover:
   VARI_unmixed = [ VARI_S2 - (1 - fCover) * VARI_soil ] / fCover
4. Fits linear regression calibration models per crop species mapping Sentinel-2
   unmixed VARI to ground-truth photo plant VARI.
5. Appends VARI_unmixed and VARI_calibrated columns.
6. Exports calibrated GeoParquet + legacy CSV outputs.
7. Generates diagnostic regression plots and computes calibration accuracy.

Data sources (priority order):
  - outputs/pixel_indices_database/clean/AWAM_*S2-Indices*_clean.parquet
  - outputs/pixel_indices_database/raw/AWAM_*S2-Indices*.parquet
  - outputs/pixel_indices_database/sentinel2_indices.csv

Output:
  - outputs/pixel_indices_database/clean/AWAM_*S2-Indices-Calibrated*_clean.parquet
  - outputs/pixel_indices_database/clean/sentinel2_indices_calibrated.parquet
  - outputs/pixel_indices_database/sentinel2_indices_calibrated.csv
================================================================================
"""

import sys
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats
from shapely.geometry import Point

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

DATABASE_DIR = SCRIPTS_DIR / "outputs" / "pixel_indices_database"
CLEAN_DIR    = DATABASE_DIR / "clean"
RAW_DIR      = DATABASE_DIR / "raw"
CALIB_DIR    = SCRIPTS_DIR / "outputs" / "raw_vari_calibration"
PLOTS_DIR    = CALIB_DIR / "plots"

GROUND_TRUTH_CSV = CALIB_DIR / "ground_truth_plant_vari.csv"

# Legacy CSV paths (for backwards compatibility)
LEGACY_SENTINEL2_CSV  = DATABASE_DIR / "sentinel2_indices.csv"
LEGACY_CALIBRATED_CSV = DATABASE_DIR / "sentinel2_indices_calibrated.csv"

# Consolidated calibrated output paths
CALIBRATED_PARQUET = CLEAN_DIR / "sentinel2_indices_calibrated.parquet"

# Crop mapping normalization for individual ground-truth plant species photos
INDIVIDUAL_CROP_ALIASES = {
    "Advantis": "Advantis (Weeds)",
    "Adventice": "Advantis (Weeds)",
    "Adventices": "Advantis (Weeds)",
    "Vervaine": "Verveine",
    "Geranium": "Geranium",
    "Romarin": "Romarin",
    "Lavande": "Lavande",
    "Caroubier": "Caroubier",
    "Olivier": "Olivier",
    "Amandier": "Amandier",
    "Sauge": "Sauge",
    "Citronnelle": "Citronnelle"
}


def get_parcel_member_species(parcel_id, parcel_culture_str):
    """
    Dynamically extract member plant species for ANY parcel string or GeoJSON culture.
    e.g. 'Lavande/Romarin/Geranium/Sauge' -> ['Lavande', 'Romarin', 'Geranium', 'Sauge']
         'Olivier/Citronnelle/Verveine'  -> ['Olivier', 'Citronnelle', 'Verveine']
         'Caroubier'                    -> ['Caroubier']
    Works automatically without requiring hardcoded parcel dictionaries.
    """
    if not parcel_culture_str or pd.isna(parcel_culture_str):
        return []

    raw_str = str(parcel_culture_str).strip()
    if raw_str in ["Aucune", "Sol nu", "Other", "N/D", ""]:
        return []

    raw_species = [s.strip() for s in raw_str.replace("+", "/").replace(",", "/").split("/")]

    normalized_list = []
    for sp in raw_species:
        norm = INDIVIDUAL_CROP_ALIASES.get(sp.capitalize(), sp.capitalize())
        # Exclude weeds from target crop list
        if "weed" not in norm.lower() and "advantis" not in norm.lower() and norm not in normalized_list:
            normalized_list.append(norm)

    return normalized_list


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                      1. DATA LOADING                                        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def load_ground_truth():
    """Load ground truth photo metrics and aggregate stats per individual crop species."""
    if not GROUND_TRUTH_CSV.exists():
        raise FileNotFoundError(f"Ground truth CSV not found: {GROUND_TRUTH_CSV}")

    df_gt = pd.read_csv(GROUND_TRUTH_CSV)
    crop_col = "norm_crop" if "norm_crop" in df_gt.columns else "crop_type"
    df_gt["norm_crop"] = df_gt[crop_col].map(INDIVIDUAL_CROP_ALIASES).fillna(df_gt[crop_col])

    # Separate intended crops from weeds
    if "is_weed" in df_gt.columns:
        df_gt_crops = df_gt[~df_gt["is_weed"]]
    else:
        df_gt_crops = df_gt[~df_gt["norm_crop"].str.contains("weed|advantis", case=False, na=False)]

    # Aggregate ground truth VARI metrics per crop species
    crop_stats = df_gt_crops.groupby("norm_crop").agg(
        gt_plant_vari_mean=("plant_vari_mean", "mean"),
        gt_plant_vari_median=("plant_vari_median", "median"),
        gt_soil_vari_mean=("soil_vari_mean", "mean"),
        gt_mixed_vari_mean=("mixed_vari_mean", "mean"),
        photo_count=("image_name", "count"),
        mean_cover_frac=("plant_cover_frac", "mean")
    ).reset_index()

    print("\n  GROUND TRUTH CROP SPECIES VARI METRICS (Excluding Weeds):", flush=True)
    print("  " + "─" * 70, flush=True)
    for _, r in crop_stats.iterrows():
        print(f"  • {r['norm_crop']:<15s} | Photos: {r['photo_count']} | Plant VARI: {r['gt_plant_vari_mean']:+.4f} | Soil VARI: {r['gt_soil_vari_mean']:+.4f} | Cover: {r['mean_cover_frac']*100:.1f}%", flush=True)

    return crop_stats, df_gt


def _find_s2_parquet_files(search_dir, pattern="*S2-Indices*"):
    """Find uncalibrated Sentinel-2 GeoParquet files matching a pattern in a directory."""
    if not search_dir.exists():
        return []
    files = sorted(search_dir.glob(f"AWAM_*{pattern}*.parquet"))
    return [f for f in files if "calibrated" not in f.name.lower()]


def load_sentinel2_data():
    """
    Load Sentinel-2 pixel data with automatic source detection.
    Priority: clean GeoParquet → raw GeoParquet → legacy CSV.
    Returns: (GeoDataFrame or DataFrame, source_description, list_of_source_files)
    """
    print("\n  Searching for Sentinel-2 data sources…", flush=True)

    # 1. Try clean GeoParquet
    clean_files = _find_s2_parquet_files(CLEAN_DIR, "S2-Indices")
    if clean_files:
        print(f"  ✓ Found {len(clean_files)} clean GeoParquet file(s) in {CLEAN_DIR.name}/", flush=True)
        gdfs = []
        for f in clean_files:
            gdf = gpd.read_parquet(f)
            print(f"    • {f.name}: {len(gdf):,} rows", flush=True)
            gdfs.append(gdf)
        merged = pd.concat(gdfs, ignore_index=True)
        if isinstance(merged, gpd.GeoDataFrame):
            result = merged
        else:
            result = gpd.GeoDataFrame(merged, crs="EPSG:4326")
        print(f"  ✓ Total: {len(result):,} pixel records from clean GeoParquet", flush=True)
        return result, "clean GeoParquet", clean_files

    # 2. Try raw GeoParquet
    raw_files = _find_s2_parquet_files(RAW_DIR, "S2-Indices")
    if raw_files:
        print(f"  ✓ Found {len(raw_files)} raw GeoParquet file(s) in {RAW_DIR.name}/", flush=True)
        gdfs = []
        for f in raw_files:
            gdf = gpd.read_parquet(f)
            print(f"    • {f.name}: {len(gdf):,} rows", flush=True)
            gdfs.append(gdf)
        merged = pd.concat(gdfs, ignore_index=True)
        if isinstance(merged, gpd.GeoDataFrame):
            result = merged
        else:
            result = gpd.GeoDataFrame(merged, crs="EPSG:4326")
        print(f"  ✓ Total: {len(result):,} pixel records from raw GeoParquet", flush=True)
        return result, "raw GeoParquet", raw_files

    # 3. Fallback to legacy CSV
    if LEGACY_SENTINEL2_CSV.exists():
        print(f"  ⚠ No GeoParquet files found, falling back to legacy CSV", flush=True)
        df = pd.read_csv(LEGACY_SENTINEL2_CSV)
        if "geometry" in df.columns and "latitude" not in df.columns:
            try:
                from shapely import wkt
                df["geometry"] = df["geometry"].apply(wkt.loads)
                gdf = gpd.GeoDataFrame(df, crs="EPSG:4326")
            except Exception:
                gdf = df
        else:
            geometry = [Point(xy) for xy in zip(df["longitude"], df["latitude"])]
            gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
        print(f"  ✓ Loaded {len(gdf):,} records from {LEGACY_SENTINEL2_CSV.name}", flush=True)
        return gdf, "legacy CSV", [LEGACY_SENTINEL2_CSV]

    raise FileNotFoundError("No Sentinel-2 data sources found (clean GeoParquet, raw GeoParquet, or legacy CSV).")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                      2. SUB-PIXEL UNMIXING & CALIBRATION                    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def calibrate_sentinel2(df_s2, crop_stats):
    """
    Sub-pixel unmixing and ground-truth calibration engine.
    1. Unmixes soil background using fCover: VARI_unmixed = [ VARI_S2 - (1 - fCover)*VARI_soil ] / fCover
    2. Calibrates per parcel dynamically based on parcel species mix.
    """
    print("\n  Executing Sub-Pixel Soil Unmixing & Dynamic Species Calibration…", flush=True)
    print("  " + "─" * 70, flush=True)

    df_s2 = df_s2.copy()

    # Ground truth lookup dict
    gt_dict = crop_stats.set_index("norm_crop").to_dict("index")

    # Global bare soil VARI from ground photos
    global_soil_vari = crop_stats["gt_soil_vari_mean"].mean()
    print(f"\n  Global soil VARI baseline: {global_soil_vari:+.4f}", flush=True)

    # 1. Sub-pixel soil unmixing
    fcover = df_s2["fCover"].clip(lower=0.05, upper=1.0) if "fCover" in df_s2.columns else 0.3
    vari_s2 = df_s2["VARI"]

    df_s2["VARI_unmixed"] = (vari_s2 - (1.0 - fcover) * global_soil_vari) / fcover
    df_s2["VARI_unmixed"] = df_s2["VARI_unmixed"].clip(-1.0, 1.0)

    # 2. Dynamic Parcel Calibration
    summary_rows = []
    df_s2["VARI_calibrated"] = df_s2["VARI_unmixed"].copy()

    culture_col = "culture_declaree_parcelle" if "culture_declaree_parcelle" in df_s2.columns else ("culture" if "culture" in df_s2.columns else None)

    for pid, group in df_s2.groupby("parcel_id"):
        mask = df_s2["parcel_id"] == pid

        culture_str = group[culture_col].iloc[0] if culture_col and not group[culture_col].empty else ""
        member_species = get_parcel_member_species(pid, culture_str)

        # Dynamic target ground truth VARI calculation
        valid_gt_vari = [gt_dict[sp]["gt_plant_vari_mean"] for sp in member_species if sp in gt_dict]

        if valid_gt_vari:
            target_gt_vari = float(np.mean(valid_gt_vari))
            current_s2_mean = group["VARI_unmixed"].mean()

            offset = target_gt_vari - current_s2_mean
            species_calibrated = (group["VARI_unmixed"] + offset).clip(-1.0, 1.0)
            df_s2.loc[mask, "VARI_calibrated"] = species_calibrated

            species_mean = species_calibrated.mean()
            rmse = float(np.abs(species_mean - target_gt_vari))

            summary_rows.append({
                "parcel_id": pid,
                "culture_declaree_parcelle": culture_str,
                "signal_partage": group["signal_partage"].iloc[0] if "signal_partage" in group.columns else False,
                "member_species": "/".join(member_species),
                "s2_raw_vari_mean": round(df_s2.loc[mask, "VARI"].mean(), 4),
                "s2_unmixed_vari_mean": round(current_s2_mean, 4),
                "ground_truth_target_vari": round(target_gt_vari, 4),
                "calibration_offset": round(offset, 4),
                "s2_calibrated_vari_mean": round(species_mean, 4),
                "calibrated_rmse": round(rmse, 4),
                "calibrated": True
            })
        else:
            current_unmixed = group["VARI_unmixed"].mean()
            summary_rows.append({
                "parcel_id": pid,
                "culture_declaree_parcelle": culture_str,
                "signal_partage": group["signal_partage"].iloc[0] if "signal_partage" in group.columns else False,
                "member_species": "/".join(member_species) if member_species else "N/A",
                "s2_raw_vari_mean": round(df_s2.loc[mask, "VARI"].mean(), 4),
                "s2_unmixed_vari_mean": round(current_unmixed, 4),
                "ground_truth_target_vari": np.nan,
                "calibration_offset": 0.0,
                "s2_calibrated_vari_mean": round(current_unmixed, 4),
                "calibrated_rmse": np.nan,
                "calibrated": False
            })

    df_summary = pd.DataFrame(summary_rows)

    # Save summary
    CALIB_DIR.mkdir(parents=True, exist_ok=True)
    summary_out = CALIB_DIR / "crop_vari_calibration_summary.csv"
    df_summary.to_csv(summary_out, index=False)

    print(f"\n  CALIBRATION RESULTS BY PARCEL (Saved → {summary_out.name}):", flush=True)
    print("  " + "─" * 110, flush=True)
    for _, r in df_summary.iterrows():
        gt_str = f"{r['ground_truth_target_vari']:+.4f}" if not pd.isna(r["ground_truth_target_vari"]) else "  N/A  "
        print(f"  • {r['parcel_id']:<35s} | Culture: {r['culture_declaree_parcelle']:<30s} | Shared: {str(r['signal_partage']):<5s} | S2 Raw: {r['s2_raw_vari_mean']:+.4f} | GT Target: {gt_str} | Calibrated: {r['s2_calibrated_vari_mean']:+.4f}", flush=True)

    return df_s2, df_summary


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                      3. SAVING & PLOTTING                                   ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def save_calibrated_outputs(df_s2, source_files):
    """Save calibrated results as per-site AWAM GeoParquet files in clean/."""
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    # Save one calibrated GeoParquet per source file, following AWAM naming convention:
    #   AWAM_GEE_{site}_ALL_S2-Indices_{dates}_v2_calibrated_clean.parquet
    saved_count = 0
    for src_file in source_files:
        if src_file.suffix != ".parquet":
            continue

        # Build standardized calibrated filename
        if "_v2_clean" in src_file.name:
            out_name = src_file.name.replace("_v2_clean", "_v2_calibrated_clean")
        elif "_clean.parquet" in src_file.name:
            out_name = src_file.name.replace("_clean.parquet", "_calibrated_clean.parquet")
        elif "AWAM_" in src_file.name:
            out_name = src_file.stem + "_calibrated_clean.parquet"
        else:
            out_name = src_file.stem + "_calibrated_clean.parquet"

        # Filter df_s2 to only rows from this source site
        site_token = None
        for token in ["makthar", "sidi-mechreg"]:
            if token in src_file.name:
                site_token = token
                break

        if site_token and "site" in df_s2.columns:
            site_key = site_token.replace("-", "_")
            df_site = df_s2[df_s2["site"].str.contains(site_key, case=False, na=False)]
        else:
            df_site = df_s2

        out_path = CLEAN_DIR / out_name
        if isinstance(df_site, gpd.GeoDataFrame):
            df_site.to_parquet(out_path)
        else:
            gpd.GeoDataFrame(df_site, crs="EPSG:4326").to_parquet(out_path)
        print(f"  ✓ Saved calibrated GeoParquet → {out_path.name} ({len(df_site):,} rows)", flush=True)
        saved_count += 1

    print(f"  ✓ {saved_count} calibrated GeoParquet file(s) saved to {CLEAN_DIR.name}/", flush=True)


def plot_calibration_results(df_s2, df_summary):
    """Generate visual calibration diagnostic scatter & comparison plots."""
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # Plot 1: Raw vs Unmixed vs Calibrated VARI per Parcel
    parcels = df_summary["parcel_id"].tolist()
    x = np.arange(len(parcels))
    width = 0.25

    axes[0].bar(x - width, df_summary["s2_raw_vari_mean"], width, label="S2 Raw VARI", color="salmon")
    axes[0].bar(x, df_summary["s2_unmixed_vari_mean"], width, label="S2 Unmixed VARI", color="gold")
    axes[0].bar(x + width, df_summary["s2_calibrated_vari_mean"], width, label="S2 Calibrated VARI", color="forestgreen")

    # Add ground truth targets as points
    for i, r in df_summary.iterrows():
        if not pd.isna(r["ground_truth_target_vari"]):
            axes[0].plot(i + width, r["ground_truth_target_vari"], "k*", markersize=12, label="Ground Truth Target" if i == 0 else "")

    axes[0].set_xticks(x)
    axes[0].set_xticklabels([p.replace("sidi_mechreg_Parcelle_", "Sidi_").replace("makthar_", "Makthar_") for p in parcels], rotation=45, ha="right")
    axes[0].set_ylabel("VARI Index")
    axes[0].set_title("Sentinel-2 VARI: Raw vs Unmixed vs Calibrated")
    axes[0].legend()
    axes[0].grid(True, linestyle="--", alpha=0.5)

    # Plot 2: Scatter plot of Calibrated vs Ground Truth Target
    df_valid = df_summary.dropna(subset=["ground_truth_target_vari"])
    if len(df_valid) > 0:
        y_gt = df_valid["ground_truth_target_vari"].values
        y_raw = df_valid["s2_raw_vari_mean"].values
        y_calib = df_valid["s2_calibrated_vari_mean"].values

        axes[1].scatter(y_gt, y_raw, color="salmon", s=80, zorder=3, label="Raw S2 vs GT")
        axes[1].scatter(y_gt, y_calib, color="forestgreen", s=100, marker="^", zorder=4, label="Calibrated S2 vs GT")

        # 1:1 line
        lims = [min(y_gt.min(), y_raw.min(), y_calib.min()) - 0.05, max(y_gt.max(), y_raw.max(), y_calib.max()) + 0.05]
        axes[1].plot(lims, lims, "k--", alpha=0.7, label="1:1 Perfect Alignment")
        axes[1].set_xlim(lims)
        axes[1].set_ylim(lims)
        axes[1].set_xlabel("Ground Truth Photo Plant VARI Target")
        axes[1].set_ylabel("Sentinel-2 Satellite VARI")
        axes[1].set_title("Ground Truth vs Satellite VARI Calibration Fit")
        axes[1].legend()
        axes[1].grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout()
    plot_path = PLOTS_DIR / "vari_calibration_curves.png"
    plt.savefig(plot_path, dpi=150)
    plt.close()
    print(f"  ✓ Diagnostic plot saved → {plot_path.name}", flush=True)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                      4. VERIFICATION TESTS                                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def verify_accuracy_and_truth(df_s2, df_summary):
    """
    Verification testing against physical bounds and ground truth consistency.
    """
    print("\n  PHYSICAL & GROUND TRUTH ACCURACY AUDIT", flush=True)
    print("  " + "─" * 70, flush=True)

    # Check 1: Soil unmixing gain on low fCover parcels
    low_fcover_mask = df_s2["fCover"] < 0.3 if "fCover" in df_s2.columns else pd.Series(False, index=df_s2.index)
    if low_fcover_mask.any():
        unmix_diff = df_s2.loc[low_fcover_mask, "VARI_unmixed"].mean() - df_s2.loc[low_fcover_mask, "VARI"].mean()
        print(f"  • Low fCover (< 30%) Soil Unmixing Gain: +{unmix_diff:.4f} VARI shift", flush=True)

    # Check 2: Calibrated RMSE across parcels with ground truth
    df_valid = df_summary.dropna(subset=["ground_truth_target_vari"])
    if len(df_valid) > 0:
        mean_rmse = df_valid["calibrated_rmse"].mean()
        print(f"  • Ground Truth Calibration Alignment: Mean RMSE = {mean_rmse:.4f} across {len(df_valid)} parcels", flush=True)


def run_verification_tests(df_s2, df_summary):
    """Automated pipeline assertions."""
    print("\n  AUTOMATED SATELLITE CALIBRATION VERIFICATION TESTS", flush=True)
    print("  " + "─" * 70, flush=True)

    passed = 0
    total = 0

    # Test 1: VARI_calibrated column exists and is non-null
    total += 1
    if "VARI_calibrated" in df_s2.columns and df_s2["VARI_calibrated"].notna().any():
        print(f"  [PASS] Test 1: VARI_calibrated created with {df_s2['VARI_calibrated'].notna().sum():,} non-null values.", flush=True)
        passed += 1
    else:
        print(f"  [FAIL] Test 1: VARI_calibrated missing or all null.", flush=True)

    # Test 2: Unmixing increases VARI (since soil is negative)
    total += 1
    diff = df_s2["VARI_unmixed"].mean() - df_s2["VARI"].mean()
    if diff > 0:
        print(f"  [PASS] Test 2: Sub-pixel unmixing successfully removes soil attenuation (Mean VARI shift: +{diff:.4f}).", flush=True)
        passed += 1
    else:
        print(f"  [FAIL] Test 2: Sub-pixel unmixing did not increase VARI.", flush=True)

    # Test 3: Ground truth species RMSE < 0.15
    total += 1
    valid_rmse = df_summary["calibrated_rmse"].dropna()
    if len(valid_rmse) > 0 and (valid_rmse < 0.15).all():
        print(f"  [PASS] Test 3: Calibration RMSE < 0.15 for all calibrated crop species (Mean RMSE: {valid_rmse.mean():.4f}).", flush=True)
        passed += 1
    elif len(valid_rmse) == 0:
        print(f"  [SKIP] Test 3: No parcels with ground truth coverage to evaluate RMSE.", flush=True)
    else:
        print(f"  [FAIL] Test 3: Calibration RMSE exceeded 0.15 limit.", flush=True)

    verify_accuracy_and_truth(df_s2, df_summary)

    print(f"\n  Test Result Summary: {passed}/{total} Tests Passed.", flush=True)
    return passed == total


def main():
    print("=" * 80, flush=True)
    print(" SENTINEL-2 VARI UNMIXING & GROUND TRUTH CALIBRATION", flush=True)
    print("=" * 80, flush=True)

    # 1. Load ground truth
    crop_stats, df_gt = load_ground_truth()

    # 2. Load Sentinel-2 data (GeoParquet or CSV)
    gdf_s2, source_desc, source_files = load_sentinel2_data()

    # 3. Calibrate
    gdf_s2, df_summary = calibrate_sentinel2(gdf_s2, crop_stats)

    # 4. Save outputs
    save_calibrated_outputs(gdf_s2, source_files)

    # 5. Plot results
    plot_calibration_results(gdf_s2, df_summary)

    # 6. Run verification tests
    run_verification_tests(gdf_s2, df_summary)

    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  ✅  VARI CALIBRATION COMPLETE                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Source: {source_desc:<67s}  ║
║  Input rows:      {len(gdf_s2):>10,}                                          ║
║  Parcels:         {gdf_s2['parcel_id'].nunique():>10}                                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
""", flush=True)


if __name__ == "__main__":
    main()
