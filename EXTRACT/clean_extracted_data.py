#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
DATA CLEANING PIPELINE FOR SPATIAL INDICES DATABASE  (v2)
================================================================================

Reads raw GeoParquet files from `outputs/pixel_indices_database/raw/`,
applies domain-specific physical validation, quality flag filtering, outlier
rejection, and deduplication rules per sensor, and exports clean GeoParquet
files into `outputs/pixel_indices_database/clean/`.

Also generates a comprehensive `cleaning_report.md`.

CHANGELOG vs v1
----------------
1. ECOSTRESS QC: the raw "QC" GeoTIFF band is a 16-bit BIT MASK, not a plain
   0-3 integer. Only bits 1:0 ("Mandatory QA") encode pixel quality; higher
   bits carry other accuracy flags and are frequently non-zero. v1 compared
   the RAW value directly to <=1, which discarded ~100% of rows even for
   good pixels (e.g. raw QC=65 -> mandatory QA=1, "usable", but 65<=1 is
   False). v2 masks with `& 0b11` before comparing.
   Source: ECO_L2T_LSTE V002 User Guide / LP DAAC product page.

2. ECOSTRESS cloud mask: NASA's official Data Alert for v002 states the QC
   layer no longer carries cloud information; the separate `cloud` band
   bundled in the L2T_LSTE product must be used instead (0 = clear,
   1 = cloud). v1 extracted this band (`cloud_flag`) but never filtered on
   it. v2 drops cloud_flag == 1.
   Source: LP DAAC Data Alert (Sept 2024) + NASA VITALS ECOSTRESS tutorial.

3. ERA5-Land precipitation: `total_precipitation_sum` is a GRIB-packed flow
   band. Google's own catalog page for ECMWF/ERA5_LAND/DAILY_AGGR documents
   that these bands "might occasionally have negative values, which doesn't
   make physical sense" and "at other times their values might be
   excessively high" due to GRIB packing. v1 did not validate precip_mm at
   all. v2 clips negative values to 0 and flags/drops implausibly large
   values (> PRECIP_MAX_MM_DAY, a generous artifact guard, not a
   climatological limit -- tune it to your AOI if needed).

4. Deduplication: v1 used `drop_duplicates(subset=key_cols)` everywhere,
   which silently keeps whichever row happens to appear first in the file
   and DISCARDS any other row sharing the same key -- even if it carries a
   genuinely different measured value (e.g. two real acquisitions on the
   same day, at the same rounded coordinates, from overlapping
   tiles/orbits/swaths). v2 only drops rows that are byte-for-byte
   identical across every column outright; rows that share the dedup key
   but disagree on their measured values are merged by averaging instead
   of being arbitrarily discarded, so no real observation is silently
   thrown away. The report distinguishes "Dedup Dropped" (true duplicates)
   from "Merged (conflict)" (distinct observations combined by averaging).

