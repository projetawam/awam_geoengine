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
    """
    if df.empty:
        logger.warning("DataFrame vide fourni au validateur de schéma.")
        return df

    df_clean = df.copy()

    # 1. Typage strict des colonnes obligatoires
    if "date" in df_clean.columns:
        df_clean["date"] = pd.to_datetime(df_clean["date"], errors="coerce")
    
    for col_str in ["parcel_id", "site", "culture"]:
        if col_str in df_clean.columns:
            df_clean[col_str] = df_clean[col_str].astype(str)

    # 2. Suppression des dates invalides (NaT)
    if "date" in df_clean.columns:
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

    # 4. Dédoublonnage sur (parcel_id, date) si présent
    if "parcel_id" in df_clean.columns and "date" in df_clean.columns:
        before_dup = len(df_clean)
        df_clean = df_clean.drop_duplicates(subset=["parcel_id", "date"], keep="last")
        if len(df_clean) < before_dup:
            logger.info(f"Dédoublonnage : {before_dup - len(df_clean)} doublons supprimés.")

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
