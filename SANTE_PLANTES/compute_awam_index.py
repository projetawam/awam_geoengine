#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compute_awam_index.py
===================================================================
Agrégation des 7 scores composites de santé des plantes en un Indice de Santé AWAM
global (0-100).

Applique les pondérations validées par l'utilisateur :
- Vigueur végétative : 20%
- Chlorophylle        : 15%
- Stress hydrique     : 20%
- Couverture canopée  : 15%
- Suivi phénologique  : 10%
- Détection anomalies : 10%
- Risque maladies     : 10%

Avertissement & Règle de transparence :
Tous les scores sont TOUJOURS CALCULÉS. Si fCover < 15% (mode SUIVI_BRUT ou ANOMALIE_AUTO_REFERENCEE),
l'Indice AWAM est calculé mais le statut/pastille porte la mention claire :
'⚠️ CONFIANCE BASSE / MOYENNE (signal sol nu prédominant)' afin de ne jamais tromper l'utilisateur.
"""

import numpy as np
import pandas as pd
from config_sante import (
    POIDS_SANTE_AWAM_DEFAUT,
    SEUIL_PASTILLE_SAIN,
    SEUIL_PASTILLE_ATTENTION,
    SEUIL_FCOVER_FAIBLE,
    SEUIL_FCOVER_MOYEN,
)


def attribuer_pastille_sante(score_awam, confiance):
    """
    Attribue la pastille visuelle et le libellé de statut.
    """
    if pd.isna(score_awam) or score_awam is None:
        return "⚪ NON_EVALUABLE", "Aucune donnée disponible"

    score = float(score_awam)

    if score >= SEUIL_PASTILLE_SAIN:
        pastille_base = "🟢 SAIN"
        libelle_base = "Excellente santé végétale"
    elif score >= SEUIL_PASTILLE_ATTENTION:
        pastille_base = "🟡 ATTENTION"
        libelle_base = "Vigilance recommandée (stress ou retard)"
    else:
        pastille_base = "🔴 CRITIQUE"
        libelle_base = "Stress ou dégradation sévère"

    if confiance == "BASSE":
        return f"{pastille_base} ⚠️ (Confiance BASSE)", f"{libelle_base} - Note: fCover < 5%, signal dominé par le sol nu"
    elif confiance == "MOYENNE":
        return f"{pastille_base} ⚠️ (Confiance MOYENNE)", f"{libelle_base} - Note: fCover 5-15%, occupation partielle"
    else:
        return pastille_base, libelle_base


def calculer_indice_sante_awam(panel, poids_custom=None):
    """
    Calcule l'Indice de Santé AWAM (0-100) pour chaque ligne d'un panel enrichi.
    Exige la présence d'au moins une donnée optique/canopée (NDVI/fCover/Vigueur/Canopée),
    sinon retourne NaN et marque le statut comme ⚪ DONNÉES INSUFFISANTES.
    Si la parcelle est en Sol Nu, retourne ⚪ SOL_NU.
    """
    df = panel.copy()
    poids = poids_custom if poids_custom else POIDS_SANTE_AWAM_DEFAUT

    somme_poids = sum(poids.values())
    poids_norm = {k: v / somme_poids for k, v in poids.items()}

    scores_awam = []
    pastilles = []
    explications = []
    modes_confiance = []

    for _, row in df.iterrows():
        fcover = row.get("fCover", np.nan)
        confiance = row.get("confiance_signal", "BASSE")
        cult_name = str(row.get("culture_declaree_parcelle", row.get("culture", ""))).lower()

        # Mode de confiance
        if not pd.isna(fcover) and fcover >= SEUIL_FCOVER_MOYEN:
            mode = "DIAGNOSTIC_COMPLET"
        elif not pd.isna(fcover) and fcover >= SEUIL_FCOVER_FAIBLE:
            mode = "ANOMALIE_AUTO_REFERENCEE"
        else:
            mode = "SUIVI_BRUT"

        modes_confiance.append(mode)

        # 1. CAS PARTICULIER : PARCELLE EN SOL NU
        if any(s in cult_name for s in ["sol nu", "sol_nu", "bare_soil"]) or cult_name in ["nu", "sol nu"]:
            scores_awam.append(np.nan)
            pastilles.append("⚪ SOL_NU")
            explications.append("Parcelle déclarée en sol nu (indice de santé non applicable)")
            continue

        # 2. VÉRIFICATION DE LA PRÉSENCE DES SCORES CLÉS OPTIQUES / CANOPÉE
        s_vigueur = row.get("score_vigueur_vegetative")
        s_canopee = row.get("score_couverture_canopee")
        ndvi_val = row.get("NDVI")

        optical_available = (
            (s_vigueur is not None and not pd.isna(s_vigueur)) or
            (s_canopee is not None and not pd.isna(s_canopee)) or
            (ndvi_val is not None and not pd.isna(ndvi_val))
        )

        if not optical_available:
            # SÉCURITÉ CRITIQUE : Si aucune donnée optique n'est disponible, l'AWAM NE PEUT PAS s'évaluer !
            scores_awam.append(np.nan)
            pastilles.append("⚪ NON_EVALUABLE")
            explications.append("Absence d'acquisitions optiques (Sentinel-2/fCover) : données insuffisantes pour évaluer la santé végétale")
            continue

        # 3. CALCUL DE LA SOMME PONDÉRÉE DES SCORES DISPONIBLES
        valeurs_dispo = []
        poids_actifs = []

        for score_col, weight in poids_norm.items():
            val = row.get(score_col)
            if val is not None and not pd.isna(val):
                valeurs_dispo.append(float(val))
                poids_actifs.append(weight)

        if valeurs_dispo:
            w_sum = sum(poids_actifs)
            score_final = sum(v * (w / w_sum) for v, w in zip(valeurs_dispo, poids_actifs))
            # Règle biophysique (Loi du minimum de Liebig & non-contradiction inter-modules) :
            # Si le stress hydrique est déficitaire (< 60), l'indice global de santé ne peut prétendre
            # à l'excellence (>= 80, Santé Optimale) car le facteur eau est limitant.
            s_hydr = row.get("score_stress_hydrique")
            if s_hydr is not None and not pd.isna(s_hydr) and float(s_hydr) < 60.0:
                score_final = min(score_final, 79.0)
            score_final = round(float(np.clip(score_final, 0.0, 100.0)), 2)
            pastille_str, explication_str = attribuer_pastille_sante(score_final, confiance)
        else:
            score_final = np.nan
            pastille_str = "⚪ NON_EVALUABLE"
            explication_str = "Aucun sous-score disponible pour calculer l'indice AWAM"

        scores_awam.append(score_final)
        pastilles.append(pastille_str)
        explications.append(explication_str)

    df["score_sante_awam"] = scores_awam
    df["mode_confiance"] = modes_confiance
    df["pastille_sante"] = pastilles
    df["diagnostic_explication"] = explications

    return df
