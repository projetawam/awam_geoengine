#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
moteur_cascades.py
===================================================================
Moteur de Cascades Causales (implementation_plan_v2.md §11).

Analyse les alertes générées par detect_alertes.py et identifie les chaînes
de causalité complexes (Chaîne 1: Canicule -> Stress Hydrique -> Carence résiduelle,
Chaîne 2: Engorgement -> Lessivage Nitrates -> Stress Azoté, Chaîne 3: Escalade panne).

Conserve impérativement 3 axes distincts dans la sortie :
- score_confiance
- gravite
- statut_cascade
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = MODULE_DIR.parent
IRRIGATION_DIR = SCRIPTS_DIR / "IRRIGATION"
SANTE_DIR = SCRIPTS_DIR / "SANTE_PLANTES"

for p in [str(SCRIPTS_DIR), str(IRRIGATION_DIR), str(SANTE_DIR), str(MODULE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Import réutilisé depuis IRRIGATION (§11.3)
try:
    import detect_besoin_vs_irrigation as dbi
    croiser_besoin_irrigation = dbi.croiser_besoin_irrigation
except ImportError:
    def croiser_besoin_irrigation(df_panel):
        return pd.DataFrame()


def executer_moteur_cascades(
    df_alertes_all: pd.DataFrame,
    df_panel: pd.DataFrame = None
) -> pd.DataFrame:
    """
    Évalue les dépendances et enchaînements causaux sur l'ensemble des alertes.

    Returns:
        pd.DataFrame pour 4_diagnostics_cascades.csv
    """
    if df_alertes_all.empty:
        return pd.DataFrame(columns=[
            "site", "parcel_id", "date", "culture", "type_alerte",
            "statut_cascade", "chaine_id", "noeud_precedent", "diagnostic_texte"
        ])

    df = df_alertes_all.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["parcel_id", "date"]).reset_index(drop=True)

    results = []

    for (pid, culture), group in df.groupby(["parcel_id", "culture"]):
        group = group.sort_values("date").reset_index(drop=True)

        for i, row in group.iterrows():
            t_alt = row["type_alerte"]
            dt_cur = row["date"]
            site = row["site"]

            statut_casc = "ISOLEE"
            chaine_id = np.nan
            noeud_prec = ""
            diag_txt = "Alerte indépendante sans chaîne causale détectée."

            # ---------------------------------------------------------------
            # Chaîne 1 : Canicule (#4) -> Stress Hydrique (#1/#3) -> Stress Azoté résiduel (#2)
            # ---------------------------------------------------------------
            if t_alt == "ALERTE_2_STRESS_AZOTE_FORT":
                # Chercher une alerte #1 ou #3 dans les 7-21 jours précédents
                sub_prev_hydr = group[
                    (group["type_alerte"].isin(["ALERTE_1_STRESS_HYDRIQUE", "ALERTE_3_STRESS_COMBINE_EAU_AZOTE"])) &
                    (group["date"] < dt_cur) &
                    (group["date"] >= dt_cur - pd.Timedelta(days=21))
                ]
                if not sub_prev_hydr.empty:
                    alt_hydr = sub_prev_hydr.iloc[-1]
                    dt_hydr = alt_hydr["date"]

                    # Chercher canicule #4 amont
                    sub_prev_canic = group[
                        (group["type_alerte"] == "ALERTE_4_STRESS_THERMIQUE_CANICULE") &
                        (group["date"] <= dt_hydr) &
                        (group["date"] >= dt_hydr - pd.Timedelta(days=10))
                    ]

                    if not sub_prev_canic.empty:
                        chaine_id = 1
                        noeud_prec = f"{alt_hydr['type_alerte']} du {dt_hydr.strftime('%Y-%m-%d')}"
                        statut_casc = "CHAINE_TEMPORELLEMENT_COHERENTE"
                        diag_txt = (
                            f"Carence azotée RÉSIDUELLE post-stress hydrique (l'assimilation a été "
                            f"interrompue suite à la canicule du {sub_prev_canic.iloc[-1]['date'].strftime('%Y-%m-%d')} "
                            f"et au stress hydrique du {dt_hydr.strftime('%Y-%m-%d')})."
                        )

            # ---------------------------------------------------------------
            # Chaîne 2 : Excès d'Humidité (#5) -> Stress Azoté (#2) post-pluie
            # ---------------------------------------------------------------
            elif t_alt == "ALERTE_2_STRESS_AZOTE_FORT" and np.isnan(chaine_id):
                sub_prev_exces = group[
                    (group["type_alerte"] == "ALERTE_5_EXCES_HUMIDITE_ENGORGEMENT") &
                    (group["date"] < dt_cur) &
                    (group["date"] >= dt_cur - pd.Timedelta(days=15))
                ]
                if not sub_prev_exces.empty:
                    alt_exces = sub_prev_exces.iloc[-1]
                    chaine_id = 2
                    noeud_prec = f"ALERTE_5_EXCES_HUMIDITE_ENGORGEMENT du {alt_exces['date'].strftime('%Y-%m-%d')}"
                    statut_casc = "CORRELATION_TEMPORELLE_NON_CONFIRMEE"
                    diag_txt = (
                        f"Carence azotée probablement liée au lessivage des nitrates après l'épisode "
                        f"pluvieux du {alt_exces['date'].strftime('%Y-%m-%d')} (hypothèse agronomique "
                        f"standard de lessivage/hypoxie racinaire, non mesurable directement par satellite)."
                    )

            # ---------------------------------------------------------------
            # Escalade / Cascade Alerte 10 : Écart d'occupation qualifié
            # ---------------------------------------------------------------
            elif t_alt == "ALERTE_10_ECART_OCCUPATION_REELLE_VS_DECLAREES":
                # Chercher si un stress hydrique/thermique récent a provoqué cette perte de feuillage
                sub_prev_stress = group[
                    (group["type_alerte"].isin(["ALERTE_1_STRESS_HYDRIQUE", "ALERTE_3_STRESS_COMBINE_EAU_AZOTE", "ALERTE_4_STRESS_THERMIQUE_CANICULE", "ALERTE_6_SECHERESSE_PROLONGEE"])) &
                    (group["date"] < dt_cur) &
                    (group["date"] >= dt_cur - pd.Timedelta(days=30))
                ]
                if not sub_prev_stress.empty:
                    alt_st = sub_prev_stress.iloc[-1]
                    chaine_id = 1
                    noeud_prec = f"{alt_st['type_alerte']} du {alt_st['date'].strftime('%Y-%m-%d')}"
                    statut_casc = "CHAINE_TEMPORELLEMENT_COHERENTE"
                    diag_txt = f"Défoliation / Écart de couvert résiduel consécutif au stress ({alt_st['nom_alerte']} du {alt_st['date'].strftime('%Y-%m-%d')})."
                else:
                    details_str = str(row.get("details", ""))
                    if "Couvert clairsemé" in details_str:
                        diag_txt = "Structure de couvert naturellement clairsemée (jeune plantation ou espacement d'arbres sur sol nu inter-rangs). Aucune anomalie active."
                    elif "Sol nu persistant" in details_str:
                        diag_txt = "Parcelle en sol nu continu (jachère ou préparation de sol, culture non implantée). Aucun risque de défoliation."
                    else:
                        diag_txt = "Écart de couvert isolé (à vérifier sur le terrain)."

            # ---------------------------------------------------------------
            # Chaîne 3 : Escalade Panne Matérielle (#13 + Besoin Non Comblé)
            # ---------------------------------------------------------------
            elif t_alt == "ALERTE_13_IRRIGATION_SANS_REPONSE_HYDRIQUE":
                chaine_id = 3
                noeud_prec = ""
                statut_casc = "CRITIQUE_CASCADANTE"
                diag_txt = (
                    "Panne matérielle probable (goutte-à-goutte/pompe) : irrigation déclarée sans "
                    "réponse hydrique mesurée par satellite."
                )

            results.append({
                "site": site,
                "parcel_id": pid,
                "date": dt_cur,
                "culture": culture,
                "type_alerte": t_alt,
                "statut_cascade": statut_casc,
                "chaine_id": chaine_id if not np.isnan(chaine_id) else "",
                "noeud_precedent": noeud_prec,
                "diagnostic_texte": diag_txt
            })

    return pd.DataFrame(results)
