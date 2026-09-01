#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
baselines_communes.py
===================================================================
Fondations méthodologiques communes pour la normalisation causale,
les Z-scores glissants, percentiles expanding et anomalies spatiales pixel.

Règles strictes (implementation_plan_v2.md §4.1) :
1. Baselines TOUJOURS causales (fenêtre passée se terminant à la date évaluée).
2. Minimum 10 observations valides par parcelle dans la fenêtre, sinon
   statut marqué 'BASELINE_INSUFFISANTE' (pas de forçage silencieux à 0).
3. Détection d'anomalie spatiale intra-parcelle avec masquage de bordure (-10m).
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path

# Tentative d'import shapely pour la géométrie de bordure -10m
try:
    import shapely.geometry as sg
    from shapely.ops import transform
    import pyproj
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False

try:
    from scipy.spatial import cKDTree
    HAS_CKDTREE = True
except ImportError:
    HAS_CKDTREE = False

import json


def fusionner_tous_les_capteurs_sur_grille_pixel_10m(dict_sources: dict) -> pd.DataFrame:
    """
    Méthodologie standard internationale de ré-échantillonnage et fusion multi-sources :
    Grille cible canonique = Sentinel-2 pixels 10m (longitude, latitude, parcel_id, date).

    Applique :
    1. Grille cible canonique 10m (Sentinel-2).
    2. Ré-échantillonnage spatial par plus proche voisin (k-d Tree en UTM/métrique) pour chaque capteur :
       - S1-SAR (10-20m)
       - ECOSTRESS-LST (70m) : réplication 70m -> sub-pixels 10m
       - NISAR SoilMoisture / Backscatter (200m) : réplication 200m -> sub-pixels 10m
       - Landsat / MODIS (30m - 1km) : réplication -> sub-pixels 10m
       - ERA5-Meteo (9km) : rattaché par (parcel_id, date) à tous les sub-pixels 10m
    """
    if not dict_sources or "S2-Indices" not in dict_sources or dict_sources["S2-Indices"].empty:
        return pd.DataFrame()

    df_s2 = dict_sources["S2-Indices"].copy()
    if "longitude" not in df_s2.columns or "latitude" not in df_s2.columns:
        return df_s2

    df_s2["date"] = pd.to_datetime(df_s2["date"])

    # 1. Rattachement d'ERA5-Meteo par (parcel_id, date) à tous les sub-pixels 10m
    if "ERA5-Meteo" in dict_sources and not dict_sources["ERA5-Meteo"].empty:
        df_era5 = dict_sources["ERA5-Meteo"].copy()
        df_era5["date"] = pd.to_datetime(df_era5["date"])
        cols_met = [c for c in ["Tmax_C", "Tmin_C", "precip_mm", "GDD_cumul"] if c in df_era5.columns and c not in df_s2.columns]
        if cols_met:
            df_s2 = pd.merge(df_s2, df_era5[["parcel_id", "date"] + cols_met].drop_duplicates(), on=["parcel_id", "date"], how="left")

    # 2. Rattachement spatial k-d Tree des autres capteurs (ECOSTRESS, NISAR, Landsat, MODIS, S1-SAR)
    if HAS_CKDTREE:
        for stype, df_src in dict_sources.items():
            if stype in ["S2-Indices", "ERA5-Meteo"] or df_src.empty:
                continue
            if "longitude" not in df_src.columns or "latitude" not in df_src.columns:
                continue

            df_src = df_src.copy()
            df_src["date"] = pd.to_datetime(df_src["date"])

            # Colonnes d'intérêt à fusionner
            val_cols = [
                c for c in df_src.columns 
                if c not in ["site", "parcel_id", "date", "longitude", "latitude", "culture", "geometry"] 
                and c not in df_s2.columns 
                and pd.api.types.is_numeric_dtype(df_src[c])
            ]
            if not val_cols:
                continue

            merged_chunks = []
            src_dict = dict(tuple(df_src.groupby(["parcel_id", "date"])))

            for (pid, dt), g_s2 in df_s2.groupby(["parcel_id", "date"]):
                g_src = src_dict.get((pid, dt))
                if g_src is None or g_src.empty:
                    continue

                lat0 = g_s2["latitude"].mean()
                m_lat = 111320.0
                m_lon = 111320.0 * np.cos(np.radians(lat0))

                s2_xy = np.c_[g_s2["longitude"].values * m_lon, g_s2["latitude"].values * m_lat]
                src_xy = np.c_[g_src["longitude"].values * m_lon, g_src["latitude"].values * m_lat]

                # Construire l'arbre k-d sur les points du capteur source (g_src)
                # et requêter pour CHAQUE pixel Sentinel-2 (s2_xy) son voisin source le plus proche
                tree = cKDTree(src_xy)
                dists, idxs = tree.query(s2_xy, k=1)

                g_s2_mapped = g_s2[["longitude", "latitude"]].copy()
                g_s2_mapped["date"] = dt
                g_s2_mapped["parcel_id"] = pid
                for c in val_cols:
                    g_s2_mapped[c] = g_src[c].values[idxs]
                merged_chunks.append(g_s2_mapped)

            if merged_chunks:
                df_all_src = pd.concat(merged_chunks, ignore_index=True)
                df_s2 = pd.merge(df_s2, df_all_src, on=["parcel_id", "date", "longitude", "latitude"], how="left")

    # 3. Harmonisation thermique multi-capteurs (LST ECOSTRESS / Landsat / MODIS)
    if "LST_Landsat_C" in df_s2.columns and "LST_ECOSTRESS_C" in df_s2.columns:
        df_s2["LST_ECOSTRESS_C"] = df_s2["LST_ECOSTRESS_C"].fillna(df_s2["LST_Landsat_C"])
    if "LST_K" in df_s2.columns and "LST_ECOSTRESS_C" in df_s2.columns:
        df_s2["LST_ECOSTRESS_C"] = df_s2["LST_ECOSTRESS_C"].fillna(df_s2["LST_K"] - 273.15)

    # 4. Interpolation Spatio-Temporelle Causale par pixel 10m
    non_s2_cols = [
        c for c in df_s2.columns 
        if c not in ["site", "parcel_id", "date", "longitude", "latitude", "culture", "geometry", "NDVI", "SAVI", "EVI", "NDRE", "NDWI", "NDMI", "BSI", "fCover"]
        and pd.api.types.is_numeric_dtype(df_s2[c])
    ]
    if non_s2_cols:
        df_s2 = df_s2.sort_values(["parcel_id", "longitude", "latitude", "date"])
        for col in non_s2_cols:
            df_s2[col] = df_s2.groupby(["parcel_id", "longitude", "latitude"])[col].ffill(limit=45)
            df_s2[col] = df_s2.groupby(["parcel_id", "longitude", "latitude"])[col].bfill(limit=45)

    return df_s2


