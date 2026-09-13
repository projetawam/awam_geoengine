#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config_global.py
===================================================================
Configuration globale centralisée et utilitaires spatiaux pour la
plateforme analytique GeoAI AWAM.

Centralise :
1. Les chemins canoniques des répertoires et fichiers d'entrée/sortie.
2. Le chargement dynamique universel des parcelles à partir de fichiers GeoJSON.
3. Les constantes temporelles, spatiales et les bornes physiques des indices.
"""

import os
import sys
import json
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ===========================================================================
# 1. CHEMINS CANONIQUES ET ARBORESCENCE
# ===========================================================================
PIPELINE_MASTER_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = PIPELINE_MASTER_DIR.parent
ROOT_DIR = SCRIPTS_DIR.parent

DATA_CLEAN_DIR = SCRIPTS_DIR / "outputs" / "pixel_indices_database" / "clean"
REGISTRE_EVENTS_PATH = PIPELINE_MASTER_DIR / "registre_evenements_terrain.csv"

# Centralized GeoJSON paths (AWAM naming convention)
PARCELLES_DIR = SCRIPTS_DIR / "parcelles_geojson"
GEOJSON_ALL_PARCELS_PATH = PARCELLES_DIR / "AWAM_TERRAIN_ALL_ALL_Boundaries_20250501_20260828_v1.0.geojson"
GEOJSON_MAKTHAR_PATH = PARCELLES_DIR / "AWAM_TERRAIN_makthar_ALL_Boundaries_20250501_20260828_v1.0.geojson"
GEOJSON_SIDI_PATH = PARCELLES_DIR / "AWAM_TERRAIN_sidi-mechreg_ALL_Boundaries_20250501_20260828_v1.0.geojson"
GEOJSON_DEFAULT_PATH = GEOJSON_ALL_PARCELS_PATH

LOGS_DIR = SCRIPTS_DIR / "logs"

OUTPUT_DIR_SANTE = SCRIPTS_DIR / "SANTE_PLANTES" / "output"
OUTPUT_DIR_IRRIG = SCRIPTS_DIR / "IRRIGATION" / "outputs" / "irrigation"
OUTPUT_DIR_ALERTES = SCRIPTS_DIR / "MODULE_ALERTES" / "output"
OUTPUT_DIR_TOPO = SCRIPTS_DIR / "outputs" / "topography"

# Fichiers topographiques standardisés AWAM (MNT SRTM 30m)
TOPOGRAPHY_PARQUET_CLEAN_PATH = DATA_CLEAN_DIR / "AWAM_DEM_ALL_ALL_SRTM-Topography_20250501_20260828_v2_clean.parquet"
TOPOGRAPHY_PARQUET_PATH = OUTPUT_DIR_TOPO / "AWAM_DEM_ALL_ALL_SRTM-Topography_20250501_20260828_v2_clean.parquet"
TOPOGRAPHY_CSV_PATH = OUTPUT_DIR_TOPO / "AWAM_DEM_ALL_ALL_SRTM-Topography_20250501_20260828_v2_clean.csv"

# S'assurer que les répertoires clés existent
for _d in [LOGS_DIR, OUTPUT_DIR_SANTE, OUTPUT_DIR_IRRIG, OUTPUT_DIR_ALERTES, OUTPUT_DIR_TOPO, PARCELLES_DIR, DATA_CLEAN_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ===========================================================================
# 2. CONSTANTES DE BORNES PHYSIQUES ET SEUILS DE QUALITÉ
# ===========================================================================
DEFAULT_CRS = "EPSG:4326"

BORNES_INDICES = {
    "NDVI": (-1.0, 1.0),
    "NDRE": (-1.0, 1.0),
    "NDWI": (-1.0, 1.0),
    "NDMI": (-1.0, 1.0),
    "SAVI": (-1.0, 1.0),
    "MSAVI": (-1.0, 1.0),
    "EVI": (-1.0, 1.0),
    "VARI": (-1.0, 1.0),
    "CI_RedEdge": (0.0, 15.0),
    "fCover": (0.0, 1.0),
    "LAI": (0.0, 10.0),
    "BSI": (-1.0, 1.0),
    "CWSI_proxy": (0.0, 1.0),
    "SMI": (0.0, 1.0),
    "soil_moisture_vol": (0.0, 100.0),
}


# ===========================================================================
# 3. CHARGEUR DYNAMIQUE ET UNIVERSEL DE PARCELLES GEOJSON
# ===========================================================================
def load_parcelles_from_geojson(geojson_path: Path = None) -> pd.DataFrame:
    """
    Charge n'importe quel fichier GeoJSON de parcelles et retourne un DataFrame
    contenant les attributs et métadonnées de sol/eau/culture.
    Permet un découplage total : zéro ID de parcelle hardcodé dans le code.
    """
    if geojson_path is None:
        geojson_path = GEOJSON_DEFAULT_PATH
    
    geojson_path = Path(geojson_path).resolve()
    if not geojson_path.exists():
        print(f"  [⚠] Fichier GeoJSON non trouvé : {geojson_path}")
        return pd.DataFrame()

    try:
        with open(geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        records = []
        for feat in features:
            props = feat.get("properties", {}).copy()
            geom = feat.get("geometry", {})
            
            fid = props.get("fid") or props.get("id")
            nom_parcelle = props.get("name") or props.get("nom") or f"Parcelle_{fid}"
            
            # Formater l'ID canonique de parcelle (ex: sidi_mechreg_Parcelle_Badreddine_5 ou makthar_P1)
            if "parcel_id" in props and props["parcel_id"]:
                canon_id = props["parcel_id"]
            else:
                site_prefix = geojson_path.stem.split("_")[3] if len(geojson_path.stem.split("_")) > 3 else "site"
                if site_prefix not in nom_parcelle.lower():
                    canon_id = f"sidi_mechreg_{nom_parcelle.replace(' ', '_')}_{fid}"
                else:
                    canon_id = nom_parcelle

            props["parcel_id"] = canon_id
            props["geometry_type"] = geom.get("type", "Unknown")
            records.append(props)

        df_parcelles = pd.DataFrame(records)

        # Fusion avec la table topographique statique (GeoParquet / Parquet standardisé prioritaire)
        topo_path_found = None
        if TOPOGRAPHY_PARQUET_CLEAN_PATH.exists():
            topo_path_found = TOPOGRAPHY_PARQUET_CLEAN_PATH
        elif TOPOGRAPHY_PARQUET_PATH.exists():
            topo_path_found = TOPOGRAPHY_PARQUET_PATH
        elif TOPOGRAPHY_CSV_PATH.exists():
            topo_path_found = TOPOGRAPHY_CSV_PATH

        if topo_path_found is not None:
            try:
                if str(topo_path_found).endswith(".parquet"):
                    df_topo = pd.read_parquet(topo_path_found)
                else:
                    df_topo = pd.read_csv(topo_path_found)
                cols_topo = [c for c in df_topo.columns if c not in ["site", "culture", "area_h"]]
                df_parcelles = df_parcelles.merge(df_topo[cols_topo], on="parcel_id", how="left")
            except Exception as e:
                print(f"  [⚠] Impossible de fusionner les données topographiques depuis {topo_path_found.name} : {e}")

        return df_parcelles

    except Exception as e:
        print(f"  [❌] Erreur lors de la lecture du GeoJSON {geojson_path} : {e}")
        return pd.DataFrame()


def get_map_parcelles_terrain(geojson_path: Path = None) -> dict:
    """
    Construit le dictionnaire de mapping (parcel_id -> métadonnées terrain & topographie)
    à partir du GeoJSON et de la table topographique.
    """
    df_p = load_parcelles_from_geojson(geojson_path)
    if df_p.empty:
        return {}

    parcelles_map = {}
    for _, row in df_p.iterrows():
        pid = row.get("parcel_id")
        nom = row.get("name") or row.get("nom") or pid
        culture = row.get("culture", "Inconnue")
        area_h = float(row.get("area_h", 1.0))
        
        parcelles_map[pid] = {
            "nom": nom,
            "culture": culture,
            "area_h": area_h,
            "sol_ph": row.get("sol_ph"),
            "sol_nitrates": row.get("sol_nitrates_N_mg_L"),
            "sol_mo": row.get("sol_matiere_organique_pct"),
            "sol_salinite": row.get("sol_salinite_g_L") or row.get("sol_salinite_ds_m") or row.get("sol_ec_mS_cm"),
            "sol_ec": row.get("sol_ec_mS_cm"),
            "sol_texture": row.get("sol_texture"),
            "sol_diagnostic": row.get("sol_diagnostic"),
            "eau_ph": row.get("eau_ph"),
            "eau_ec": row.get("eau_ec_uS_cm"),
            "eau_statut": row.get("eau_statut"),
            "statut_phytosanitaire": row.get("statut_phytosanitaire", "NORMAL"),
            "pathogene_identifie": row.get("pathogene_identifie"),
            # Métadonnées topographiques (§27.7.6)
            "elevation_m": row.get("elevation_m", 900.0 if "makthar" in str(pid).lower() else 50.0),
            "slope_deg": row.get("slope_deg", 1.5),
            "slope_pct": row.get("slope_pct", 2.6),
            "aspect_cardinal": row.get("aspect_cardinal", "PLAT"),
            "exposition_type": row.get("exposition_type", "TRANSITION"),
            "twi_proxy": row.get("twi_proxy", 8.0),
            "position_relief": row.get("position_relief", "VERSANT_DOUX"),
            "correction_thermique_lapse_rate_c": row.get("correction_thermique_lapse_rate_c", 0.0),
        }
    return parcelles_map


# ===========================================================================
# 4. MODÈLES BIOPHYSIQUES TOPOGRAPHIQUES (§27.7.6)
# ===========================================================================
def corriger_temperature_altitude(t_era5: float, elevation_m: float, elevation_ref_m: float = 650.0) -> float:
    """
    Applique la correction adiabatique environnementale (-6.5 °C / 1000m)
    sur une température brute ERA5-Land.
    """
    if t_era5 is None or pd.isna(t_era5):
        return t_era5
    delta_z = float(elevation_m) - float(elevation_ref_m)
    delta_t = delta_z * (-0.0065)
    return round(float(t_era5) + delta_t, 2)


def calculer_coefficient_ruissellement(slope_deg: float, texture_sol: str = "LIMONEUX") -> float:
    """
    Calcule le coefficient de ruissellement (0.0 à 0.50) modulant l'infiltration
    effective de la pluie et de l'irrigation (FAO-56 Dual).
    """
    if slope_deg is None or pd.isna(slope_deg):
        slope_deg = 1.0
    
    s_deg = float(slope_deg)
    # Base de ruissellement selon la pente
    if s_deg < 2.0:
        c_pente = 0.05
    elif s_deg < 5.0:
        c_pente = 0.12
    elif s_deg < 10.0:
        c_pente = 0.22
    else:
        c_pente = 0.35

    # Modulation selon texture
    tex = str(texture_sol).upper() if texture_sol else "LIMONEUX"
    if "ARGILE" in tex:
        c_tex = 1.2  # Infiltration plus lente -> ruissellement accru
    elif "SABL" in tex:
        c_tex = 0.6  # Infiltration rapide -> ruissellement réduit
    else:
        c_tex = 1.0

    return min(0.50, round(c_pente * c_tex, 3))


if __name__ == "__main__":
    print("=== Test du module PIPELINE_MASTER/config_global.py ===")
    df_p = load_parcelles_from_geojson()
    print(f"✓ {len(df_p)} parcelles chargées depuis {GEOJSON_DEFAULT_PATH.name} :")
    if not df_p.empty:
        cols_show = [c for c in ["parcel_id", "culture", "area_h", "elevation_m", "slope_deg", "exposition_type"] if c in df_p.columns]
        print(df_p[cols_show].to_string())
