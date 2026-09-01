#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_besoin_vs_irrigation.py
===================================================================
Croise le BESOIN D'EAU (stress hydrique détecté depuis des indices déjà
présents dans votre base -- CWSI_proxy, SMI, humidité du sol NISAR SME2,
baisse de NDMI/NDWI) avec les jours d'IRRIGATION DÉTECTÉE par
detect_irrigation_vs_pluie_v3.py, pour répondre à la question :

    "Les jours où les plantes avaient besoin d'eau, ont-elles
     réellement été irriguées, ou non ?"

Ce script NE RÉ-IMPLÉMENTE RIEN de la détection d'irrigation elle-même : il
IMPORTE detect_irrigation_vs_pluie_v3.py comme bibliothèque (même dossier)
et réutilise ses fonctions telles quelles (découverte de fichiers, panel
multi-capteur, score composite d'irrigation, classification pluie/été-hiver).
Une seule source de vérité pour cette logique -- si vous corrigez un seuil
ou une formule là-bas, ce script en bénéficie automatiquement.

CE QUE CE SCRIPT AJOUTE : un second axe, symétrique, pour le BESOIN :

  Signal de stress          Source            Sens du signal
  -------------------------------------------------------------------------
  CWSI_proxy élevé          MODIS-LST         proche de l'extrême "sec"
                                               historique DE CETTE PARCELLE
                                               (indice déjà causal -- voir
                                               gee_export_pixel_indices_
                                               database.py, fenêtre expanding)
  SMI bas                   MODIS-LST         idem, sens inverse (SMI haut
                                               = humide)
  soil_moisture_vol bas     NISAR SME2        sous le 20e percentile observé
                                               JUSQU'ICI pour cette parcelle
                                               (fenêtre expanding, causale)
  Baisse de NDMI / NDWI     S2-Indices        assèchement de surface détecté
                                               optiquement (corroboration
                                               secondaire, poids plus faible)

Chaque signal est optionnel et n'active son module que si la colonne
correspondante existe dans vos fichiers -- exactement la même philosophie
adaptative que le script d'irrigation (un sous-ensemble de capteurs suffit,
le script ne plante jamais faute d'un capteur absent).

DEUX TABLEAUX EN SORTIE :
  1. rapport_..._besoin_vs_irrigation.csv : un jour de STRESS par ligne,
     avec le verdict "comblé par une irrigation détectée dans les N jours
     qui suivent" ou "NON comblé".
  2. rapport_..._irrigation_vs_besoin.csv : la vue symétrique -- pour
     chaque irrigation détectée, y avait-il un stress détecté avant
     (irrigation RÉACTIVE) ou non (PRÉVENTIVE / planifiée / stress non
     capté par les capteurs disponibles) ?

USAGE
-----
    python detect_besoin_vs_irrigation.py --dry-run
        Résumé des modules de stress activés + validation sur l'événement
        connu (Kemel/Yahia), sans écrire de CSV.

    python detect_besoin_vs_irrigation.py --data-dir /chemin/vers/parquet
        Croisement complet sur toute la période.

Dépendances : identiques à detect_irrigation_vs_pluie_v3.py (scipy, requests
optionnels). Les deux scripts doivent être dans le même dossier.
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# Extrait corrigé pour detect_besoin_vs_irrigation.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import detect_irrigation_vs_pluie_v3 as irr
except ImportError:
    raise SystemExit(
        "Impossible d'importer detect_irrigation_vs_pluie_v3.py -- assurez-vous "
        "que ce script se trouve dans le même dossier."
    )


# ===========================================================================
# CONFIGURATION -- seuils de stress (besoin d'eau)
# ===========================================================================

# CWSI_proxy et SMI sont déjà des indices [0,1] normalisés PAR PARCELLE sur
# une fenêtre causale (expanding, cf. gee_export...py) -- on les seuille
# directement, pas besoin d'une anomalie de second ordre.
SEUIL_CWSI_STRESS = 0.70     # CWSI_proxy >= seuil -> proche de l'extrême sec observé jusqu'ici
SEUIL_SMI_STRESS = 0.30      # SMI <= seuil -> idem (SMI haut = humide, donc bas = sec)

# soil_moisture_vol est en m3/m3 (grandeur physique), pas normalisée : on la
# seuille relativement à SA PROPRE PARCELLE (percentile expanding causal),
# car le point de flétrissement dépend de la texture du sol, inconnue ici.
PERCENTILE_SM_SEC = 20.0
BASELINE_JOURS_SM = 30

# NDMI/NDWI : une BAISSE sous la baseline propre à la parcelle corrobore un
# assèchement de surface (logique inverse de evidence_optique() dans le
# script d'irrigation, qui traite une HAUSSE comme preuve d'irrigation).
SEUIL_BAISSE_NDMI_STRESS = -0.05
SEUIL_BAISSE_NDWI_STRESS = -0.05
BASELINE_JOURS_OPTIQUE_STRESS = 30

# Score de stress composite minimal pour flaguer un jour "besoin d'eau"
SEUIL_SCORE_STRESS = 1.0

# Fenêtres de croisement stress <-> irrigation détectée
FENETRE_REPONSE_APRES_JOURS = 5    # au lieu de 10 — un délai de 10j est trop long pour dire
                                    # qu'une irrigation "répond" à un stress sur du goutte-à-goutte
FENETRE_REPONSE_AVANT_JOURS = 2    # au lieu de 3
FENETRE_PRECEDENT_STRESS_JOURS = 10  # pour la vue symétrique (irrigation réactive vs préventive)


# ===========================================================================
# ÉVIDENCES DE STRESS HYDRIQUE (besoin d'eau)
# ===========================================================================

def evidence_stress_cwsi(panel, seuil=SEUIL_CWSI_STRESS, seuil_abs=0.85, poids=2.0):
    if "CWSI_proxy" not in panel.columns or panel["CWSI_proxy"].notna().sum() == 0:
        return panel, False
    
    # Garde-fou de cohérence physique : CWSI_proxy doit être un indice normalisé dans [0, 1]
    cwsi_vals = panel["CWSI_proxy"].dropna()
    if not cwsi_vals.empty and (cwsi_vals.min() < -0.05 or cwsi_vals.max() > 1.05):
        print(f"  [⚠] Valeurs CWSI_proxy hors bornes [0, 1] (min={cwsi_vals.min():.2f}, max={cwsi_vals.max():.2f}) — vérifiez l'export GEE.")

    flag_rel = panel["CWSI_proxy"] >= seuil
    flag_abs = panel["CWSI_proxy"] >= seuil_abs
    # CWSI_proxy vient de MODIS-LST (1 km) -- correction d'echelle pour anomalies relatives,
    # mais si CWSI >= 0.85 (plateau de sécheresse absolue), poids fixe de 1.5 pts garanti
    # pour capturer la canicule prolongée sans fuite par la baseline glissante.
    fe = panel["parcel_id"].map(lambda pid: irr.facteur_echelle(pid, irr.SOURCE_SPECS["MODIS-LST"]["resolution_m"])).values
    panel["stress_CWSI_facteur_echelle"] = fe
    panel["stress_CWSI_evidence"] = np.where(flag_abs, 1.5, np.where(flag_rel, poids * fe, 0.0))
    panel["stress_CWSI_flag"] = flag_rel | flag_abs
    panel["stress_CWSI_capteur"] = "MODIS-LST"
    return panel, True


def evidence_stress_smi(panel, seuil=SEUIL_SMI_STRESS, poids=1.5):
    if "SMI" not in panel.columns or panel["SMI"].notna().sum() == 0:
        return panel, False
    flag = panel["SMI"] <= seuil
    fe = panel["parcel_id"].map(lambda pid: irr.facteur_echelle(pid, irr.SOURCE_SPECS["MODIS-LST"]["resolution_m"])).values
    panel["stress_SMI_facteur_echelle"] = fe
    panel["stress_SMI_evidence"] = np.where(flag, poids, 0.0) * fe
    panel["stress_SMI_flag"] = flag
    panel["stress_SMI_capteur"] = "MODIS-LST"
    return panel, True


def evidence_stress_soil_moisture(panel, percentile=PERCENTILE_SM_SEC, poids=3.0,
                                   baseline_jours=BASELINE_JOURS_SM):
    """Stress si soil_moisture_vol tombe au/sous le {percentile}e percentile
    le plus sec observé JUSQU'À PRÉSENT pour CETTE parcelle (fenêtre
    expanding, causale -- aucune fuite d'information future : le seuil du
    1er mai 2025 ne dépend pas des observations d'août 2026)."""
    if "soil_moisture_vol" not in panel.columns or panel["soil_moisture_vol"].notna().sum() == 0:
        return panel, False
    panel["stress_SM_seuil_sec"] = np.nan
    for parcel_id, g in panel.groupby("parcel_id"):
        gg = g.set_index("date").sort_index()
        seuil_sec = gg["soil_moisture_vol"].expanding(min_periods=5).quantile(percentile / 100.0)
        panel.loc[g.sort_values("date").index, "stress_SM_seuil_sec"] = seuil_sec.values
    flag = panel["soil_moisture_vol"] <= panel["stress_SM_seuil_sec"]
    fe = panel["parcel_id"].map(lambda pid: irr.facteur_echelle(pid, irr.SOURCE_SPECS["NISAR-SoilMoisture"]["resolution_m"])).values
    panel["stress_SM_facteur_echelle"] = fe
    panel["stress_SM_evidence"] = np.where(flag, poids, 0.0) * fe
    panel["stress_SM_flag"] = flag
    panel["stress_SM_capteur"] = "NISAR-SoilMoisture"
    return panel, True


SEUILS_ABSOLUS_OPTIQUE = {
    "NDMI": -0.12,
    "NDRE": 0.055,
    "BSI": 0.22,
}


def evidence_stress_optique(panel, colonne, seuil, poids, sens_baisse=True, baseline_jours=BASELINE_JOURS_OPTIQUE_STRESS):
    """Corrobore le stress optique (combinaison anomalie relative + seuil absolu de sécheresse prolongée) :
    - sens_baisse=True (ex: NDMI, NDWI, NDRE) : baisse sous la baseline = assèchement / stress.
    - sens_baisse=False (ex: BSI) : hausse de BSI au-dessus de la baseline = assèchement du sol nu.
    """
    if colonne not in panel.columns or panel[colonne].notna().sum() == 0:
        return panel, False
    col_anom = f"{colonne}_anomalie"
    if col_anom not in panel.columns:
        panel[col_anom] = np.nan
        for parcel_id, g in panel.groupby("parcel_id"):
            gg = g.set_index("date").sort_index()
            baseline = gg[colonne].rolling(f"{baseline_jours}D", min_periods=3).median()
            anom = (gg[colonne] - baseline).values
            panel.loc[g.sort_values("date").index, col_anom] = anom
    flag_rel = (panel[col_anom] <= seuil) if sens_baisse else (panel[col_anom] >= seuil)
    seuil_abs = SEUILS_ABSOLUS_OPTIQUE.get(colonne)
    if seuil_abs is not None:
        flag_abs = (panel[colonne] <= seuil_abs) if sens_baisse else (panel[colonne] >= seuil_abs)
        flag = flag_rel | flag_abs
    else:
        flag = flag_rel
    panel[f"stress_{colonne}_evidence"] = np.where(flag, poids, 0.0)
    panel[f"stress_{colonne}_flag"] = flag
    return panel, True


def calculer_score_stress(panel):
    cols = [c for c in panel.columns if c.startswith("stress_") and c.endswith("_evidence")]

    familles_cols = {}
    for col in cols:
        label_prefixe = "stress_" + col[len("stress_"):-len("_evidence")]
        famille = irr.FAMILLE_CAPTEUR.get(label_prefixe, "AUTRE")
        familles_cols.setdefault(famille, []).append(col)

    panel["score_stress"] = 0.0
    panel["sources_stress"] = [[] for _ in range(len(panel))]

    for famille, f_cols in familles_cols.items():
        score_famille = pd.Series(0.0, index=panel.index)
        for col in f_cols:
            val_col = panel[col].fillna(0)
            score_famille += val_col
            label = col[len("stress_"):-len("_evidence")]
            actif = val_col > 0
            for i in panel.index[actif]:
                if label not in panel.at[i, "sources_stress"]:
                    panel.at[i, "sources_stress"].append(label)

        cap_famille = irr.POIDS_MAX_PAR_FAMILLE.get(famille, 2.5)
        panel["score_stress"] += score_famille.clip(upper=cap_famille)

    panel["n_sources_stress"] = panel["sources_stress"].apply(len)

    panel["capteurs_independants_stress"] = [set() for _ in range(len(panel))]
    for col in cols:
        label_prefixe = "stress_" + col[len("stress_"):-len("_evidence")]
        famille = irr.FAMILLE_CAPTEUR.get(label_prefixe)
        if famille is None:
            continue
        actif = panel[col].fillna(0) > 0
        for i in panel.index[actif]:
            panel.at[i, "capteurs_independants_stress"].add(famille)
    panel["n_capteurs_independants_stress"] = panel["capteurs_independants_stress"].apply(len)
    panel["capteurs_independants_stress"] = panel["capteurs_independants_stress"].apply(lambda s: sorted(s))
    return panel


# ===========================================================================
# CROISEMENT BESOIN <-> IRRIGATION DÉTECTÉE
# ===========================================================================

def croiser_besoin_irrigation(panel, seuil_score_stress=SEUIL_SCORE_STRESS,
                               seuil_score_irrigation=None,
                               fenetre_apres=FENETRE_REPONSE_APRES_JOURS,
                               fenetre_avant=FENETRE_REPONSE_AVANT_JOURS):
    """Un jour de STRESS par ligne. Cherche si une irrigation a été détectée
    (score_composite déjà calculé par detect_irrigation_vs_pluie_v3.py) dans
    la fenêtre [-fenetre_avant, +fenetre_apres] jours autour de cette date,
    POUR LA MÊME PARCELLE.

    Adaptation culture : si fenetre_apres est laissée par défaut (5 jours),
    la fenêtre est ajustée au profil agronomique (ex: 7j pour arbres, 4j légumes).
    """
    if seuil_score_irrigation is None:
        seuil_score_irrigation = irr.SEUIL_SCORE_COMPOSITE

    stress_jours = panel[panel["score_stress"] >= seuil_score_stress].copy()
    if stress_jours.empty:
        return pd.DataFrame(columns=["site", "parcel_id", "culture", "date", "score_stress",
                                      "sources_stress", "STATUT_BESOIN", "n_irrigations_fenetre"])

    # Toutes les irrigations au-dessus du seuil sont candidates (pas de filtre a priori).
    # La qualité physique de la preuve est évaluée APRÈS dans EFFET_SUR_LE_STRESS.
    irrig_jours = panel.loc[panel["score_composite"] >= seuil_score_irrigation,
                             ["parcel_id", "date", "score_composite"]]

    # Pré-calcul : quelles irrigations sont constituées uniquement de capteurs thermiques LST ?
    _thermal_set = {"Thermique-LST", "ECOSTRESS-LST", "Landsat-Thermal", "MODIS-LST"}
    def _est_purement_thermique_idx(idx):
        if "sources_evidence" not in panel.columns:
            return False
        srcs = panel.at[idx, "sources_evidence"]
        if not isinstance(srcs, (list, set, tuple)):
            return False
        return len(srcs) > 0 and all(s in _thermal_set for s in srcs)

    lignes = []
    for _, row in stress_jours.iterrows():
        pid, d = row["parcel_id"], row["date"]
        cult = row.get("culture")
        if pd.isna(cult) or not str(cult).strip() or str(cult) == "nan":
            if pid in irr.PARCELLES_TERRAIN:
                cult = "/".join(irr.PARCELLES_TERRAIN[pid]["cultures_terrain"])

        # Adaptation dynamique de la fenêtre après stress selon la culture
        if fenetre_apres == FENETRE_REPONSE_APRES_JOURS:
            _, spec_cult = irr.classifier_culture(cult)
            fenetre_apres_eff = spec_cult["fenetre_besoin_apres_jours"]
        else:
            fenetre_apres_eff = fenetre_apres

        cands = irrig_jours[(irrig_jours.parcel_id == pid) &
                             (irrig_jours.date >= d - pd.Timedelta(days=fenetre_avant)) &
                             (irrig_jours.date <= d + pd.Timedelta(days=fenetre_apres_eff))]

        if not cands.empty:
            plus_proche_idx = (cands["date"] - d).abs().idxmin()
            delai = int((cands.loc[plus_proche_idx, "date"] - d) / pd.Timedelta(days=1))

            # STATUT_BESOIN : rétrocompatible — "irrigation détectée à proximité temporelle"
            statut_besoin = f"BESOIN_COMBLE (irrigation detectee a J{delai:+d})"

            # STATUT_APPORT_EAU : qualité physique de la preuve d'apport
            est_thermique_seul = _est_purement_thermique_idx(plus_proche_idx)
            if est_thermique_seul:
                statut_apport = f"SIGNAL_THERMIQUE_SEUL (LST a J{delai:+d}, canicule possible)"
            else:
                statut_apport = f"APPORT_EAU_DETECTE (irrigation detectee a J{delai:+d})"

            # EFFET_SUR_LE_STRESS : vérification biologique stricte dans les 10 jours post-événement
            post_window = panel[(panel.parcel_id == pid) &
                                (panel.date > d) &
                                (panel.date <= d + pd.Timedelta(days=10))]
            cols_opt_therm = [c for c in ["CWSI_proxy", "NDMI", "NDRE", "NDVI", "SMI", "EVI", "SAVI"] if c in panel.columns]
            post_window_sat = post_window[post_window[cols_opt_therm].notna().any(axis=1)] if cols_opt_therm else post_window

            if not post_window_sat.empty:
                max_post_stress = post_window_sat["score_stress"].max()
                # Vérification complémentaire des indicateurs absolus (CWSI et NDMI)
                cwsi_max = post_window_sat["CWSI_proxy"].max() if "CWSI_proxy" in post_window_sat.columns and post_window_sat["CWSI_proxy"].notna().any() else np.nan

                # Le stress est résorbé si le stress composite baisse ET que le CWSI (si présent) reste sous 0.70
                cwsi_ok = (cwsi_max < 0.70) if not pd.isna(cwsi_max) else True
                if max_post_stress < seuil_score_stress and cwsi_ok and not est_thermique_seul:
                    effet_stress = "STRESS_RESORBE (plante recuperee)"
                else:
                    effet_stress = "STRESS_PERSISTANT (apport insuffisant ou canicule)"
            else:
                effet_stress = "DONNEES_SUIVANTES_INSUFFISANTES"
        else:
            statut_besoin = "BESOIN_NON_COMBLE (aucune irrigation detectee dans la fenetre)"
            statut_apport = "AUCUN_APPORT_DETECTE"
            effet_stress = "STRESS_NON_TRAITE (deficit hydrique)"

        capteurs_indep = row.get("capteurs_independants_stress", [])
        confiance = ("BASSE — MODIS-LST seul (1 km, très dilué sur cette parcelle)"
                     if list(capteurs_indep) == ["MODIS-LST"] else
                     ("HAUTE" if len(capteurs_indep) >= 2 else "MOYENNE"))
        lignes.append({
            "site": row["site"], "parcel_id": pid, "culture": cult,
            "date": d.date(), "score_stress": round(row["score_stress"], 2),
            "sources_stress": ";".join(row["sources_stress"]),
            "n_capteurs_independants": row.get("n_capteurs_independants_stress", row["n_sources_stress"]),
            "confiance": confiance,
            "STATUT_BESOIN": statut_besoin,
            "STATUT_APPORT_EAU": statut_apport,
            "EFFET_SUR_LE_STRESS": effet_stress,
            "n_irrigations_fenetre": len(cands),
        })
    return pd.DataFrame(lignes)

def taux_comblement_attendu_h0(panel, n_iterations=500, seuil_score_stress=SEUIL_SCORE_STRESS,
                                seuil_score_irrigation=None,
                                fenetre_apres=FENETRE_REPONSE_APRES_JOURS,
                                fenetre_avant=FENETRE_REPONSE_AVANT_JOURS,
                                rng_seed=42):
    """Estime, PAR PARCELLE, le taux de comblement qu'on obtiendrait si les
    jours d'irrigation détectés étaient distribués AU HASARD (même densité,
    même nombre total de jours flagués) plutôt qu'aux dates réellement
    détectées. Sert de référence H0 : un taux observé proche de ce chiffre
    ne prouve RIEN sur la qualité du pilotage -- seul un écart net et
    significatif au-dessus du H0 est informatif."""
    if seuil_score_irrigation is None:
        seuil_score_irrigation = irr.SEUIL_SCORE_COMPOSITE

    rng = np.random.default_rng(rng_seed)
    resultats = {}
    for pid, g in panel.groupby("parcel_id"):
        g = g.sort_values("date").reset_index(drop=True)
        n_jours = len(g)
        n_irrig = int((g["score_composite"] >= seuil_score_irrigation).sum())
        stress_idx = g.index[g["score_stress"] >= seuil_score_stress].to_numpy()
        if n_jours == 0 or n_irrig == 0 or len(stress_idx) == 0:
            resultats[pid] = None
            continue
        dates = g["date"].to_numpy()
        taux_h0 = []
        for _ in range(n_iterations):
            faux_irrig_idx = rng.choice(n_jours, size=n_irrig, replace=False)
            faux_irrig_dates = dates[faux_irrig_idx]
            n_combles = 0
            for i in stress_idx:
                d = dates[i]
                borne_bas = d - np.timedelta64(fenetre_avant, "D")
                borne_haut = d + np.timedelta64(fenetre_apres, "D")
                if np.any((faux_irrig_dates >= borne_bas) & (faux_irrig_dates <= borne_haut)):
                    n_combles += 1
            taux_h0.append(n_combles / len(stress_idx))
        resultats[pid] = {
            "taux_h0_moyen": float(np.mean(taux_h0)),
            "taux_h0_p95": float(np.percentile(taux_h0, 95)),
            "n_stress": len(stress_idx),
            "n_irrig_flagues": n_irrig,
            "n_jours_total": n_jours,
        }
    return resultats

def croiser_irrigation_besoin(panel, seuil_score_irrigation=None, seuil_score_stress=SEUIL_SCORE_STRESS,
                               fenetre_avant=FENETRE_PRECEDENT_STRESS_JOURS):
    """Vue symétrique : pour chaque irrigation détectée, un stress avait-il
    été détecté avant (irrigation RÉACTIVE) ou non (PRÉVENTIVE/planifiée,
    ou stress non capté par les capteurs disponibles ce jour-là) ?"""
    if seuil_score_irrigation is None:
        seuil_score_irrigation = irr.SEUIL_SCORE_COMPOSITE

    irrig_jours = panel[panel["score_composite"] >= seuil_score_irrigation].copy()
    if irrig_jours.empty:
        return pd.DataFrame(columns=["site", "parcel_id", "culture", "date",
                                      "score_composite", "STATUT_IRRIGATION"])

    stress_jours = panel.loc[panel["score_stress"] >= seuil_score_stress, ["parcel_id", "date"]]

    lignes = []
    for _, row in irrig_jours.iterrows():
        pid, d = row["parcel_id"], row["date"]
        cands = stress_jours[(stress_jours.parcel_id == pid) &
                              (stress_jours.date >= d - pd.Timedelta(days=fenetre_avant)) &
                              (stress_jours.date <= d)]
        statut = ("IRRIGATION_REACTIVE (stress detecte avant)" if not cands.empty else
                  "IRRIGATION_PREVENTIVE_OU_NON_CORROBOREE (aucun stress detecte avant, "
                  "dans les capteurs disponibles)")
        lignes.append({
            "site": row["site"], "parcel_id": pid, "culture": row.get("culture"),
            "date": d.date(), "score_composite": round(row["score_composite"], 2),
            "STATUT_IRRIGATION": statut,
        })
    return pd.DataFrame(lignes)


# ===========================================================================
# MAIN
# ===========================================================================

def _construire_panel_avec_irrigation(data_dir, cache_dir, csv_manuel, use_api):
    """Reproduit les étapes de detect_irrigation_vs_pluie_v3.main() jusqu'au
    score_composite d'irrigation inclus, en réutilisant ses fonctions et la
    constante partagée irr.MODULES_OPTIQUES -- ce qui n'était vrai qu'en
    apparence avant le 2026-08-14 (NDRE/SAVI/MSAVI/BSI/vwc manquaient ici,
    cf. commentaires CORRIGÉ plus bas)."""
    fichiers = irr.decouvrir_fichiers(data_dir)
    sources_brutes = {source: irr.charger_source(paths) for source, paths in fichiers.items()}

    df_meteo = sources_brutes.get("ERA5-Meteo")
    tous_sites = sorted(set().union(*[set(df.site.unique()) for df in sources_brutes.values() if not df.empty]))
    precip = irr.obtenir_precipitation(df_meteo, tous_sites, cache_dir, csv_manuel=csv_manuel, use_api=use_api)

    panel = irr.construire_panel(sources_brutes)

    for label, spec in irr.SOURCES_THERMIQUES.items():
        panel, _ = irr.evidence_thermique(panel, label, spec["colonne"], spec["poids"],
                                           colonne_est_kelvin=spec.get("colonne_est_kelvin", False),
                                           seuil_chute=spec.get("seuil_chute", irr.SEUIL_CHUTE_DTS_C),
                                           resolution_m=irr.SOURCE_SPECS[label]["resolution_m"])
    # CORRIGÉ (2026-08-14) : cette boucle ne couvrait que NDMI/NDWI (copie locale
    # figée), alors que main() traite 6 modules optiques (irr.MODULES_OPTIQUES,
    # incluant NDRE/SAVI/MSAVI/BSI). Le score_composite utilisé ici pour évaluer
    # le comblement des besoins était donc systématiquement sous-estimé par
    # rapport au panel "officiel" d'irrigation -- jusqu'à 11.5% du score total
    # sur ce jeu de données. On boucle maintenant sur la même constante partagée.
    for colonne, seuil, poids, sens_hausse, _desc in irr.MODULES_OPTIQUES:
        panel, _ = irr.evidence_optique(panel, colonne, poids, seuil, sens_hausse=sens_hausse)
    panel, _ = irr.evidence_humidite_sol(panel)
    # CORRIGÉ (2026-08-14) : appel manquant -- irr.evidence_vwc_nisar() est
    # exécutée dans main() mais n'était jamais appelée ici, donc vwc_evidence
    # n'existait tout simplement pas dans ce panel.
    panel, _ = irr.evidence_vwc_nisar(panel)
    for colonne_ndvi in ("NDVI_Landsat", "NDVI"):
        if colonne_ndvi in panel.columns:
            panel, _ = irr.evidence_ndvi_differee(panel, colonne_ndvi)

    for source, spec in irr.SOURCES_PIXEL_PIC.items():
        if source not in sources_brutes:
            continue
        lignes = []
        for parcel_id, sub in sources_brutes[source].groupby("parcel_id"):
            wide, ref, n_pixels = irr.construire_serie_pixels(sub, spec["colonne"])
            if wide.empty:
                continue
            res = irr.detecter_pics_pixel(wide, seuil_db=spec["seuil_db"])
            for date_evt, row in res.iterrows():
                lignes.append({"parcel_id": parcel_id, "date": date_evt,
                                f"{spec['colonne']}_pct_pixels_pic": row["pct_pixels_pic"]})
        if lignes:
            df_pix = pd.DataFrame(lignes)
            panel = panel.merge(df_pix, on=["parcel_id", "date"], how="left")
            flag = panel[f"{spec['colonne']}_pct_pixels_pic"] >= irr.SEUIL_PCT_PIXELS
            panel[f"{spec['colonne']}_evidence"] = np.where(flag, spec["poids_defaut"], 0.0)

    panel = irr.calculer_score_composite(panel)
    return panel, sources_brutes, precip


def main():
    global SEUIL_SCORE_STRESS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=str(irr.DEFAULT_DATA_DIR),
                     help=f"Dossier contenant les .parquet (recherche récursive). Défaut : {irr.DEFAULT_DATA_DIR}")
    ap.add_argument("--precip", default=None, help="CSV date,site,precip_mm déjà préparé")
    ap.add_argument("--no-api", action="store_true", help="Ne pas appeler Open-Meteo en secours")
    ap.add_argument("--dry-run", action="store_true", help="Résumé des modules actifs + validation événement connu, sans CSV")
    ap.add_argument("--seuil-stress", type=float, default=SEUIL_SCORE_STRESS,
                     help=f"Score de stress composite minimal pour flaguer un jour de besoin (défaut {SEUIL_SCORE_STRESS})")
    ap.add_argument("--seuil-irrigation", type=float, default=irr.SEUIL_SCORE_COMPOSITE,
                     help=f"Score composite minimal pour qu'une irrigation soit considérée détectée (défaut {irr.SEUIL_SCORE_COMPOSITE})")
    ap.add_argument("--fenetre-apres", type=int, default=FENETRE_REPONSE_APRES_JOURS,
                     help=f"Jours après un stress où chercher une irrigation qui le comble (défaut {FENETRE_REPONSE_APRES_JOURS})")
    ap.add_argument("--fenetre-avant", type=int, default=FENETRE_REPONSE_AVANT_JOURS,
                     help=f"Jours avant un stress où une irrigation compte encore comme réponse (défaut {FENETRE_REPONSE_AVANT_JOURS})")
    ap.add_argument("--fenetre-precedent-stress", type=int, default=FENETRE_PRECEDENT_STRESS_JOURS,
                     help=f"Jours à regarder AVANT une irrigation détectée pour vérifier si un stress "
                          f"l'a précédée (vue symétrique, défaut {FENETRE_PRECEDENT_STRESS_JOURS} -- "
                          f"volontairement plus large que --fenetre-avant, qui sert à l'autre sens)")
    ap.add_argument("--output-prefix", default="rapport_besoin_irrigation")
    ap.add_argument("--cache-panel", default=None,
                     help="Sauvegarde le panel complet (evidences irrigation + stress, score_composite "
                          "et score_stress déjà calculés) dans ce .pkl -- réutilisable avec --from-cache "
                          "pour tester plusieurs seuils sans tout recalculer.")
    ap.add_argument("--from-cache", default=None,
                     help="Charge le panel depuis un .pkl généré par --cache-panel (ignore --data-dir/"
                          "--precip/--no-api).")
    args = ap.parse_args()
    SEUIL_SCORE_STRESS = args.seuil_stress

    data_dir = Path(args.data_dir)
    cache_dir = data_dir / irr.CACHE_DIR_NAME

    print("=" * 80)
    print(" BESOIN D'EAU (stress hydrique) <-> IRRIGATION DÉTECTÉE — v4")
    print("=" * 80)

    if args.from_cache:
        print(f"\n[CACHE] Chargement du panel pré-calculé depuis {args.from_cache} "
              f"-- aucune relecture des .parquet, aucun recalcul de preuve.")
        panel, precip = pd.read_pickle(args.from_cache)
        sources_brutes = {}
        panel = irr.calculer_score_composite(panel)
        panel = calculer_score_stress(panel)
        print(f"  {len(panel)} lignes chargées, {panel.parcel_id.nunique()} parcelles.")
    else:
        panel, sources_brutes, precip = _construire_panel_avec_irrigation(
            data_dir, cache_dir, args.precip, use_api=not args.no_api)

        print("\n[BESOIN D'EAU] Calcul des modules de stress hydrique disponibles...")
        panel, actif = evidence_stress_cwsi(panel)
        print(f"  [{'✓' if actif else ' '}] CWSI_proxy (MODIS-LST)" + ("" if actif else " -- absent, désactivé"))
        panel, actif = evidence_stress_smi(panel)
        print(f"  [{'✓' if actif else ' '}] SMI (MODIS-LST)" + ("" if actif else " -- absent, désactivé"))
        panel, actif = evidence_stress_soil_moisture(panel)
        print(f"  [{'✓' if actif else ' '}] soil_moisture_vol (NISAR SME2)" + ("" if actif else " -- absent, désactivé"))
        MODULES_STRESS_OPTIQUE = [
            ("NDMI", SEUIL_BAISSE_NDMI_STRESS, 1.0, True, "Baisse NDMI (assèchement foliaire)"),
            ("NDWI", SEUIL_BAISSE_NDWI_STRESS, 0.75, True, "Baisse NDWI (assèchement surface)"),
            ("NDRE", -0.03, 1.0, True, "Baisse NDRE (stress chlorophyllien précoce)"),
            ("BSI", 0.04, 1.0, False, "Hausse BSI (assèchement sol nu)"),
        ]
        for colonne, seuil, poids, sens_baisse, desc in MODULES_STRESS_OPTIQUE:
            panel, actif = evidence_stress_optique(panel, colonne, seuil, poids, sens_baisse=sens_baisse)
            sens_str = "Baisse" if sens_baisse else "Hausse"
            print(f"  [{'✓' if actif else ' '}] {sens_str} {colonne} (S2-Indices -- {desc})" + ("" if actif else " -- absent, désactivé"))

        panel = calculer_score_stress(panel)

        if args.cache_panel:
            pd.to_pickle((panel, precip), args.cache_panel)
            print(f"\n[CACHE] Panel complet sauvegardé -> {args.cache_panel} -- réutilisable avec "
                  f"--from-cache pour tester d'autres seuils instantanément.")
    if panel["score_stress"].sum() == 0:
        print("\n  [!!] AUCUN module de stress disponible ou actif (CWSI_proxy, SMI, soil_moisture_vol, "
              "NDMI/NDWI tous absents ou entièrement vides) -- impossible de déterminer les jours de "
              "besoin en eau. Fournissez au moins MODIS-LST (clean) pour activer ce module.")
        return

    # --- Validation sur l'événement connu, comme le script d'irrigation ---
    print("\n" + "=" * 80)
    print(" STRESS AUTOUR DE(S) L'ÉVÉNEMENT(S) CONNU(S)")
    print("=" * 80)
    for evt in irr.EVENEMENTS_CONNUS:
        debut = pd.Timestamp(evt["date_debut"]) - pd.Timedelta(days=21)
        fin = pd.Timestamp(evt["date_fin"]) + pd.Timedelta(days=10)
        for parcel_id, label in evt["parcelles"].items():
            sous = panel[(panel.parcel_id == parcel_id) & (panel.date >= debut) & (panel.date <= fin)]
            sous_stress = sous[sous["score_stress"] > 0].sort_values("date")
            print(f"\n  {label} [{parcel_id}] :")
            if sous_stress.empty:
                print("    Aucun stress détecté dans les 3 semaines avant / 10 jours après "
                      "(sur les modules de stress disponibles ce run).")
            else:
                for _, row in sous_stress.iterrows():
                    print(f"    {row['date'].date()} : score_stress={row['score_stress']:.2f} "
                          f"(sources: {row['sources_stress']})")

    if args.dry_run:
        return

    df_besoin = croiser_besoin_irrigation(panel, args.seuil_stress, args.seuil_irrigation,
                                           args.fenetre_apres, args.fenetre_avant)
    df_irrig = croiser_irrigation_besoin(panel, args.seuil_irrigation, args.seuil_stress, args.fenetre_precedent_stress)

    out_besoin = f"{args.output_prefix}_besoin_vs_irrigation.csv"
    out_irrig = f"{args.output_prefix}_irrigation_vs_besoin.csv"
    df_besoin.to_csv(out_besoin, index=False)
    df_irrig.to_csv(out_irrig, index=False)

    print("\n" + "=" * 80)
    print(" RÉSULTATS")
    print("=" * 80)

    print(f"\n{len(df_besoin)} jour(s)*parcelle(s) de BESOIN D'EAU détecté(s) "
          f"(score_stress >= {args.seuil_stress}) -> {out_besoin}")
    if not df_besoin.empty:
        combles = df_besoin["STATUT_BESOIN"].str.startswith("BESOIN_COMBLE").sum()
        print(f"  -> {combles} comblé(s) par une irrigation détectée, {len(df_besoin) - combles} NON comblé(s)")
        print("\n  Par parcelle (comblés / total) :")
        recap = df_besoin.groupby("parcel_id")["STATUT_BESOIN"].apply(
            lambda s: f"{s.str.startswith('BESOIN_COMBLE').sum()}/{len(s)}")
        print(recap.to_string())

        # --- H0 : le taux de comblement observé bat-il le hasard ? ---
        # DOIT utiliser les MÊMES seuils/fenêtres que ceux qui ont servi à
        # construire df_besoin (args.*) -- pas les valeurs par défaut du
        # module, sans quoi la comparaison observé/H0 ne porterait pas sur
        # le même ensemble de jours et serait trompeuse.
        h0 = taux_comblement_attendu_h0(
            panel,
            seuil_score_stress=args.seuil_stress,
            seuil_score_irrigation=args.seuil_irrigation,
            fenetre_apres=args.fenetre_apres,
            fenetre_avant=args.fenetre_avant,
        )
        print("\n  Comparaison au hasard (H0 -- irrigation redistribuée aléatoirement, même densité) :")
        for pid, stats in h0.items():
            if stats is None:
                continue
            sous_pid = df_besoin.loc[df_besoin.parcel_id == pid, "STATUT_BESOIN"]
            if sous_pid.empty:
                continue
            taux_reel = sous_pid.str.startswith("BESOIN_COMBLE").mean()
            ecart = taux_reel - stats["taux_h0_moyen"]
            alerte = "  [PEU INFORMATIF]" if ecart < 0.10 else ""
            print(f"    {pid} : observé={taux_reel:.0%}  H0={stats['taux_h0_moyen']:.0%} "
                  f"(p95={stats['taux_h0_p95']:.0%})  écart=+{ecart:.0%}{alerte}")

    print(f"\n{len(df_irrig)} jour(s)*parcelle(s) d'IRRIGATION détectée(s) "
          f"(score_composite >= {args.seuil_irrigation}) -> {out_irrig}")
    if not df_irrig.empty:
        reactive = df_irrig["STATUT_IRRIGATION"].str.startswith("IRRIGATION_REACTIVE").sum()
        print(f"  -> {reactive} réactive(s) (stress détecté avant), "
              f"{len(df_irrig) - reactive} préventive(s)/non corroborée(s)")

    if not df_besoin.empty:
        n_non_combles = int((~df_besoin['STATUT_BESOIN'].str.startswith('BESOIN_COMBLE')).sum())
        if n_non_combles:
            print(f"\n  [!] {n_non_combles} jour(s) de besoin en eau NON comblés par une irrigation détectée -- "
                  f"à vérifier : soit un vrai déficit hydrique, soit une irrigation réelle que les capteurs "
                  f"disponibles n'ont pas su capter (cf. limites documentées dans le rapport SAR : goutte-à-"
                  f"goutte sur sol nu).")


if __name__ == "__main__":
    main()