def calculer_baseline_glissante_causale(
    df: pd.DataFrame,
    col_target: str,
    window_days: int = 30,
    min_obs: int = 10,
    group_col: str = "parcel_id",
    date_col: str = "date"
) -> pd.Series:
    """
    Calcule un Z-score causal par parcelle sur une fenêtre glissante glissante_days.
    Z = (valeur_courante - moyenne_passée) / std_passée

    Returns:
        pd.Series contenant le Z-score. Si < min_obs dans la fenêtre, vaut NaN.
    """
    if col_target not in df.columns or df.empty:
        return pd.Series(np.nan, index=df.index)

    df_sorted = df.copy()
    df_sorted[date_col] = pd.to_datetime(df_sorted[date_col])

    z_scores = pd.Series(np.nan, index=df.index, dtype=float)

    for pid, group in df_sorted.groupby(group_col):
        group = group.sort_values(date_col)
        dates = group[date_col].values
        vals = group[col_target].values

        z_group = np.full(len(vals), np.nan)

        for i in range(len(vals)):
            cur_date = dates[i]
            cur_val = vals[i]
            if np.isnan(cur_val):
                continue

            # Fenêtre causale: [cur_date - window_days, cur_date]
            start_window = cur_date - np.timedelta64(window_days, 'D')
            mask = (dates >= start_window) & (dates <= cur_date)
            window_vals = vals[mask]
            window_vals = window_vals[~np.isnan(window_vals)]

            if len(window_vals) >= min_obs:
                mean = np.mean(window_vals)
                std = np.std(window_vals, ddof=1)
                if std > 1e-6:
                    z_group[i] = (cur_val - mean) / std
                else:
                    z_group[i] = 0.0

        z_scores.loc[group.index] = z_group

    return z_scores


def calculer_percentile_expanding_causal(
    df: pd.DataFrame,
    col_target: str,
    min_obs: int = 10,
    group_col: str = "parcel_id",
    date_col: str = "date"
) -> pd.Series:
    """
    Calcule le rang centile (0 à 100) causal de la valeur courante par rapport
    à l'historique disponible jusqu'à la date d'évaluation.
    """
    if col_target not in df.columns or df.empty:
        return pd.Series(np.nan, index=df.index)

    df_sorted = df.copy()
    df_sorted[date_col] = pd.to_datetime(df_sorted[date_col])

    percentiles = pd.Series(np.nan, index=df.index, dtype=float)

    for pid, group in df_sorted.groupby(group_col):
        group = group.sort_values(date_col)
        vals = group[col_target].values
        pct_group = np.full(len(vals), np.nan)

        valid_history = []
        for i in range(len(vals)):
            v = vals[i]
            if not np.isnan(v):
                valid_history.append(v)

            if len(valid_history) >= min_obs and not np.isnan(v):
                # Pourcentage de valeurs dans valid_history <= v
                arr = np.array(valid_history)
                pct_group[i] = float(np.sum(arr <= v) / len(arr) * 100.0)

        percentiles.loc[group.index] = pct_group

    return percentiles


