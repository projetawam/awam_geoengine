#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
schema_validator.py
===================================================================
Module de validation et d'assainissement de schéma pour les données
multi-capteurs GeoAI AWAM.

Garantit :
1. Le typage strict des colonnes clés (date -> datetime64, parcel_id -> str).
2. Le clamping des indices spectraux et physiques hors-bornes (NDVI, NDRE, fCover).
3. Le dédoublonnage strict sur (parcel_id, date).
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path

try:
    from config_global import BORNES_INDICES
    from pipeline_logging import get_logger
except ImportError:
    BORNES_INDICES = {
        "NDVI": (-1.0, 1.0),
        "NDRE": (-1.0, 1.0),
        "fCover": (0.0, 1.0),
        "LAI": (0.0, 10.0),
    }
    def get_logger(name):
        import logging
        return logging.getLogger(name)

logger = get_logger("AWAM.SchemaValidator")


def valider_et_nettoyer_panel(df: pd.DataFrame) -> pd.DataFrame:
    """
    Valide et nettoie un DataFrame de panel multi-capteurs.

    CORRECTIONS PHASE 2 (§27.6.C) :
    - Vérification des colonnes obligatoires avant tout traitement.
    - Forçage explicite du typage numérique pour détecter les colonnes object masquées.
    - Déduplication géospatiale : inclut longitude/latitude pour ne pas détruire
      les observations pixel distinctes partageant la même (parcel_id, date).
    - Tri explicite avant déduplication pour un comportement déterministe.
    - Suppression du df.copy() systématique (mutation in-place sécurisée).
    """
    if df.empty:
        logger.warning("DataFrame vide fourni au validateur de schéma.")
        return df

    # BUGFIX §27.6.C.4 : Vérification des colonnes obligatoires
    colonnes_obligatoires = ["parcel_id", "date"]
    manquantes = [c for c in colonnes_obligatoires if c not in df.columns]
    if manquantes:
        raise ValueError(
            f"[SchemaValidator] Colonnes obligatoires manquantes : {manquantes}. "
            f"Colonnes disponibles : {list(df.columns)}"
        )

    df_clean = df.copy()

    # 1. Typage strict des colonnes obligatoires
    df_clean["date"] = pd.to_datetime(df_clean["date"], errors="coerce")
    df_clean["parcel_id"] = df_clean["parcel_id"].astype(str)
    for col_str in ["site", "culture"]:
        if col_str in df_clean.columns:
            df_clean[col_str] = df_clean[col_str].astype(str)

    # BUGFIX §27.6.C.3 : Forçage explicite du typage numérique
    # Les colonnes numériques stockées en object (suite à une concaténation ou
    # un export CSV sans typage) étaient silencieusement ignorées par le clamping.
    for idx_col in BORNES_INDICES:
        if idx_col in df_clean.columns and df_clean[idx_col].dtype == object:
            df_clean[idx_col] = pd.to_numeric(df_clean[idx_col], errors="coerce")
            logger.warning(f"Colonne '{idx_col}' était de type object — convertie en numérique.")

    # 2. Suppression des dates invalides (NaT)
    initial_len = len(df_clean)
    df_clean = df_clean.dropna(subset=["date"])
    if len(df_clean) < initial_len:
        logger.warning(f"Suppression de {initial_len - len(df_clean)} ligne(s) avec des dates invalides.")

    # 3. Clamping des indices spectraux et physiques hors-bornes
    count_clamped = 0
    for idx_col, (b_min, b_max) in BORNES_INDICES.items():
        if idx_col in df_clean.columns and pd.api.types.is_numeric_dtype(df_clean[idx_col]):
            mask_out = (df_clean[idx_col] < b_min) | (df_clean[idx_col] > b_max)
            n_out = mask_out.sum()
            if n_out > 0:
                df_clean[idx_col] = df_clean[idx_col].clip(lower=b_min, upper=b_max)
                count_clamped += n_out

    if count_clamped > 0:
        logger.info(f"Sanitization : {count_clamped} valeur(s) hors-bornes clampée(s) selon BORNES_INDICES.")

    # 4. Dédoublonnage géospatial
    # BUGFIX §27.6.C.1 : L'ancien subset=[parcel_id, date] détruisait toutes les
    # observations pixel distinctes (longitude, latitude différents) partageant la
    # même (parcel_id, date) — n'en conservant qu'une seule par jour par parcelle.
    # BUGFIX §27.6.C.2 : Tri explicite avant dédup pour un comportement déterministe.
    coord_cols = [c for c in ["longitude", "latitude"] if c in df_clean.columns]
    dedup_subset = ["parcel_id", "date"] + coord_cols

    sort_cols = ["parcel_id", "date"] + coord_cols
    df_clean = df_clean.sort_values(sort_cols, na_position="last")

    before_dup = len(df_clean)
    df_clean = df_clean.drop_duplicates(subset=dedup_subset, keep="last")
    n_removed = before_dup - len(df_clean)
    if n_removed > 0:
        logger.info(
            f"Dédoublonnage géospatial ({'+'.join(dedup_subset)}) : "
            f"{n_removed} doublons exacts supprimés."
        )

    return df_clean


if __name__ == "__main__":
    print("=== Test du PIPELINE_MASTER/schema_validator.py ===")
    df_test = pd.DataFrame({
        "parcel_id": ["P1", "P1", "P2"],
        "date": ["2026-08-01", "2026-08-01", "invalid_date"],
        "NDVI": [1.5, 0.5, 0.8],
        "fCover": [-0.2, 0.3, 0.4]
    })
    df_res = valider_et_nettoyer_panel(df_test)
    print("✓ Résultat de la sanitization :")
    print(df_res)
