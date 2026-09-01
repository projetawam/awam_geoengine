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

# S'assurer que les répertoires clés existent
for _d in [LOGS_DIR, OUTPUT_DIR_SANTE, OUTPUT_DIR_IRRIG, OUTPUT_DIR_ALERTES, PARCELLES_DIR]:
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
        return df_parcelles

    except Exception as e:
        print(f"  [❌] Erreur lors de la lecture du GeoJSON {geojson_path} : {e}")
        return pd.DataFrame()


def get_map_parcelles_terrain(geojson_path: Path = None) -> dict:
    """
    Construit le dictionnaire de mapping (parcel_id -> métadonnées terrain)
    à partir du GeoJSON pour remplacer le dictionnaire hardcodé PARCELLES_TERRAIN.
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
        }
    return parcelles_map


if __name__ == "__main__":
    print("=== Test du module PIPELINE_MASTER/config_global.py ===")
    df_p = load_parcelles_from_geojson()
    print(f"✓ {len(df_p)} parcelles chargées depuis {GEOJSON_DEFAULT_PATH.name} :")
    if not df_p.empty:
        print(df_p[["parcel_id", "culture", "area_h"]].to_string())