Author: GeoAI / WWC Internship
================================================================================
"""

import sys
import os
import re
import math
import time
import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path

# Force UTF-8 output encoding for Windows terminal compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

EXTRACT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = EXTRACT_DIR.parent if EXTRACT_DIR.name == "EXTRACT" else EXTRACT_DIR
RAW_DIR = SCRIPTS_DIR / "outputs" / "pixel_indices_database" / "raw"
CLEAN_DIR = SCRIPTS_DIR / "outputs" / "pixel_indices_database" / "clean"

# Generous sanity guard against GRIB-packing artifacts in ERA5-Land flow
# bands (see changelog #3). NOT a climatological maximum -- raise it if
# your AOI is prone to genuine extreme-rainfall events.
PRECIP_MAX_MM_DAY = 300.0


def detect_datatype(filename):
    """Detect sensor/datatype from AWAM filename."""
    name = filename.name
    if "S2-Indices" in name:
        return "S2-Indices"
    elif "S1-SAR" in name:
        return "S1-SAR"
    elif "MODIS-LST" in name:
        return "MODIS-LST"
    elif "Landsat-Thermal" in name:
        return "Landsat-Thermal"
    elif "ERA5-Meteo" in name:
        return "ERA5-Meteo"
    elif "ECOSTRESS-LST" in name:
        return "ECOSTRESS-LST"
    elif "NISAR-SoilMoisture" in name:
        return "NISAR-SoilMoisture"
    elif "NISAR-Backscatter" in name:
        return "NISAR-Backscatter"
    return "Unknown"


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                      SHARED HELPER: NON-DESTRUCTIVE DEDUP                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def dedup_smart(gdf, key_cols):
    """
    Deduplicate on key_cols without silently discarding genuine distinct
    observations that merely happen to share the same key.

    - Rows identical across EVERY column (true duplicates -- e.g. the same
      pixel re-emitted by an overlapping export batch/retry) are dropped.
    - Rows that share key_cols but DIFFER in their measured values (e.g.
      two real acquisitions covering the same parcel/date/coords from
      overlapping tiles or orbits) are merged by averaging their numeric
      columns, instead of arbitrarily keeping whichever came first.

    Returns (clean_gdf, n_exact_dropped, n_conflicts_merged)
    """
    if not key_cols or not all(c in gdf.columns for c in key_cols) or len(gdf) == 0:
        return gdf, 0, 0

    was_gdf = isinstance(gdf, gpd.GeoDataFrame)
    crs = gdf.crs if was_gdf else None
    geom_col = gdf.geometry.name if was_gdf and gdf.geometry.name in gdf.columns else None

    # 1. Drop byte-for-byte identical rows outright.
    exact_dupe_mask = gdf.duplicated(keep="first")
    n_exact = int(exact_dupe_mask.sum())
    gdf = gdf[~exact_dupe_mask].copy()

    # 2. Rows still sharing the key but differing in value -> merge, don't drop.
    dup_key_mask = gdf.duplicated(subset=key_cols, keep=False)
    if not dup_key_mask.any():
        return gdf, n_exact, 0

    conflict = pd.DataFrame(gdf[dup_key_mask])
    rest = gdf[~dup_key_mask]

    n_conflict_rows = len(conflict)

    # BUGFIX (independent finding, not from the earlier audit): every
    # numeric column that isn't part of the merge key used to be averaged
    # unconditionally -- including quality/flag CODES such as
    # LST_ECOSTRESS_QC, soil_moisture_qc, cloud_flag, and frost_risk.
    # These are categorical codes, not continuous quantities: averaging
    # QC=0 (good) and QC=2 (bad) produces QC=1.0, a value that is not a
    # meaningful flag and that the downstream QC filters (`<= 1`, `== 0`)
    # would then silently accept or reject in a way that doesn't reflect
    # either original observation. For these columns, take the worst-case
    # (max) of the two readings instead -- in every case here, 0 means
    # "best/clear/no-frost" and higher means "worse", so max is the
    # conservative choice, not an arbitrary one.
    FLAG_LIKE_COLUMNS = {"LST_ECOSTRESS_QC", "soil_moisture_qc", "cloud_flag", "frost_risk"}

    numeric_cols = [c for c in conflict.select_dtypes(include=[np.number]).columns if c not in key_cols]
    flag_cols = [c for c in numeric_cols if c in FLAG_LIKE_COLUMNS]
    mean_cols = [c for c in numeric_cols if c not in FLAG_LIKE_COLUMNS]
    other_cols = [c for c in conflict.columns if c not in key_cols and c not in numeric_cols]

    agg = {c: "mean" for c in mean_cols}
    agg.update({c: "max" for c in flag_cols})
    agg.update({c: "first" for c in other_cols})

    # IMPORTANT: pandas groupby() drops rows whose key contains NaN/NaT by
    # default (dropna=True). Without dropna=False here, any row with a
    # missing date/coordinate that happens to collide with another row on
    # the rest of the key would silently vanish -- not merged, not counted
    # anywhere in the stats. This was the cause of dates disappearing
    # without explanation.
    merged = conflict.groupby(key_cols, as_index=False, dropna=False).agg(agg)
    n_merged_rows = len(merged)
    n_conflicts_merged = n_conflict_rows - n_merged_rows

    out = pd.concat([pd.DataFrame(rest), merged], ignore_index=True)

    if was_gdf and geom_col and geom_col in out.columns:
        out = gpd.GeoDataFrame(out, geometry=geom_col, crs=crs)

    return out, n_exact, n_conflicts_merged


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                      SENSOR-SPECIFIC CLEANING RULES                        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def clean_s2_indices(gdf):
    """Cleaning rules for Sentinel-2 spectral indices + fCover."""
    stats = {"qc_drop": 0, "outlier_drop": 0, "dedup_drop": 0, "merged": 0}

    # 1. Clamp physical bounds [-1.0, 1.0] for ratio indices
    ratio_cols = ["NDVI", "SAVI", "MSAVI", "EVI", "NDRE", "NDWI", "NDMI", "BSI", "NDSI_soil"]
    for col in ratio_cols:
        if col in gdf.columns:
            gdf[col] = gdf[col].clip(-1.0, 1.0)

    # 2. Clamp fCover [0.0, 1.0]
    if "fCover" in gdf.columns:
        gdf["fCover"] = gdf["fCover"].clip(0.0, 1.0)

    # 3. Reject cloud leakage outliers (NDVI outside [-0.5, 1.0])
    if "NDVI" in gdf.columns:
        valid_ndvi = (gdf["NDVI"].isna()) | ((gdf["NDVI"] >= -0.5) & (gdf["NDVI"] <= 1.0))
        stats["outlier_drop"] += int((~valid_ndvi).sum())
        gdf = gdf[valid_ndvi]

    # 4. Reject fully empty sensor rows (> 80% NaN among sensor cols)
    sensor_cols = [c for c in ratio_cols + ["CI_RedEdge", "VARI", "Carbonate_SWIR", "SI_soil", "fCover"] if c in gdf.columns]
    if sensor_cols:
        nan_pct = gdf[sensor_cols].isna().mean(axis=1)
        valid_sensor = nan_pct <= 0.8
        stats["qc_drop"] += int((~valid_sensor).sum())
        gdf = gdf[valid_sensor]

    # 5. Deduplicate (non-destructive -- see dedup_smart docstring)
    dedup_cols = [c for c in ["parcel_id", "date", "longitude", "latitude"] if c in gdf.columns]
    gdf, n_exact, n_merged = dedup_smart(gdf, dedup_cols)
    stats["dedup_drop"] = n_exact
    stats["merged"] = n_merged

    return gdf, stats


def clean_s1_sar(gdf):
    """Cleaning rules for Sentinel-1 SAR backscatter & DpRVIc."""
    stats = {"qc_drop": 0, "outlier_drop": 0, "dedup_drop": 0, "merged": 0}

    # 1. Physical bounds
    if "VV_dB" in gdf.columns:
        gdf["VV_dB"] = gdf["VV_dB"].clip(-30.0, 5.0)
    if "VH_dB" in gdf.columns:
        gdf["VH_dB"] = gdf["VH_dB"].clip(-35.0, 0.0)
    if "VH_VV_ratio" in gdf.columns:
        gdf["VH_VV_ratio"] = gdf["VH_VV_ratio"].clip(0.0, 1.0)
    if "DpRVIc" in gdf.columns:
        # BUGFIX: DpRVIc now holds RVI = 4*VH/(VV+VH) (see extraction script
        # fix), whose theoretical range is [0, 4], not [0, 1]. Clipping to
        # [0, 1] here would silently truncate almost every real value.
        gdf["DpRVIc"] = gdf["DpRVIc"].clip(0.0, 4.0)

    # 2. Speckle IQR filter per parcel & date
    #
    # BUGFIX (v2.1): this used to be implemented as
    #   gdf.groupby(["parcel_id", "date"]).apply(iqr_filter)
    # where iqr_filter(group) returned a *subset of the group unchanged*.
    # As of pandas >= 2.2, DataFrameGroupBy.apply() no longer includes the
    # grouping columns in the sub-DataFrame it hands to the callback, and
    # since the callback just returned that (already-stripped) sub-frame,
    # "parcel_id" and "date" were silently dropped from the ENTIRE output
    # the moment this line executed -- for every S1-SAR file, not just
    # rows that failed the IQR test. This is the actual cause of the
    # "date column disappears" symptom: every downstream step (including
    # the "non-destructive dedup" a few lines below) then ran without
    # parcel_id/date, so dedup silently fell back to matching on
    # longitude/latitude alone and merged observations from DIFFERENT
    # dates that happened to share the same rounded coordinates.
    # (The dropna=False fix inside dedup_smart() addresses a real but
    # separate NaN-key issue; it does not fix this one.)
    #
    # Rewritten with groupby(...).transform(...), which computes the same
    # per-(parcel_id, date) quartiles but returns a Series aligned to the
    # original index/columns instead of rebuilding the DataFrame, so no
    # column can be silently dropped.
    if "VV_dB" in gdf.columns and "parcel_id" in gdf.columns and "date" in gdf.columns:
        n_pre_iqr = len(gdf)
        grp = gdf.groupby(["parcel_id", "date"], dropna=False)["VV_dB"]
        q25 = grp.transform("quantile", 0.25)
        q75 = grp.transform("quantile", 0.75)
        iqr = q75 - q25
        lower = q25 - 1.5 * iqr
        upper = q75 + 1.5 * iqr
        # Groups with iqr == 0 or NaN (e.g. a single observation, or an
        # all-NaN VV_dB group) keep all their rows, matching the original
        # per-group behaviour.
        valid = (iqr == 0) | iqr.isna() | ((gdf["VV_dB"] >= lower) & (gdf["VV_dB"] <= upper))
        stats["outlier_drop"] = int((~valid).sum())
        gdf = gdf[valid]

    # 3. Deduplicate (non-destructive)
    dedup_cols = [c for c in ["parcel_id", "date", "longitude", "latitude"] if c in gdf.columns]
    gdf, n_exact, n_merged = dedup_smart(gdf, dedup_cols)
    stats["dedup_drop"] = n_exact
    stats["merged"] = n_merged

    return gdf, stats


def clean_modis_lst(gdf):
    """Cleaning rules for MODIS LST, SMI, and CWSI_proxy."""
    stats = {"qc_drop": 0, "outlier_drop": 0, "dedup_drop": 0, "merged": 0}

    # 1. LST bounds [250K, 340K]
    if "LST_K" in gdf.columns:
        valid_lst = (gdf["LST_K"].isna()) | ((gdf["LST_K"] >= 250.0) & (gdf["LST_K"] <= 340.0))
        stats["outlier_drop"] += int((~valid_lst).sum())
        gdf = gdf[valid_lst]

    # 2. SMI & CWSI bounds [0, 1]
    if "SMI" in gdf.columns:
        gdf["SMI"] = gdf["SMI"].clip(0.0, 1.0)
    if "CWSI_proxy" in gdf.columns:
        gdf["CWSI_proxy"] = gdf["CWSI_proxy"].clip(0.0, 1.0)

    # 3. Deduplicate (non-destructive)
    dedup_cols = [c for c in ["parcel_id", "date", "longitude", "latitude"] if c in gdf.columns]
    gdf, n_exact, n_merged = dedup_smart(gdf, dedup_cols)
    stats["dedup_drop"] = n_exact
    stats["merged"] = n_merged

    return gdf, stats


def clean_landsat_thermal(gdf):
    """Cleaning rules for Landsat 8/9 Thermal & NDVI."""
    stats = {"qc_drop": 0, "outlier_drop": 0, "dedup_drop": 0, "merged": 0}

    # 1. LST bounds [250K, 340K]
    if "LST_Landsat_K" in gdf.columns:
        valid_lst = (gdf["LST_Landsat_K"].isna()) | ((gdf["LST_Landsat_K"] >= 250.0) & (gdf["LST_Landsat_K"] <= 340.0))
        stats["outlier_drop"] += int((~valid_lst).sum())
        gdf = gdf[valid_lst]

    # 2. NDVI bounds [-1, 1]
    if "NDVI_Landsat" in gdf.columns:
        gdf["NDVI_Landsat"] = gdf["NDVI_Landsat"].clip(-1.0, 1.0)

    # 3. Deduplicate (non-destructive)
    dedup_cols = [c for c in ["parcel_id", "date", "longitude", "latitude"] if c in gdf.columns]
    gdf, n_exact, n_merged = dedup_smart(gdf, dedup_cols)
    stats["dedup_drop"] = n_exact
    stats["merged"] = n_merged

    return gdf, stats


def clean_era5_meteo(gdf):
    """Cleaning rules for ERA5-Land temperature, precipitation, GDD, frost risk."""
    stats = {"qc_drop": 0, "outlier_drop": 0, "dedup_drop": 0, "merged": 0}

    # 1. Physical bounds Tmin in [-15, 50] C, Tmax in [-10, 55] C
    if "Tmin_C" in gdf.columns and "Tmax_C" in gdf.columns:
        valid_t = (
            (gdf["Tmin_C"].isna() | ((gdf["Tmin_C"] >= -15.0) & (gdf["Tmin_C"] <= 50.0))) &
            (gdf["Tmax_C"].isna() | ((gdf["Tmax_C"] >= -10.0) & (gdf["Tmax_C"] <= 55.0))) &
            (gdf["Tmin_C"].isna() | gdf["Tmax_C"].isna() | (gdf["Tmin_C"] <= gdf["Tmax_C"]))
        )
        stats["outlier_drop"] += int((~valid_t).sum())
        gdf = gdf[valid_t]

    # 2. Precipitation validation (NEW in v2). ERA5-Land's total_precipitation_sum
    #    is a GRIB-packed flow band; Google's own dataset documentation warns
    #    it "might occasionally have negative values, which doesn't make
    #    physical sense" and can sometimes be "excessively high" due to GRIB
    #    packing. Negative precip is unambiguously non-physical -> clip to 0.
    #    Implausibly large values are flagged as outliers rather than
    #    silently clipped, since a genuine extreme storm should not be
    #    invisibly rewritten -- inspect these rows if any get dropped.
    if "precip_mm" in gdf.columns:
        negative_mask = gdf["precip_mm"] < 0
        if negative_mask.any():
            gdf.loc[negative_mask, "precip_mm"] = 0.0

        valid_precip = gdf["precip_mm"].isna() | (gdf["precip_mm"] <= PRECIP_MAX_MM_DAY)
        stats["outlier_drop"] += int((~valid_precip).sum())
        gdf = gdf[valid_precip]

    # 3. Recalculate frost_risk from validated Tmin
    if "Tmin_C" in gdf.columns:
        gdf["frost_risk"] = (gdf["Tmin_C"] < 0.0).astype(int)

    # 4. Deduplicate (non-destructive)
    dedup_cols = [c for c in ["parcel_id", "date"] if c in gdf.columns]
    gdf, n_exact, n_merged = dedup_smart(gdf, dedup_cols)
    stats["dedup_drop"] = n_exact
    stats["merged"] = n_merged

    return gdf, stats


def clean_ecostress_lst(gdf):
    """Cleaning rules for ECOSTRESS LST & emissivity."""
    stats = {"qc_drop": 0, "outlier_drop": 0, "dedup_drop": 0, "merged": 0}

    # 1. Filter QC: keep only pixels whose "Mandatory QA" bits (bits 1:0 of
    #    the raw 16-bit QC value) indicate a produced pixel of usable
    #    accuracy. Per the ECO_L2T_LSTE V002 User Guide, bits 1:0 encode:
    #       00 = pixel produced by TES (good)
    #       01 = pixel produced by TES, but LST accuracy may be degraded
    #       10 = not set (NOT a cloud flag in v002, unlike v001)
    #       11 = pixel not produced
    #    Higher-order bits (2+) carry other accuracy flags and are frequently
    #    non-zero, so the RAW value must be masked with 0b11 before
    #    comparing -- comparing the raw value directly to <=1 (v1 behaviour)
    #    silently discards almost every valid pixel, e.g. raw QC=65
    #    (0b1000001, mandatory QA=01, "usable") fails `65 <= 1`.
    if "LST_ECOSTRESS_QC" in gdf.columns:
        mandatory_qa = gdf["LST_ECOSTRESS_QC"].astype("Int64") & 0b11
        valid_qc = gdf["LST_ECOSTRESS_QC"].isna() | (mandatory_qa <= 1)
        stats["qc_drop"] += int((~valid_qc).sum())
        gdf = gdf[valid_qc]

    # 2. Cloud filter (NEW in v2). NASA's official Data Alert for v002 states
    #    the QC layer no longer reflects cloud contamination; the dedicated
    #    `cloud` band bundled in L2T_LSTE must be used instead, where
    #    0 = clear and 1 = cloud (NASA VITALS ECOSTRESS tutorial). This band
    #    was already being extracted as `cloud_flag` but never applied.
    if "cloud_flag" in gdf.columns:
        valid_cloud = gdf["cloud_flag"].isna() | (gdf["cloud_flag"] == 0)
        stats["qc_drop"] += int((~valid_cloud).sum())
        gdf = gdf[valid_cloud]

    # 3. LST bounds [250K, 340K]
    if "LST_ECOSTRESS_K" in gdf.columns:
        valid_lst = (gdf["LST_ECOSTRESS_K"].isna()) | ((gdf["LST_ECOSTRESS_K"] >= 250.0) & (gdf["LST_ECOSTRESS_K"] <= 340.0))
        stats["outlier_drop"] += int((~valid_lst).sum())
        gdf = gdf[valid_lst]

    # 4. Emissivity bounds [0.85, 1.0]
    if "emissivity" in gdf.columns:
        gdf["emissivity"] = gdf["emissivity"].clip(0.85, 1.0)

    # 5. Deduplicate (non-destructive)
    dedup_cols = [c for c in ["parcel_id", "date", "acquisition_time", "longitude", "latitude"] if c in gdf.columns]
    gdf, n_exact, n_merged = dedup_smart(gdf, dedup_cols)
    stats["dedup_drop"] = n_exact
    stats["merged"] = n_merged

    return gdf, stats


def clean_nisar_soil_moisture(gdf):
    """Cleaning rules for NISAR L3 Soil Moisture."""
    stats = {"qc_drop": 0, "outlier_drop": 0, "dedup_drop": 0, "merged": 0}

    # 1. Filter QC flag (0 == recommended)
    if "soil_moisture_qc" in gdf.columns:
        valid_qc = gdf["soil_moisture_qc"].isna() | (gdf["soil_moisture_qc"] == 0)
        stats["qc_drop"] += int((~valid_qc).sum())
        gdf = gdf[valid_qc]

    # 2. Volumetric soil moisture physical range [0.01, 0.60] m3/m3
    if "soil_moisture_vol" in gdf.columns:
        valid_sm = (gdf["soil_moisture_vol"].isna()) | ((gdf["soil_moisture_vol"] >= 0.01) & (gdf["soil_moisture_vol"] <= 0.60))
        stats["outlier_drop"] += int((~valid_sm).sum())
        gdf = gdf[valid_sm]

    # 3. Vegetation water content [0, 10] kg/m2
    if "vegetation_water_content" in gdf.columns:
        gdf["vegetation_water_content"] = gdf["vegetation_water_content"].clip(0.0, 10.0)

    # 4. Deduplicate (non-destructive)
    dedup_cols = [c for c in ["parcel_id", "date", "longitude", "latitude"] if c in gdf.columns]
    gdf, n_exact, n_merged = dedup_smart(gdf, dedup_cols)
    stats["dedup_drop"] = n_exact
    stats["merged"] = n_merged

    return gdf, stats


def clean_nisar_backscatter(gdf):
    """Cleaning rules for NISAR L2 GCOV Backscatter."""
    stats = {"qc_drop": 0, "outlier_drop": 0, "dedup_drop": 0, "merged": 0}

    # 1. Physical bounds: HH [-30, 5] dB, HV [-40, 0] dB
    if "HH_gamma0_dB" in gdf.columns:
        gdf["HH_gamma0_dB"] = gdf["HH_gamma0_dB"].clip(-30.0, 5.0)
    if "HV_gamma0_dB" in gdf.columns:
        gdf["HV_gamma0_dB"] = gdf["HV_gamma0_dB"].clip(-40.0, 0.0)
    if "RVI_NISAR" in gdf.columns:
        # BUGFIX: RVI_NISAR now holds RVI = 4*HV/(HH+HV) (see extraction
        # script fix), whose theoretical range is [0, 4], not [0, 1].
        gdf["RVI_NISAR"] = gdf["RVI_NISAR"].clip(0.0, 4.0)

    # 2. Deduplicate (non-destructive)
    dedup_cols = [c for c in ["parcel_id", "date", "longitude", "latitude"] if c in gdf.columns]
    gdf, n_exact, n_merged = dedup_smart(gdf, dedup_cols)
    stats["dedup_drop"] = n_exact
    stats["merged"] = n_merged

    return gdf, stats


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║                            MAIN CLEANING RUNNER                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

CLEANING_FUNCTIONS = {
    "S2-Indices":          clean_s2_indices,
    "S1-SAR":              clean_s1_sar,
    "MODIS-LST":           clean_modis_lst,
    "Landsat-Thermal":     clean_landsat_thermal,
    "ERA5-Meteo":          clean_era5_meteo,
    "ECOSTRESS-LST":       clean_ecostress_lst,
    "NISAR-SoilMoisture":  clean_nisar_soil_moisture,
    "NISAR-Backscatter":   clean_nisar_backscatter,
}


def run_cleaning_pipeline(append_mode=False):
    import argparse
    parser = argparse.ArgumentParser(description="Data Cleaning Pipeline")
    parser.add_argument("--append", action="store_true", help="Merge newly cleaned raw data with existing clean GeoParquet files")
    args, _ = parser.parse_known_args()
    if args.append:
        append_mode = True

    print("\n" + "=" * 80)
    print(" DATA CLEANING PIPELINE — VALIDATION, FILTERING & DEDUPLICATION (v2)")
    print(f" Mode: {'APPEND & MERGE' if append_mode else 'OVERWRITE'}")
    print("=" * 80 + "\n")

    if not RAW_DIR.exists():
        print(f"  ⚠ Raw directory does not exist: {RAW_DIR}", flush=True)
        return

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    raw_files = sorted(list(RAW_DIR.glob("*.parquet")))
    if not raw_files:
        print(f"  ⚠ No raw GeoParquet files found in {RAW_DIR}", flush=True)
        return

    print(f"  Found {len(raw_files)} raw file(s) in {RAW_DIR.name}/\n", flush=True)

    from collections import defaultdict
    grouped_raw = defaultdict(list)
    for fpath in raw_files:
        datatype = detect_datatype(fpath)
        parts = fpath.stem.split("_")
        provider = parts[1] if len(parts) > 1 else "GEE"
        site = parts[2] if len(parts) > 2 else "all"
        grouped_raw[(provider, site, datatype)].append(fpath)

    print(f"  Organized into {len(grouped_raw)} sensor/site dataset group(s).\n", flush=True)

    report_rows = []

    for (provider, site, datatype), fpaths in sorted(grouped_raw.items()):
        clean_fn = CLEANING_FUNCTIONS.get(datatype)

        print(f"  Processing [{provider} / {site} / {datatype}] ({len(fpaths)} raw chunk(s))…", flush=True)
        for fp in fpaths:
            print(f"    ↳ {fp.name}", flush=True)

        gdfs = [gpd.read_parquet(fp) for fp in fpaths]
        gdf = pd.concat(gdfs, ignore_index=True)
        n_raw = len(gdf)

        if clean_fn:
            gdf_clean, stats = clean_fn(gdf)
        else:
            print(f"    ⚠ No specific cleaning function for {datatype}, deduplicating only", flush=True)
            all_cols = [c for c in gdf.columns]
            gdf_clean, n_exact, n_merged = dedup_smart(gdf, all_cols)
            stats = {"qc_drop": 0, "outlier_drop": 0, "dedup_drop": n_exact, "merged": n_merged}

        # Find any existing clean file for this provider/site/datatype combination
        existing_clean_file = None
        for cf in CLEAN_DIR.glob("*.parquet"):
            if f"_{provider}_" in cf.name and f"_{site}_" in cf.name and datatype in cf.name:
                existing_clean_file = cf
                break

        # If append mode and clean file already exists, merge with existing
        if append_mode and existing_clean_file and existing_clean_file.exists():
            print(f"    ⟳ Merging new cleaned rows with existing clean file ({existing_clean_file.name})...", flush=True)
            existing_gdf = gpd.read_parquet(existing_clean_file)
            combined_gdf = pd.concat([existing_gdf, gdf_clean], ignore_index=True)
            
            # Re-deduplicate
            all_cols = [c for c in combined_gdf.columns if c != "geometry"]
            gdf_clean, n_exact_app, n_merged_app = dedup_smart(combined_gdf, all_cols)
            stats["dedup_drop"] += n_exact_app
            stats["merged"] += n_merged_app
            print(f"    ✓ Merged total: {len(gdf_clean):,} clean rows preserved.", flush=True)

        # Construct updated clean filename using true min and max dates in gdf_clean
        if not gdf_clean.empty and "date" in gdf_clean.columns:
            d_min_str = pd.to_datetime(gdf_clean["date"]).min().strftime("%Y%m%d")
            d_max_str = pd.to_datetime(gdf_clean["date"]).max().strftime("%Y%m%d")
            clean_filename = f"AWAM_{provider}_{site}_ALL_{datatype}_{d_min_str}_{d_max_str}_v2_clean.parquet"
        else:
            clean_filename = fpaths[0].stem + "_clean.parquet"

        clean_filepath = CLEAN_DIR / clean_filename

        # Remove old clean file if its date tag was different
        if existing_clean_file and existing_clean_file.exists() and existing_clean_file != clean_filepath:
            try:
                existing_clean_file.unlink()
                print(f"    🧹 Removed outdated clean file: {existing_clean_file.name}", flush=True)
            except Exception:
                pass

        n_clean = len(gdf_clean)
        n_dropped = n_raw - n_clean
        pct_retained = (n_clean / n_raw * 100.0) if n_raw > 0 else 100.0

        # BUGFIX §27.1.13 : Écriture ATOMIQUE des fichiers Parquet.
        # L'ancienne écriture directe (gdf_clean.to_parquet(clean_filepath)) laissait
        # un fichier corrompu si le processus était tué (SIGKILL, OOM) en cours d'écriture.
        # La séquence write-to-tmp + os.replace() est atomique sur NTFS et POSIX :
        # en cas de crash, seul le .tmp est perdu ; le fichier officiel reste intact.
        tmp_filepath = clean_filepath.with_suffix(".tmp.parquet")
        try:
            gdf_clean.to_parquet(tmp_filepath, index=False)
            import os as _os
            _os.replace(tmp_filepath, clean_filepath)  # atomique NTFS + POSIX
        except Exception:
            if tmp_filepath.exists():
                tmp_filepath.unlink(missing_ok=True)
            raise

        print(f"    ↳ QC filter dropped     : {stats.get('qc_drop', 0):,} rows", flush=True)
        print(f"    ↳ Outliers dropped      : {stats.get('outlier_drop', 0):,} rows", flush=True)
        print(f"    ↳ True duplicates dropped: {stats.get('dedup_drop', 0):,} rows", flush=True)
        print(f"    ↳ Conflicting rows merged (averaged, not lost): {stats.get('merged', 0):,}", flush=True)
        print(f"    ✓ {n_raw:,} raw → {n_clean:,} clean ({pct_retained:.1f}% retained) → {clean_filename}\n", flush=True)

        report_rows.append({
            "Filename":        ", ".join(f.name for f in fpaths),
            "Datatype":        datatype,
            "Raw Rows":        n_raw,
            "Clean Rows":      n_clean,
            "Dropped Rows":    n_dropped,
            "QC Dropped":      stats.get("qc_drop", 0),
            "Outliers Dropped": stats.get("outlier_drop", 0),
            "Dedup Dropped":   stats.get("dedup_drop", 0),
            "Merged (conflict)": stats.get("merged", 0),
            "Retained %":      f"{pct_retained:.1f}%"
        })

    # Generate cleaning_report.md
    report_path = CLEAN_DIR / "cleaning_report.md"
    generate_markdown_report(report_rows, report_path)
    print(f"\n  ✓ Cleaning report written to {report_path.name}")


def generate_markdown_report(report_rows, output_path):
    """Generate markdown cleaning summary report."""
    now_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

    df_rep = pd.DataFrame(report_rows)

    md = f"""# Data Cleaning & Validation Report (v2)
