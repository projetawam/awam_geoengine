#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compute_health_scores.py
===================================================================
Calcul des 7 scores composites de santé des plantes + 2 ajouts méthodologiques
(Qualité du Sol & Stress Température).

Réutilise `detect_irrigation_vs_pluie_v3.py` pour le facteur d'échelle et
l'importation des données.

Principe clé :
- Tous les indices et scores sont TOUJOURS CALCULÉS, mais accompagnés d'un tag
  de confiance (HAUTE, MOYENNE, BASSE) déterminé par le fCover.
- Aucun score n'est bloqué, garantissant une visibilité complète.
"""

import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd

# Extrait pour accéder au dossier IRRIGATION si besoin
IRRIGATION_DIR = Path(__file__).resolve().parent.parent / "IRRIGATION"
sys.path.insert(0, str(IRRIGATION_DIR))

try:
    import detect_irrigation_vs_pluie_v3 as irr
except ImportError:
    irr = None

from config_sante import (
    SEUIL_FCOVER_FAIBLE,
    SEUIL_FCOVER_MOYEN,
    STADES_PHENOLOGIQUES_PAR_CULTURE,
    SEUIL_DECOUPLAGE_NDRE_NDVI,
    SEUIL_HUMIDITE_ERA5_MALADIE,
    SEUIL_TEMP_OPTIMALE_MALADIE,
    SEUIL_GEL_RISQUE_LEGER,
    SEUIL_GEL_RISQUE_SEVERE,
    SEUIL_CHALEUR_STRESS_C,
)
from lai_model import calculer_lai_panel


def determiner_confiance_fcover(fcover_val):
    """
    Retourne la confiance ('HAUTE', 'MOYENNE', 'BASSE') basée sur le fCover.
    """
    if pd.isna(fcover_val) or fcover_val is None:
        return "BASSE"
    fc = float(fcover_val)
    if fc >= SEUIL_FCOVER_MOYEN:
        return "HAUTE"
    elif fc >= SEUIL_FCOVER_FAIBLE:
        return "MOYENNE"
    else:
        return "BASSE"


def normaliser_0_100(valeur, min_val, max_val, inverse=False):
    """
    Normalise une valeur dans [0, 100].
    Si inverse=True, min_val donne 100 et max_val donne 0.
    """
    if pd.isna(valeur):
        return np.nan
    if max_val == min_val:
        return 50.0
    val_clamped = np.clip(valeur, min(min_val, max_val), max(min_val, max_val))
    norm = (val_clamped - min_val) / (max_val - min_val)
    if inverse:
        norm = 1.0 - norm
    return round(float(np.clip(norm * 100.0, 0.0, 100.0)), 2)


def obtenir_bornes_ndvi_culture(culture_str):
    """Retourne la plage NDVI [min, max] ajustée selon le profil de la culture."""
    if not culture_str or pd.isna(culture_str):
        return 0.10, 0.60
    c = str(culture_str).lower()
    if any(k in c for k in ["thym", "romarin", "sauge", "lavande"]):
        return 0.10, 0.45  # Aromatiques basses à biomasse modérée
    elif any(k in c for k in ["olivier", "amandier", "caroubier"]):
        return 0.10, 0.65  # Vergers / arbres à haut NDVI
    else:
        return 0.10, 0.60  # Maraîchage / biomasse dense


# ===========================================================================
# 1. SCORE VIGUEUR VÉGÉTATIVE
# ===========================================================================
def calculer_score_vigueur_vegetative(panel):
    """
    Score Vigueur Végétative (0-100) : Indice composite de NDVI, SAVI/MSAVI, EVI, VARI.
    Ajusté pour tenir compte des bornes NDVI spécifiques à la culture.
    """
    df = panel.copy()
    scores = []
    for _, row in df.iterrows():
        sub_scores = []
        cult_name = row.get("culture_declaree_parcelle", row.get("culture"))
        ndvi_min, ndvi_max = obtenir_bornes_ndvi_culture(cult_name)

        # NDVI (plage ajustée à la culture)
        if "NDVI" in row and not pd.isna(row["NDVI"]):
            sub_scores.append(normaliser_0_100(row["NDVI"], ndvi_min, ndvi_max))
            
        # SAVI / MSAVI (plage 0.08 à 0.50)
        savi_val = row.get("SAVI", row.get("MSAVI"))
        if savi_val is not None and not pd.isna(savi_val):
            sub_scores.append(normaliser_0_100(savi_val, 0.08, 0.50))
            
        # EVI (plage 0.05 à 0.60)
        if "EVI" in row and not pd.isna(row["EVI"]):
            sub_scores.append(normaliser_0_100(row["EVI"], 0.05, 0.60))
            
        # VARI calibré si disponible, sinon VARI brut (plage -0.10 à 0.40)
        vari_val = row.get("VARI_calibre", row.get("VARI"))
        if vari_val is not None and not pd.isna(vari_val):
            sub_scores.append(normaliser_0_100(vari_val, -0.10, 0.40))
            
        if sub_scores:
            scores.append(round(float(np.mean(sub_scores)), 2))
        else:
            scores.append(np.nan)

    df["score_vigueur_vegetative"] = scores
    return df


# ===========================================================================
# 2. SCORE CHLOROPHYLLE
# ===========================================================================
def calculer_score_chlorophylle(panel):
    """
    Score Chlorophylle (0-100) : NDRE, CI_RedEdge.
    Très informatif même sous occupation faible (signal RedEdge résilient).
    """
    df = panel.copy()
    scores = []
    for _, row in df.iterrows():
        sub = []
        
        # NDRE (plage 0.05 à 0.35)
        if "NDRE" in row and not pd.isna(row["NDRE"]):
            sub.append(normaliser_0_100(row["NDRE"], 0.05, 0.35))
            
        # CI_RedEdge (plage 0.10 à 1.50)
        if "CI_RedEdge" in row and not pd.isna(row["CI_RedEdge"]):
            sub.append(normaliser_0_100(row["CI_RedEdge"], 0.10, 1.50))
            
        if sub:
            scores.append(round(float(np.mean(sub)), 2))
        else:
            scores.append(np.nan)

    df["score_chlorophylle"] = scores
    return df


# ===========================================================================
# 3. SCORE STRESS HYDRIQUE
# ===========================================================================
def calculer_score_stress_hydrique(panel):
    """
    Score Stress Hydrique (0-100, 100 = aucun stress / hydraté, 0 = stress extrême).
    Combine NDMI, NDWI, CWSI_proxy, SMI, soil_moisture_vol.
    """
    df = panel.copy()
    scores = []
    for _, row in df.iterrows():
        sub = []
        
        # NDMI (plage -0.15 à 0.30) -> plus haut est meilleur
        if "NDMI" in row and not pd.isna(row["NDMI"]):
            sub.append(normaliser_0_100(row["NDMI"], -0.15, 0.30))
            
        # NDWI (plage -0.20 à 0.20)
        if "NDWI" in row and not pd.isna(row["NDWI"]):
            sub.append(normaliser_0_100(row["NDWI"], -0.20, 0.20))
            
        # SMI (Soil Moisture Index 0 à 1) -> plus haut = plus humide
        if "SMI" in row and not pd.isna(row["SMI"]):
            sub.append(normaliser_0_100(row["SMI"], 0.10, 0.80))
            
        # CWSI_proxy (0 à 1) -> plus bas = moins de stress
        if "CWSI_proxy" in row and not pd.isna(row["CWSI_proxy"]):
            sub.append(normaliser_0_100(row["CWSI_proxy"], 0.10, 0.85, inverse=True))
            
        # Soil Moisture NISAR (0.02 à 0.35 m3/m3)
        if "soil_moisture_vol" in row and not pd.isna(row["soil_moisture_vol"]):
            sub.append(normaliser_0_100(row["soil_moisture_vol"], 0.03, 0.30))

        if sub:
            scores.append(round(float(np.mean(sub)), 2))
        else:
            scores.append(np.nan)

    df["score_stress_hydrique"] = scores
    return df


# ===========================================================================
# 4. SCORE COUVERTURE CANOPÉE
# ===========================================================================
def calculer_score_couverture_canopee(panel):
    """
    Score Couverture Canopée (0-100) : fCover et LAI.
    Brique de base (confiance_signal_pct).
    """
    df = panel.copy()
    if "LAI" not in df.columns:
        df = calculer_lai_panel(df)

    scores = []
    for _, row in df.iterrows():
        sub = []
        
        # fCover (0 à 0.60)
        if "fCover" in row and not pd.isna(row["fCover"]):
            sub.append(normaliser_0_100(row["fCover"], 0.0, 0.50))
            
        # LAI (0 à 3.0 m2/m2)
        if "LAI" in row and not pd.isna(row["LAI"]):
            sub.append(normaliser_0_100(row["LAI"], 0.0, 2.50))

        if sub:
            scores.append(round(float(np.mean(sub)), 2))
        else:
            scores.append(np.nan)

    df["score_couverture_canopee"] = scores
    return df


# ===========================================================================
# 5. SCORE SUIVI PHÉNOLOGIQUE (GESTION DE LA POLYCULTURE)
# ===========================================================================
def extraire_cles_culture_multi(culture_str):
    """
    Mappe la chaîne de culture (incluant les associations polyculturales ex: 'Lavande/Romarin/Geranium')
    à toutes les clés correspondantes dans STADES_PHENOLOGIQUES_PAR_CULTURE.
    """
    if not culture_str or pd.isna(culture_str):
        return ["DEFAULT"]
    c_str = str(culture_str).lower()
    
    if any(s in c_str for s in ["sol nu", "sol_nu", "bare_soil", "nu"]):
        return ["SOL_NU"]

    candidates = [
        ("lavande", "Lavande"), ("romarin", "Romarin"), ("sauge", "Sauge"),
        ("géranium", "Geranium"), ("geranium", "Geranium"), ("verveine", "Verveine"),
        ("thym", "Thym"), ("citronnelle", "Citronnelle"), ("olivier", "Olivier"),
        ("amandier", "Amandier"), ("caroubier", "Caroubier"), ("piment", "Piment"),
        ("oignon", "Oignon")
    ]
    trouves = []
    for kw, key in candidates:
        if kw in c_str and key not in trouves:
            trouves.append(key)
    return trouves if trouves else ["DEFAULT"]


def calculer_score_suivi_phenologique(panel):
    """
    Score Suivi Phénologique (0-100) : Compare les trajectoires observées
    aux plages attendues (NDVI/NDRE) par mois et par culture (ou association multi-cultures).
    Pour les polycultures, évalue chaque sous-culture individuellement et calcule
    la moyenne des scores pour éviter la dilution du pouvoir de détection.
    """
    df = panel.copy()
    scores = []
    stades_libelles = []

    for _, row in df.iterrows():
        d = pd.to_datetime(row["date"])
        mois = d.month
        cult_keys = extraire_cles_culture_multi(row.get("culture_declaree_parcelle", row.get("culture")))

        if "SOL_NU" in cult_keys:
            scores.append(np.nan)
            stades_libelles.append("Sol nu (Non applicable)")
            continue

        stades_noms = []
        sub_scores_per_crop = []

        ndvi_obs = row.get("NDVI")
        ndre_obs = row.get("NDRE")
        has_optique = (ndvi_obs is not None and not pd.isna(ndvi_obs)) or (ndre_obs is not None and not pd.isna(ndre_obs))

        if not has_optique:
            scores.append(np.nan)
            for k in cult_keys:
                stades_spec = STADES_PHENOLOGIQUES_PAR_CULTURE.get(k, STADES_PHENOLOGIQUES_PAR_CULTURE["DEFAULT"])
                stade_trouve = next((spec for spec in stades_spec if mois in spec["mois"]), stades_spec[0])
                stades_noms.append(stade_trouve["stade"])
            stades_libelles.append(" / ".join(list(dict.fromkeys(stades_noms))))
            continue

        for k in cult_keys:
            stades_spec = STADES_PHENOLOGIQUES_PAR_CULTURE.get(k, STADES_PHENOLOGIQUES_PAR_CULTURE["DEFAULT"])
            stade_trouve = next((spec for spec in stades_spec if mois in spec["mois"]), stades_spec[0])
            stades_noms.append(stade_trouve["stade"])

            crop_sub = []
            if ndvi_obs is not None and not pd.isna(ndvi_obs):
                t_min = stade_trouve["ndvi_min"]
                t_max = stade_trouve["ndvi_max"]
                if t_min <= ndvi_obs <= t_max:
                    crop_sub.append(90.0)
                elif ndvi_obs > t_max:
                    crop_sub.append(80.0)
                else:
                    ecart = t_min - ndvi_obs
                    crop_sub.append(max(20.0, 70.0 - ecart * 200.0))

            if ndre_obs is not None and not pd.isna(ndre_obs):
                t_min = stade_trouve["ndre_min"]
                t_max = stade_trouve["ndre_max"]
                if t_min <= ndre_obs <= t_max:
                    crop_sub.append(90.0)
                elif ndre_obs > t_max:
                    crop_sub.append(85.0)
                else:
                    ecart = t_min - ndre_obs
                    crop_sub.append(max(20.0, 70.0 - ecart * 300.0))

            if crop_sub:
                sub_scores_per_crop.append(float(np.mean(crop_sub)))

        stades_libelles.append(" / ".join(list(dict.fromkeys(stades_noms))))

        if sub_scores_per_crop:
            scores.append(round(float(np.mean(sub_scores_per_crop)), 2))
        else:
            scores.append(np.nan)

    df["score_suivi_phenologique"] = scores
    df["stade_phenologique_attendu"] = stades_libelles
    return df


# ===========================================================================
# 6. SCORE DÉTECTION D'ANOMALIES
# ===========================================================================
def calculer_score_detection_anomalie(panel, horizon_jours=30):
    """
    Score Détection d'Anomalies (0-100, 100 = aucune anomalie, 0 = anomalie sévère).
    Détecte les chutes brutales de NDVI ou NDMI par rapport à la baseline glissante.
    Si les indices optiques manquent, retourne NaN plutôt que 100 (pour ne pas masquer les goulots).
    """
    df = panel.copy()
    scores_res = []

    for parcel_id, g in df.groupby("parcel_id", sort=False):
        gg = g.set_index("date").sort_index()
        
        has_ndvi = "NDVI" in gg.columns and gg["NDVI"].notna().sum() >= 3
        has_ndmi = "NDMI" in gg.columns and gg["NDMI"].notna().sum() >= 3

        if has_ndvi:
            baseline_ndvi = gg["NDVI"].rolling(f"{horizon_jours}D", min_periods=3).median()
            delta_ndvi = (gg["NDVI"] - baseline_ndvi).values
            chute_ndvi = np.where((gg["NDVI"].notna()) & (delta_ndvi < -0.05), np.abs(delta_ndvi) * 200.0, 0.0)
        else:
            chute_ndvi = None

        if has_ndmi:
            baseline_ndmi = gg["NDMI"].rolling(f"{horizon_jours}D", min_periods=3).median()
            delta_ndmi = (gg["NDMI"] - baseline_ndmi).values
            chute_ndmi = np.where((gg["NDMI"].notna()) & (delta_ndmi < -0.05), np.abs(delta_ndmi) * 200.0, 0.0)
        else:
            chute_ndmi = None

        for idx in range(len(gg)):
            ndvi_val = gg["NDVI"].iloc[idx] if "NDVI" in gg.columns else np.nan
            ndmi_val = gg["NDMI"].iloc[idx] if "NDMI" in gg.columns else np.nan
            
            if pd.isna(ndvi_val) and pd.isna(ndmi_val):
                scores_res.append(np.nan)
            else:
                pen_v = chute_ndvi[idx] if chute_ndvi is not None and not pd.isna(ndvi_val) else 0.0
                pen_m = chute_ndmi[idx] if chute_ndmi is not None and not pd.isna(ndmi_val) else 0.0
                pen = max(pen_v, pen_m)
                scores_res.append(round(float(np.clip(100.0 - pen, 0.0, 100.0)), 2))

    df["score_detection_anomalie"] = scores_res
    return df


# ===========================================================================
# 7. SCORE RISQUE DE MALADIES
# ===========================================================================
def calculer_score_risque_maladie(panel):
    """
    Score Risque de Maladies (0-100, 100 = risque nul, 0 = risque élevé).
    Évalue :
    1. Le découplage NDRE vs NDVI (chlorose / baisse de chlorophylle spécifique via SEUIL_DECOUPLAGE_NDRE_NDVI)
    2. Les conditions météo propices aux spores fongiques (T° 18-26°C et RH >= 80% ou pluie > 2mm).
    Retourne NaN si aucune donnée optique ni météo n'est disponible.
    """
    df = panel.copy()
    scores = []
    
    for _, row in df.iterrows():
        eval_done = False
        risque_penalite = 0.0

        # 1. Découplage NDRE vs NDVI (seuil abaissé à NDVI > 0.08 pour couvrir parcelles jeunes/taillées)
        ndvi = row.get("NDVI")
        ndre = row.get("NDRE")
        if ndvi is not None and ndre is not None and not pd.isna(ndvi) and not pd.isna(ndre):
            eval_done = True
            if ndvi > 0.08:
                ratio = ndre / ndvi
                if ratio < 0.35 or (ratio - 0.5) < SEUIL_DECOUPLAGE_NDRE_NDVI:
                    risque_penalite += 30.0

        # 2. Conditions météo favorables aux champignons (Pluie récurrente ou RH >= 80% & T 18-26°C)
        tmax = row.get("Tmax_C")
        tmin = row.get("Tmin_C")
        precip = row.get("precip_mm")
        rh = row.get("RH_pct", row.get("rh_era5", row.get("relative_humidity_pct")))

        if tmax is not None and tmin is not None and not pd.isna(tmax) and not pd.isna(tmin):
            eval_done = True
            t_moy = (tmax + tmin) / 2.0
            if SEUIL_TEMP_OPTIMALE_MALADIE[0] <= t_moy <= SEUIL_TEMP_OPTIMALE_MALADIE[1]:
                humidite_elevee = False
                if rh is not None and not pd.isna(rh) and rh >= SEUIL_HUMIDITE_ERA5_MALADIE:
                    humidite_elevee = True
                elif precip is not None and not pd.isna(precip) and precip > 2.0:
                    humidite_elevee = True

                if humidite_elevee:
                    risque_penalite += 35.0

        if eval_done:
            score_final = max(0.0, 100.0 - risque_penalite)
            scores.append(round(score_final, 2))
        else:
            scores.append(np.nan)

    df["score_risque_maladie"] = scores
    return df


# ===========================================================================
# 8. AJOUT MÉTHODOLOGIQUE 1 : SCORE QUALITÉ DU SOL (Propriétés GeoJSON)
# ===========================================================================
def calculer_score_qualite_sol(panel):
    """
    Score Qualité du Sol (0-100) : Exploite pH, Matière Organique (MO%), Salinité.
    Extrait dynamiquement les propriétés du GeoJSON (sol_ph, sol_matiere_organique_pct, sol_salinite_g_L / sol_salinite_ds_m / sol_ec_mS_cm),
    avec fallback via get_map_parcelles_terrain() ou métadonnées terrain.
    """
    df = panel.copy()
    scores = []

    try:
        from PIPELINE_MASTER.config_global import get_map_parcelles_terrain
        terrain_map = get_map_parcelles_terrain()
    except Exception:
        try:
            from config_global import get_map_parcelles_terrain
            terrain_map = get_map_parcelles_terrain()
        except Exception:
            terrain_map = {}

    for _, row in df.iterrows():
        pid = row["parcel_id"]
        # Extraction dynamique des colonnes GeoJSON si présentes
        ph = row.get("sol_ph", row.get("ph"))
        mo = row.get("sol_matiere_organique_pct", row.get("mo", row.get("sol_mo")))
        sal = row.get("sol_salinite_g_L", row.get("sol_salinite_ds_m", row.get("sol_salinite", row.get("salinite", row.get("sol_ec_mS_cm")))))

        if pd.isna(ph) or pd.isna(mo) or pd.isna(sal):
            meta = terrain_map.get(pid, {})
            if meta:
                ph = meta.get("sol_ph") if pd.isna(ph) else ph
                mo = meta.get("sol_mo") if pd.isna(mo) else mo
                sal = meta.get("sol_salinite") if pd.isna(sal) else sal

        if pd.isna(ph) or pd.isna(mo) or pd.isna(sal):
            scores.append(65.0) # Valeur neutre par défaut pour parcelles sans analyse de sol
            continue

        s_ph = 100.0 if 6.5 <= ph <= 7.8 else (70.0 if ph <= 8.3 else 40.0)
        s_mo = normaliser_0_100(mo, 0.5, 3.5)
        s_sal = normaliser_0_100(sal, 0.05, 1.0, inverse=True)

        score_sol = round(0.4 * s_ph + 0.4 * s_mo + 0.2 * s_sal, 2)
        scores.append(score_sol)

    df["score_qualite_sol"] = scores
    return df


# ===========================================================================
# 9. AJOUT MÉTHODOLOGIQUE 2 : SCORE STRESS TEMPÉRATURE / GEL (ERA5)
# ===========================================================================
def calculer_score_temperature_stress(panel):
    """
    Score Stress Température (0-100) : Détecte les chocs thermiques (Canicule Tmax >= 38°C)
    et les risques de gel tardif (Tmin <= 0°C).
    """
    df = panel.copy()
    scores = []

    for _, row in df.iterrows():
        tmax = row.get("Tmax_C")
        tmin = row.get("Tmin_C")

        penalite = 0.0
        if tmax is not None and not pd.isna(tmax):
            if tmax >= SEUIL_CHALEUR_STRESS_C:
                penalite += (tmax - SEUIL_CHALEUR_STRESS_C) * 8.0

        if tmin is not None and not pd.isna(tmin):
            if tmin <= SEUIL_GEL_RISQUE_SEVERE:
                penalite += 60.0
            elif tmin <= SEUIL_GEL_RISQUE_LEGER:
                penalite += 30.0

        scores.append(round(max(0.0, 100.0 - penalite), 2))

    df["score_temperature_stress"] = scores
    return df


def integrer_vari_calibre(panel):
    """
    Intègre le VARI calibré issu de outputs/raw_vari_calibration/ (photos terrain).
    Extrait prioritairement la colonne 'vari_calibration_offset' du GeoJSON, sinon défaut 0.0.
    VARI_calibrated = VARI + offset_calibration
    """
    df = panel.copy()
    if "VARI" in df.columns:
        if "vari_calibration_offset" in df.columns:
            offsets = df["vari_calibration_offset"].fillna(0.0)
        else:
            offsets = 0.0
        df["VARI_calibre"] = df["VARI"] + offsets
    else:
        df["VARI_calibre"] = np.nan
    return df


def appliquer_masque_nuages_et_qa(panel):
    """
    Filtre Qualité (QA) : Masque les indices optiques si cloud_flag == 1.
    Garantit qu'un pixel ennuagé n'est pas injecté dans le calcul des scores.
    """
    df = panel.copy()
    if "cloud_flag" in df.columns:
        cols_optiques = ["NDVI", "SAVI", "MSAVI", "EVI", "NDRE", "CI_RedEdge", "VARI", "VARI_calibre", "NDWI", "NDMI", "fCover"]
        present = [c for c in cols_optiques if c in df.columns]
        if present:
            mask_nuage = df["cloud_flag"] == 1
            df.loc[mask_nuage, present] = np.nan
    return df


def interpoler_toutes_les_sources_multi_capteurs(panel):
    """
    Interpolation temporelle multi-capteurs (forward-fill causale par parcelle).

    Règles :
    - Filtre QA nuage préalable (cloud_flag).
    - Métadonnées parcelle (culture, surface, signal_partage) : ffill + bfill (valeur constante).
    - Indices optiques S2 : ffill(10j) — la biomasse ne disparaît pas entre 2 passages.
    - Radar S1/NISAR : ffill(14j) — revisit ~12 jours.
    - Thermique (MODIS/Landsat/ECOSTRESS) : ffill(14j).
    - Météo ERA5 (Tmin, Tmax, GDD) : ffill(5j) — températures quasi-quotidiennes.
    - Précipitations (precip_mm) : AUCUN forward-fill (flux journalier). NaNs remplis par 0.0.
    """
    df = panel.copy()
    df = appliquer_masque_nuages_et_qa(df)

    # Métadonnées parcelle uniquement (valeurs constantes par parcelle)
    cols_meta_str = ["culture_declaree_parcelle", "signal_partage", "area_h"]
    present_meta = [c for c in cols_meta_str if c in df.columns]

    groups_and_limits = [
        (["NDVI", "SAVI", "MSAVI", "EVI", "NDRE", "CI_RedEdge", "VARI", "VARI_calibre",
          "NDWI", "NDMI", "BSI", "Carbonate_SWIR", "NDSI_soil", "SI_soil", "fCover"], 10),
        (["VV_dB", "VH_dB", "VH_VV_ratio", "DpRVIc", "HH_gamma0_dB", "HV_gamma0_dB", "RVI_NISAR"], 14),
        (["LST_K", "SMI", "CWSI_proxy", "LST_Landsat_K", "LST_Landsat_C", "NDVI_Landsat",
          "LST_ECOSTRESS_K", "LST_ECOSTRESS_C"], 14),
        (["Tmin_C", "Tmax_C", "GDD_cumul", "frost_risk"], 5),
    ]

    dfs_parcelles = []
    for parcel_id, g in df.groupby("parcel_id", sort=False):
        g_sorted = g.sort_values("date").copy()

        # Métadonnées : ffill + bfill (constantes par parcelle)
        if present_meta:
            g_sorted[present_meta] = g_sorted[present_meta].ffill().bfill().infer_objects(copy=False)

        # Données capteurs : ffill limité par la fréquence de revisite
        for cols, lim in groups_and_limits:
            present = [c for c in cols if c in g_sorted.columns]
            if present:
                g_sorted[present] = g_sorted[present].ffill(limit=lim)

        # Précipitations : flux journalier strictement non propagé dans le temps
        if "precip_mm" in g_sorted.columns:
            g_sorted["precip_mm"] = g_sorted["precip_mm"].fillna(0.0)

        dfs_parcelles.append(g_sorted)

    df_res = pd.concat(dfs_parcelles, axis=0)
    return df_res


# ===========================================================================
# CALCUL COMPLET DE TOUS LES SCORES COMPOSITES
# ===========================================================================
def calculer_tous_les_scores_sante(panel):
    """
    Enchaîne le calcul des 7 scores composites + LAI + 2 ajouts méthodologiques.
    Assigne le tag de confiance fCover sur chaque ligne.
    """
    df = panel.copy()

    # 0. Intégration du VARI calibré & Interpolation multi-capteurs
    df = integrer_vari_calibre(df)
    df = interpoler_toutes_les_sources_multi_capteurs(df)

    # 1. Estimation LAI
    df = calculer_lai_panel(df)

    # 2. Confiance fCover
    if "fCover" in df.columns:
        df["confiance_signal"] = df["fCover"].apply(determiner_confiance_fcover)
    else:
        df["confiance_signal"] = "BASSE"

    # 3. Les 7 scores composites
    df = calculer_score_vigueur_vegetative(df)
    df = calculer_score_chlorophylle(df)
    df = calculer_score_stress_hydrique(df)
    df = calculer_score_couverture_canopee(df)
    df = calculer_score_suivi_phenologique(df)
    df = calculer_score_detection_anomalie(df)
    df = calculer_score_risque_maladie(df)

    # 4. Ajouts méthodologiques
    df = calculer_score_qualite_sol(df)
    df = calculer_score_temperature_stress(df)

    return df