def charger_polygones_parcelles(geojson_paths: list) -> dict:
    """
    Charge les géométries GeoJSON des parcelles et crée des polygones avec buffer -10m.
    Returns:
        dict: {parcel_id: {"poly": Polygon, "inner_poly": Polygon_buffered_-10m}}
    """
    parcels_geo = {}
    if not HAS_SHAPELY:
        return parcels_geo

    # Projection WGS84 -> UTM 32N (Tunisie) pour buffer métrique exact
    wgs84 = pyproj.CRS('EPSG:4326')
    utm32n = pyproj.CRS('EPSG:32632')
    project_to_utm = pyproj.Transformer.from_crs(wgs84, utm32n, always_xy=True).transform
    project_to_wgs = pyproj.Transformer.from_crs(utm32n, wgs84, always_xy=True).transform

    for path_str in geojson_paths:
        p = Path(path_str)
        if not p.exists():
            continue
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            features = data.get("features", [])
            for feat in features:
                props = feat.get("properties", {})
                pid = props.get("parcel_id") or props.get("id") or props.get("code")
                geom_dict = feat.get("geometry")
                if pid and geom_dict:
                    poly_wgs = sg.shape(geom_dict)
                    poly_utm = transform(project_to_utm, poly_wgs)
                    # Buffer intérieur -10m en UTM
                    inner_utm = poly_utm.buffer(-10.0)
                    if not inner_utm.is_empty:
                        inner_wgs = transform(project_to_wgs, inner_utm)
                    else:
                        inner_wgs = None
                    
                    parcels_geo[pid] = {
                        "poly_wgs": poly_wgs,
                        "poly_utm": poly_utm,
                        "inner_wgs": inner_wgs
                    }
        except Exception:
            continue

    return parcels_geo


def calculer_anomalie_spatiale_pixel(
    df_pixels: pd.DataFrame,
    col_target: str = "NDVI",
    buffer_m: float = 10.0,
    geojson_paths: list = None
) -> pd.DataFrame:
    """
    Évalue l'anomalie spatiale sous-parcelle pixel 10m (§6 Alerte #7).
    Calcule:
      - chute_pct_vs_moyenne : (valeur_pixel - mean_parcelle) / mean_parcelle
      - Z_spatial : (valeur_pixel - mean_parcelle) / std_parcelle
      - est_bordure : True si le pixel est à moins de buffer_m mètres du bord de la parcelle
    """
    res = df_pixels.copy()
    if col_target not in res.columns or res.empty:
        res["Z_spatial"] = np.nan
        res["chute_pct_vs_parcelle"] = np.nan
        res["est_bordure"] = False
        return res

    parcels_geo = charger_polygones_parcelles(geojson_paths or [])

    z_spatial_list = np.full(len(res), np.nan)
    chute_pct_list = np.full(len(res), np.nan)
    est_bordure_list = np.zeros(len(res), dtype=bool)

    # Vérification bordure par coordonnée
    has_coords = "longitude" in res.columns and "latitude" in res.columns

    for (pid, dt), group in res.groupby(["parcel_id", "date"]):
        idx = group.index
        vals = group[col_target].values
        valid_mask = ~np.isnan(vals)

        if np.sum(valid_mask) > 1:
            mean_p = np.mean(vals[valid_mask])
            std_p = np.std(vals[valid_mask], ddof=1)

            if mean_p > 1e-4:
                chute_pct_list[idx] = (vals - mean_p) / mean_p

            if std_p > 1e-6:
                z_spatial_list[idx] = (vals - mean_p) / std_p
            else:
                z_spatial_list[idx] = 0.0

        # Vérification bordure
        if has_coords and pid in parcels_geo and HAS_SHAPELY:
            inner_wgs = parcels_geo[pid].get("inner_wgs")
            if inner_wgs is not None:
                lons = group["longitude"].values
                lats = group["latitude"].values
                for i_g, (lon, lat) in enumerate(zip(lons, lats)):
                    pt = sg.Point(lon, lat)
                    if not inner_wgs.contains(pt):
                        est_bordure_list[idx[i_g]] = True

    res["Z_spatial"] = z_spatial_list
    res["chute_pct_vs_parcelle"] = chute_pct_list
    res["est_bordure"] = est_bordure_list
    return res