*Generated on: {now_str}*

## Summary

This report documents the filtering, quality control, outlier removal, and deduplication
applied to the raw GeoParquet files extracted from GEE and NASA Earthdata.

"Merged (conflict)" rows are NOT lost data: they are rows that shared the same
(parcel_id, date, coords) key but disagreed on their measured values (e.g. two
genuine overlapping acquisitions on the same day). Their numeric columns were
averaged into a single row rather than one of them being silently discarded.

### Processing Results by File

| Filename | Datatype | Raw Rows | Clean Rows | Dropped | QC Drop | Outlier Drop | Dedup Drop | Merged (conflict) | Retained |
|----------|----------|---------:|-----------:|--------:|--------:|-------------:|-----------:|------------------:|---------:|
"""
    for r in report_rows:
        md += (f"| `{r['Filename']}` | {r['Datatype']} | {r['Raw Rows']:,} | {r['Clean Rows']:,} | "
               f"{r['Dropped Rows']:,} | {r['QC Dropped']:,} | {r['Outliers Dropped']:,} | "
               f"{r['Dedup Dropped']:,} | {r['Merged (conflict)']:,} | {r['Retained %']} |\n")

    total_raw = df_rep["Raw Rows"].sum() if not df_rep.empty else 0
    total_clean = df_rep["Clean Rows"].sum() if not df_rep.empty else 0
    total_dropped = df_rep["Dropped Rows"].sum() if not df_rep.empty else 0
    overall_pct = (total_clean / total_raw * 100.0) if total_raw > 0 else 100.0

    md += f"""
