#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lai_model.py
===================================================================
Modèle d'estimation du Leaf Area Index (LAI) basé sur Sentinel-2 SL2P.

Calcule le LAI (m²/m²) par inversion physique de Beer-Lambert appliquée sur la
fraction de couverture végétative fCover (issue du réseau de neurones SNAP SL2P).
Les coefficients officiels du réseau de neurones multi-bandes SL2P sont également
inclus dans ce fichier pour référence.
"""

import math
import numpy as np
import pandas as pd

try:
    from config_sante import K_EXTINCTION_CULTURE
except ImportError:
    try:
        from scripts.SANTE_PLANTES.config_sante import K_EXTINCTION_CULTURE
    except ImportError:
        K_EXTINCTION_CULTURE = {
            "Amandier": 0.50, "Olivier": 0.55, "Caroubier": 0.50,
            "Lavande": 0.45, "Romarin": 0.45, "Géranium": 0.50, "Geranium": 0.50,
            "Sauge": 0.45, "Verveine": 0.50, "Thym": 0.40,
            "Citronnelle": 0.60, "Basilic": 0.55, "Menthe": 0.60,
            "Piment": 0.60, "Oignon": 0.50, "DEFAULT": 0.50
        }

# Normalisation accents & alias
_K_LOOKUP = {k.lower().replace("é", "e").replace("è", "e"): v for k, v in K_EXTINCTION_CULTURE.items()}


def obtenir_k_extinction(culture: str = "DEFAULT") -> float:
    """
    Résout le coefficient d'extinction k (Beer-Lambert) pour une culture donnée.
    Gère les polycultures (ex: 'Lavande/Romarin/Geranium') en calculant la moyenne des k.
    """
    if not culture or pd.isna(culture):
        return _K_LOOKUP.get("default", 0.50)

    cult_str = str(culture).strip()
    # Séparateurs polyculture : '/', ',', '+', ';'
    for sep in ["/", ",", "+", ";"]:
        if sep in cult_str:
            parts = [p.strip() for p in cult_str.split(sep) if p.strip()]
            if parts:
                ks = [obtenir_k_extinction(p) for p in parts]
                return float(np.round(float(np.mean(ks)), 3))

    key = cult_str.lower().replace("é", "e").replace("è", "e")
    if key in _K_LOOKUP:
        return float(_K_LOOKUP[key])

    # Recherche partielle par mot-clé
    for k_name, k_val in _K_LOOKUP.items():
        if k_name in key or key in k_name:
            return float(k_val)

    return float(_K_LOOKUP.get("default", 0.50))


# ==============================================================================
# COEFFICIENTS OFFICIELS DU RÉSEAU DE NEURONES SNAP / S2TOOLBOX v2.1 - LAI
# (Source : ATBD S2ToolBox L2B v1.1, Weiss & Baret 2016, auxdata SNAP v2.1)
# ==============================================================================
SL2P_LAI_COEFFS = dict(
    norm_min=[0, 0, 0, 0.00663797254225, 0.0139727270189, 0.0266901380821,
              0.0163880741923, 0, 0.918595400582, 0.342022871159, -0.999999982118],
    norm_max=[0.253061520472, 0.290393577911, 0.305398915249, 0.608900395798,
              0.753827384323, 0.782011770669, 0.493761397883, 0.49302598446,
              0.999999999991, 0.936206429175, 0.99999999891],
    w1=[
        [-0.0234068789665, 0.921655164636, 0.13557654408, -1.9383314724, -3.34249581612, 0.90227764801, 0.205363538259, -0.0406078447217, -0.0831964097271, 0.260029270774, 0.284761567219],
        [-0.132555480857, -0.139574837334, -1.0146060169, -1.33089003865, 0.0317306245033, -1.43358354132, -0.959637898575, 1.13311570655, 0.216603876542, 0.410652303763, 0.0647601555435],
        [0.0860159777249, 0.616648776881, 0.678003876447, 0.141102398645, -0.0966822068835, -1.12883263886, 0.302189102741, 0.4344949373, -0.0219036994906, -0.228492476802, -0.0394605375898],
        [-0.10936659367, -0.0710462629727, 0.0645824114783, 2.90632523682, -0.673873108979, -3.83805186828, 1.69597934453, 0.0469502960817, -0.0497096526884, 0.021829545431, 0.0574838271041],
        [-0.08993941616, 0.175395483106, -0.0818473291726, 2.21989536749, 1.71387397514, 0.7130691861, 0.138970813499, -0.060771761518, 0.124263341255, 0.210086140404, -0.1838781387],
    ],
    b1=[4.96238030555, 1.41600844398, 1.07589704721, 1.53398826466, 3.02411593076],
    w2=[-1.50013548973, -0.0962832691215, -0.194935930577, -0.352305895756, 0.0751074158475],
    b2=1.09696310708,
    denorm_min=0.000319182538301,
    denorm_max=14.4675094548,
    out_tolerance=-0.2,
    out_min=0,
    out_max=8,
)


def estimer_lai_sl2p_fcover(fcover, culture="DEFAULT"):
    """
    Calcule le LAI (m²/m²) par inversion physique de la loi de Beer-Lambert basée sur fCover (SL2P Sentinel-2)
    en utilisant le coefficient d'extinction k spécifique à la culture.
    fCover : float ou pd.Series dans [0, 1]
    """
    k = obtenir_k_extinction(culture)
    if k <= 0:
        k = 0.50

    if isinstance(fcover, (pd.Series, np.ndarray)):
        fc_clean = np.clip(fcover, 0.0, 0.98)
        # Relation Beer-Lambert fCover <-> LAI : fCover = 1 - exp(-k * LAI) => LAI = -ln(1 - fCover) / k
        lai = -np.log(1.0 - fc_clean) / k
        return np.round(np.maximum(0.0, lai), 3)
    else:
        if pd.isna(fcover) or fcover is None:
            return np.nan
        fc_clean = min(max(float(fcover), 0.0), 0.98)
        lai = -math.log(1.0 - fc_clean) / k
        return round(max(0.0, lai), 3)


def calculer_lai_panel(panel):
    """
    Calcule le LAI (m²/m²) par inversion Beer-Lambert sur l'ensemble du panel parcelle x date.
    """
    df = panel.copy()
    df["LAI"] = np.nan
    df["LAI_methode"] = "ABSENT"

    if "fCover" in df.columns and df["fCover"].notna().any():
        for pid, g in df.groupby("parcel_id"):
            culture = g["culture"].iloc[0] if "culture" in g.columns else "DEFAULT"
            mask = g["fCover"].notna()
            idx = g.index[mask]
            df.loc[idx, "LAI"] = estimer_lai_sl2p_fcover(g.loc[idx, "fCover"], culture=culture)
            df.loc[idx, "LAI_methode"] = "BEER_LAMBERT_FCOVER_SL2P"

    return df