### Overall Metrics

- **Total Raw Records Extracted:** {total_raw:,}
- **Total Clean Records Preserved:** {total_clean:,}
- **Total Records Filtered:** {total_dropped:,}
- **Overall Data Retention Rate:** {overall_pct:.2f}%

---

## Applied Cleaning Rules Summary

1. **Sentinel-2 Indices (`S2-Indices`)**
   - Bound ratio indices (NDVI, SAVI, EVI, NDRE, NDWI, NDMI, BSI, NDSI) to `[-1.0, +1.0]`.
   - Bound `fCover` to `[0.0, +1.0]`.
   - Reject cloud leakage outliers where NDVI < -0.5.
   - Drop fully empty pixel observations (> 80% NaN).
   - Non-destructive dedup on `(parcel_id, date, longitude, latitude)`.

2. **Sentinel-1 SAR (`S1-SAR`)**
   - Clip backscatter VV_dB `[-30, +5]`, VH_dB `[-35, 0]`.
   - Speckle filter using IQR thresholding (1.5 x IQR) per parcel & date.
   - Non-destructive dedup on `(parcel_id, date, longitude, latitude)`.

3. **MODIS & Landsat & ECOSTRESS Thermal (`MODIS-LST`, `Landsat-Thermal`, `ECOSTRESS-LST`)**
   - Filter physical land surface temperature bounds `[250 K, 340 K]`.
   - ECOSTRESS: filter on the Mandatory QA bits (1:0) of the QC bitmask, masked with `& 0b11`
     (NOT the raw QC value).
   - ECOSTRESS: filter the dedicated cloud band (`cloud_flag == 0`), since the QC layer does
     not encode cloud information in product v002.
   - Non-destructive dedup on `(parcel_id, date, coords)`.

4. **AgERA5 / ERA5-Land Weather (`ERA5-Meteo`)**
   - Validate physical temperatures: Tmin in `[-15, 50] °C`, Tmax in `[-10, 55] °C`.
   - Assert logical consistency: `Tmin <= Tmax`.
   - Precipitation: clip GRIB-packing negative artifacts to 0; flag/drop values
     above {PRECIP_MAX_MM_DAY:.0f} mm/day as likely packing artifacts.
   - Recalculate frost risk binary flag from validated Tmin.
   - Non-destructive dedup on `(parcel_id, date)`.

5. **NISAR Radar Products (`NISAR-SoilMoisture`, `NISAR-Backscatter`)**
   - Validate volumetric soil moisture bounds `[0.01, 0.60] m³/m³`.
   - Filter recommended quality flags (`QC == 0`).
   - Bound backscatter gamma0 powers and radar vegetation index (RVI).
   - Non-destructive dedup on `(parcel_id, date, longitude, latitude)`.
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)


if __name__ == "__main__":
    run_cleaning_pipeline()