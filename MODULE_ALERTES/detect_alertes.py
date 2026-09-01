#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_alertes.py
===================================================================
Moteur autonome de détection des 15 alertes agronomiques multi-sources.

Réutilisation obligatoire (implementation_plan_v2.md §3) :
- Importe decouvrir_fichiers, charger_source, construire_panel, facteur_echelle, PARCELLES_TERRAIN
  depuis detect_irrigation_vs_pluie_v3.py (IRRIGATION)
- Importe appliquer_masque_nuages_et_qa, determiner_confiance_fcover depuis compute_health_scores.py (SANTE_PLANTES)
- Importe baselines_communes.py (MODULE_ALERTES)
"""

import sys
import os
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

import baselines_communes as bc
import config_alertes as cfg_alt

# Importations réutilisées depuis IRRIGATION
try:
    import detect_irrigation_vs_pluie_v3 as irr
    facteur_echelle = irr.facteur_echelle
    PARCELLES_TERRAIN = irr.PARCELLES_TERRAIN
    decouvrir_fichiers = irr.decouvrir_fichiers
    charger_source = irr.charger_source
    construire_panel = irr.construire_panel
except ImportError:
    # Mode dégradé de secours si non disponible
    def facteur_echelle(parcel_id, resolution_m=1000):
        return 0.15
    PARCELLES_TERRAIN = {}
    def decouvrir_fichiers(data_dir):
        return {}
    def charger_source(filepath, spec):
        return pd.DataFrame()
    def construire_panel(dict_sources):
        return pd.DataFrame()

# Importations réutilisées depuis SANTE_PLANTES
try:
    import compute_health_scores as chs
    appliquer_masque_nuages_et_qa = chs.appliquer_masque_nuages_et_qa
except ImportError:
    def appliquer_masque_nuages_et_qa(df):
        return df


def detecter_toutes_les_alertes(
    df_panel: pd.DataFrame,
    df_pixels_s2: pd.DataFrame = None,
    geojson_paths: list = None,
    registre_taches: pd.DataFrame = None
) -> dict:
    """
    Exécute les règles de détection pour les 15 alertes agronomiques.

    Returns:
        dict contenant:
        - "risques_naturels": DataFrame pour CSV 1
        - "comparaison": DataFrame pour CSV 2
        - "coherence": DataFrame pour CSV 3
    """
    if df_panel.empty:
        empty_df = pd.DataFrame(columns=[
            "site", "parcel_id", "date", "culture", "type_alerte", "nom_alerte",
            "categorie", "gravite", "score_confiance", "niveau_confiance",
            "familles_impliquees", "statut", "details"
        ])
        return {
            "risques_naturels": empty_df.copy(),
            "comparaison": empty_df.copy(),
            "coherence": empty_df.copy(),
            "alertes_pixel_10m": pd.DataFrame()
        }

    df = df_panel.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["parcel_id", "date"]).reset_index(drop=True)

    # 1. Calcul des baselines Z-scores et percentiles causaux sur 30j
    cols_zscore = ["NDWI", "NDMI", "NDRE", "CI_RedEdge", "NDVI", "SAVI"]
    for col in cols_zscore:
        if col in df.columns:
            df[f"Z_{col}"] = bc.calculer_baseline_glissante_causale(df, col, window_days=30, min_obs=5)
        else:
            df[f"Z_{col}"] = np.nan

    if "soil_moisture_vol" in df.columns:
        df["pct_soil_moisture"] = bc.calculer_percentile_expanding_causal(df, "soil_moisture_vol", min_obs=5)
    else:
        df["pct_soil_moisture"] = np.nan

    # Masquage sol nu fCover < 0.05
    has_fcover = "fCover" in df.columns
    if has_fcover:
        sol_nu_mask = df["fCover"] < cfg_alt.SEUIL_FCOVER_FAIBLE
    else:
        sol_nu_mask = pd.Series(False, index=df.index)

    alertes_cat_a = []
    alertes_cat_b = []
    alertes_cat_c = []

    # Iterate row by row pour évaluer les déclencheurs
    for idx, row in df.iterrows():
        site = row.get("site", "inconnu")
        pid = row.get("parcel_id", "inconnu")
        dt = row.get("date")
        culture = row.get("culture", "DEFAULT")
        fcover_val = row.get("fCover", np.nan)

        # Absence de pluie calculée par observation individuelle (Bug 0.7 résolu)
        precip_val = row.get("precip_mm")
        precip_absente = (precip_val is None) or pd.isna(precip_val)

        # -------------------------------------------------------------------
        # ALERTE 1 : Stress hydrique
        # -------------------------------------------------------------------
        if not sol_nu_mask.iloc[idx]:
            z_ndwi = row.get("Z_NDWI", np.nan)
            z_ndmi = row.get("Z_NDMI", np.nan)
            cwsi = row.get("CWSI_proxy", np.nan)
            sm_pct = row.get("pct_soil_moisture", np.nan)

            eau_optique_baisse = (not np.isnan(z_ndwi) and z_ndwi <= -1.5) or (not np.isnan(z_ndmi) and z_ndmi <= -1.5)
            eau_sol_baisse = (not np.isnan(cwsi) and cwsi >= 0.40) or (not np.isnan(sm_pct) and sm_pct <= 20.0)

            if eau_optique_baisse and eau_sol_baisse:
                cols_used = ["NDWI", "NDMI"]
                if not np.isnan(cwsi):
                    cols_used.append("CWSI_proxy")
                if not np.isnan(sm_pct):
                    cols_used.append("soil_moisture_vol")

                n_fam = cfg_alt.compter_familles_independantes(cols_used)
                fe = facteur_echelle(pid, resolution_m=1000 if "CWSI_proxy" in cols_used else 200)
                conf = cfg_alt.calculer_score_confiance_alerte(n_fam, facteur_echelle=fe)

                grav = "CRITIQUE" if ("jeune" in str(culture).lower() or culture in ["Amandier", "Olivier"]) else "AVERTISSEMENT"
                alertes_cat_a.append({
                    "site": site, "parcel_id": pid, "date": dt, "culture": culture,
                    "type_alerte": "ALERTE_1_STRESS_HYDRIQUE",
                    "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_1_STRESS_HYDRIQUE"]["nom"],
                    "categorie": "A_RISQUES_NATURELS", "gravite": grav,
                    "score_confiance": conf["score_confiance"],
                    "niveau_confiance": conf["niveau_confiance"],
                    "familles_impliquees": n_fam, "statut": "DECLENCHEE",
                    "details": f"Baisse NDWI/NDMI (Z_NDWI={z_ndwi:.2f}, Z_NDMI={z_ndmi:.2f}) et CWSI/SM (CWSI={cwsi:.2f})"
                })

        # -------------------------------------------------------------------
        # ALERTE 2 : Stress azoté fort
        # -------------------------------------------------------------------
        if not sol_nu_mask.iloc[idx]:
            z_ndre = row.get("Z_NDRE", np.nan)
            z_ci = row.get("Z_CI_RedEdge", np.nan)
            z_ndwi = row.get("Z_NDWI", np.nan)
            z_ndmi = row.get("Z_NDMI", np.nan)

            chloro_baisse = (not np.isnan(z_ndre) and z_ndre <= -1.5) or (not np.isnan(z_ci) and z_ci <= -1.5)
            eau_stable = (np.isnan(z_ndwi) or z_ndwi >= -0.5) and (np.isnan(z_ndmi) or z_ndmi >= -0.5)

            if chloro_baisse and eau_stable:
                cols_used = ["NDRE", "CI_RedEdge", "NDWI", "NDMI"]
                n_fam = cfg_alt.compter_familles_independantes(cols_used)
                conf = cfg_alt.calculer_score_confiance_alerte(n_fam, facteur_echelle=1.0)

                alertes_cat_a.append({
                    "site": site, "parcel_id": pid, "date": dt, "culture": culture,
                    "type_alerte": "ALERTE_2_STRESS_AZOTE_FORT",
                    "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_2_STRESS_AZOTE_FORT"]["nom"],
                    "categorie": "A_RISQUES_NATURELS", "gravite": "AVERTISSEMENT",
                    "score_confiance": conf["score_confiance"],
                    "niveau_confiance": conf["niveau_confiance"],
                    "familles_impliquees": n_fam, "statut": "DECLENCHEE",
                    "details": f"Chute NDRE/CI_RedEdge sans chute d'eau (Z_NDRE={z_ndre:.2f})"
                })

        # -------------------------------------------------------------------
        # ALERTE 3 : Stress combiné eau + azote
        # -------------------------------------------------------------------
        if not sol_nu_mask.iloc[idx]:
            z_ndre = row.get("Z_NDRE", np.nan)
            z_ndwi = row.get("Z_NDWI", np.nan)
            z_ndmi = row.get("Z_NDMI", np.nan)
            cwsi = row.get("CWSI_proxy", np.nan)

            chloro_baisse = not np.isnan(z_ndre) and z_ndre <= -1.5
            eau_baisse = (not np.isnan(z_ndwi) and z_ndwi <= -1.5) or (not np.isnan(z_ndmi) and z_ndmi <= -1.5) or (not np.isnan(cwsi) and cwsi >= 0.40)

            if chloro_baisse and eau_baisse:
                cols_used = ["NDRE", "NDWI"]
                if not np.isnan(cwsi):
                    cols_used.append("CWSI_proxy")
                n_fam = cfg_alt.compter_familles_independantes(cols_used)
                fe = facteur_echelle(pid, resolution_m=1000 if "CWSI_proxy" in cols_used else 10)
                conf = cfg_alt.calculer_score_confiance_alerte(n_fam, facteur_echelle=fe)

                alertes_cat_a.append({
                    "site": site, "parcel_id": pid, "date": dt, "culture": culture,
                    "type_alerte": "ALERTE_3_STRESS_COMBINE_EAU_AZOTE",
                    "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_3_STRESS_COMBINE_EAU_AZOTE"]["nom"],
                    "categorie": "A_RISQUES_NATURELS", "gravite": "CRITIQUE",
                    "score_confiance": conf["score_confiance"],
                    "niveau_confiance": conf["niveau_confiance"],
                    "familles_impliquees": n_fam, "statut": "DECLENCHEE",
                    "details": f"Stress simultané NDRE (Z={z_ndre:.2f}) et eau (Z_NDWI={z_ndwi:.2f}, Z_NDMI={z_ndmi:.2f})"
                })

        # -------------------------------------------------------------------
        # ALERTE 4 : Stress thermique / canicule
        # -------------------------------------------------------------------
        tmax = row.get("Tmax_C", np.nan)
        lst_eco = row.get("LST_ECOSTRESS_C", np.nan)
        if not np.isnan(tmax) and tmax >= 35.0:
            cols_used = ["Tmax_C"]
            if not np.isnan(lst_eco) and lst_eco >= 40.0:
                cols_used.append("LST_ECOSTRESS_C")
            n_fam = cfg_alt.compter_familles_independantes(cols_used)
            conf = cfg_alt.calculer_score_confiance_alerte(n_fam, facteur_echelle=1.0)
            grav = "CRITIQUE" if tmax >= 38.0 else "AVERTISSEMENT"

            alertes_cat_a.append({
                "site": site, "parcel_id": pid, "date": dt, "culture": culture,
                "type_alerte": "ALERTE_4_STRESS_THERMIQUE_CANICULE",
                "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_4_STRESS_THERMIQUE_CANICULE"]["nom"],
                "categorie": "A_RISQUES_NATURELS", "gravite": grav,
                "score_confiance": conf["score_confiance"],
                "niveau_confiance": conf["niveau_confiance"],
                "familles_impliquees": n_fam, "statut": "DECLENCHEE",
                "details": f"Tmax_C = {tmax:.1f}°C (ECOSTRESS={lst_eco:.1f}°C)"
            })

        # -------------------------------------------------------------------
        # ALERTE 5 : Excès d'humidité / engorgement
        # -------------------------------------------------------------------
        if precip_absente:
            alertes_cat_a.append({
                "site": site, "parcel_id": pid, "date": dt, "culture": culture,
                "type_alerte": "ALERTE_5_EXCES_HUMIDITE_ENGORGEMENT",
                "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_5_EXCES_HUMIDITE_ENGORGEMENT"]["nom"],
                "categorie": "A_RISQUES_NATURELS", "gravite": "AVERTISSEMENT",
                "score_confiance": 0.0, "niveau_confiance": "BASSE",
                "familles_impliquees": 0, "statut": "INDETERMINE_DONNEE_MANQUANTE",
                "details": "Donnée precip_mm manquante dans ERA5"
            })
        else:
            z_ndwi = row.get("Z_NDWI", np.nan)
            precip_7j = row.get("precip_mm", 0.0) # Ou cumul 7j si calculé
            if not np.isnan(z_ndwi) and z_ndwi >= 1.5 and precip_7j >= 40.0:
                cols_used = ["NDWI", "precip_mm"]
                n_fam = cfg_alt.compter_familles_independantes(cols_used)
                conf = cfg_alt.calculer_score_confiance_alerte(n_fam, facteur_echelle=1.0)

                alertes_cat_a.append({
                    "site": site, "parcel_id": pid, "date": dt, "culture": culture,
                    "type_alerte": "ALERTE_5_EXCES_HUMIDITE_ENGORGEMENT",
                    "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_5_EXCES_HUMIDITE_ENGORGEMENT"]["nom"],
                    "categorie": "A_RISQUES_NATURELS", "gravite": "AVERTISSEMENT",
                    "score_confiance": conf["score_confiance"],
                    "niveau_confiance": conf["niveau_confiance"],
                    "familles_impliquees": n_fam, "statut": "DECLENCHEE",
                    "details": f"NDWI très élevé (Z={z_ndwi:.2f}) avec pluie 7j={precip_7j:.1f}mm"
                })

        # -------------------------------------------------------------------
        # ALERTE 6 : Sécheresse prolongée
        # -------------------------------------------------------------------
        if precip_absente:
            alertes_cat_a.append({
                "site": site, "parcel_id": pid, "date": dt, "culture": culture,
                "type_alerte": "ALERTE_6_SECHERESSE_PROLONGEE",
                "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_6_SECHERESSE_PROLONGEE"]["nom"],
                "categorie": "A_RISQUES_NATURELS", "gravite": "AVERTISSEMENT",
                "score_confiance": 0.0, "niveau_confiance": "BASSE",
                "familles_impliquees": 0, "statut": "INDETERMINE_DONNEE_MANQUANTE",
                "details": "Donnée precip_mm manquante dans ERA5"
            })
        else:
            z_ndmi = row.get("Z_NDMI", np.nan)
            z_ndvi = row.get("Z_NDVI", np.nan)
            sm_pct = row.get("pct_soil_moisture", np.nan)
            precip_cur = float(precip_val)

            secheresse_optique = (not np.isnan(z_ndmi) and z_ndmi <= -1.2) or (not np.isnan(z_ndvi) and z_ndvi <= -1.2)
            secheresse_sol = (not np.isnan(sm_pct) and sm_pct <= 25.0)
            deficit_pluie = (precip_cur <= 2.0)

            if deficit_pluie and (secheresse_optique or secheresse_sol):
                cols_used = ["precip_mm"]
                if not np.isnan(z_ndmi):
                    cols_used.append("NDMI")
                if not np.isnan(z_ndvi):
                    cols_used.append("NDVI")
                if not np.isnan(sm_pct):
                    cols_used.append("soil_moisture_vol")
                n_fam = cfg_alt.compter_familles_independantes(cols_used)
                conf = cfg_alt.calculer_score_confiance_alerte(n_fam, facteur_echelle=1.0)
                grav = "CRITIQUE" if (secheresse_optique and secheresse_sol) else "AVERTISSEMENT"

                alertes_cat_a.append({
                    "site": site, "parcel_id": pid, "date": dt, "culture": culture,
                    "type_alerte": "ALERTE_6_SECHERESSE_PROLONGEE",
                    "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_6_SECHERESSE_PROLONGEE"]["nom"],
                    "categorie": "A_RISQUES_NATURELS", "gravite": grav,
                    "score_confiance": conf["score_confiance"],
                    "niveau_confiance": conf["niveau_confiance"],
                    "familles_impliquees": n_fam, "statut": "DECLENCHEE",
                    "details": f"Déficit hydrique prolongé (Pluie={precip_cur:.1f}mm, Z_NDMI={z_ndmi:.2f}, SM_pct={sm_pct:.1f}%)"
                })

        # -------------------------------------------------------------------
        # ALERTE 8 : Écart apport eau réel vs besoin
        # -------------------------------------------------------------------
        if precip_absente:
            alertes_cat_b.append({
                "site": site, "parcel_id": pid, "date": dt, "culture": culture,
                "type_alerte": "ALERTE_8_ECART_EAU_REEL_VS_BESOIN",
                "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_8_ECART_EAU_REEL_VS_BESOIN"]["nom"],
                "categorie": "B_COMPARAISON", "gravite": "AVERTISSEMENT",
                "score_confiance": 0.0, "niveau_confiance": "BASSE",
                "familles_impliquees": 0, "statut": "INDETERMINE_DONNEE_MANQUANTE",
                "details": "Donnée precip_mm manquante pour le calcul de Peff"
            })
        else:
            cwsi = row.get("CWSI_proxy", np.nan)
            z_ndmi = row.get("Z_NDMI", np.nan)
            precip_cur = float(precip_val)
            statut_besoin = str(row.get("STATUT_BESOIN", ""))
            
            # Déclenchement si besoin non comblé explicite ou stress hydrique persistant sans pluie
            besoin_non_comble = "BESOIN_NON_COMBLE" in statut_besoin or (
                ((not np.isnan(cwsi) and cwsi >= 0.70) or (not np.isnan(z_ndmi) and z_ndmi <= -1.5))
                and precip_cur < 2.0
            )
            
            if besoin_non_comble and not sol_nu_mask.iloc[idx]:
                cols_used = ["precip_mm"]
                if not np.isnan(cwsi):
                    cols_used.append("CWSI_proxy")
                if not np.isnan(z_ndmi):
                    cols_used.append("NDMI")
                n_fam = cfg_alt.compter_familles_independantes(cols_used)
                fe = facteur_echelle(pid, resolution_m=1000 if "CWSI_proxy" in cols_used else 10)
                conf = cfg_alt.calculer_score_confiance_alerte(n_fam, facteur_echelle=fe)
                
                alertes_cat_b.append({
                    "site": site, "parcel_id": pid, "date": dt, "culture": culture,
                    "type_alerte": "ALERTE_8_ECART_EAU_REEL_VS_BESOIN",
                    "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_8_ECART_EAU_REEL_VS_BESOIN"]["nom"],
                    "categorie": "B_COMPARAISON", "gravite": "CRITIQUE" if (cwsi >= 0.85 or (not np.isnan(z_ndmi) and z_ndmi <= -2.0)) else "AVERTISSEMENT",
                    "score_confiance": conf["score_confiance"],
                    "niveau_confiance": conf["niveau_confiance"],
                    "familles_impliquees": n_fam, "statut": "DECLENCHEE",
                    "details": f"Besoin hydrique non comblé (Pluie={precip_cur:.1f}mm, CWSI={cwsi:.2f}, Z_NDMI={z_ndmi:.2f})"
                })

        # -------------------------------------------------------------------
        # ALERTE 9 : Écart stade phénologique observé vs attendu
        # -------------------------------------------------------------------
        score_pheno = row.get("score_suivi_phenologique", np.nan)
        if not np.isnan(score_pheno) and score_pheno < 50.0:
            cols_used = ["NDVI", "NDRE"]
            n_fam = cfg_alt.compter_familles_independantes(cols_used)
            conf = cfg_alt.calculer_score_confiance_alerte(n_fam, facteur_echelle=1.0)
            stade_attendu = row.get("stade_phenologique_attendu", "Attendu non conforme")

            alertes_cat_b.append({
                "site": site, "parcel_id": pid, "date": dt, "culture": culture,
                "type_alerte": "ALERTE_9_ECART_STADE_PHENOLOGIQUE",
                "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_9_ECART_STADE_PHENOLOGIQUE"]["nom"],
                "categorie": "B_COMPARAISON", "gravite": "INFORMATION",
                "score_confiance": conf["score_confiance"],
                "niveau_confiance": conf["niveau_confiance"],
                "familles_impliquees": n_fam, "statut": "DECLENCHEE",
                "details": f"Score phénologique faible ({score_pheno:.1f}/100) vs stade '{stade_attendu}'"
            })

        # -------------------------------------------------------------------
        # ALERTE 10 : Écart occupation réelle vs déclarée (Qualifié)
        # -------------------------------------------------------------------
        ndvi = row.get("NDVI", np.nan)
        bsi = row.get("BSI", np.nan)
        z_ndvi = row.get("Z_NDVI", np.nan)
        if not np.isnan(ndvi) and not np.isnan(bsi):
            mois = dt.month
            stades_culture = cfg_alt.STADES_PHENOLOGIQUES_PAR_CULTURE.get(culture, cfg_alt.STADES_PHENOLOGIQUES_PAR_CULTURE.get("DEFAULT", []))
            ndvi_min_attendu = 0.15
            for st in stades_culture:
                if mois in st.get("mois", []):
                    ndvi_min_attendu = st.get("ndvi_min", 0.15)
                    break

            if ndvi < ndvi_min_attendu and bsi >= 0.20:
                cols_used = ["NDVI", "BSI"]
                n_fam = cfg_alt.compter_familles_independantes(cols_used)
                conf = cfg_alt.calculer_score_confiance_alerte(n_fam, facteur_echelle=1.0)

                # Qualification de la cause réelle et ajustement de la gravité
                if not np.isnan(z_ndvi) and z_ndvi <= -1.5:
                    grav = "CRITIQUE"
                    cause_desc = f"Défoliation/Chute brutale de biomasse (NDVI={ndvi:.2f} < min {ndvi_min_attendu:.2f}, Z_NDVI={z_ndvi:.2f})"
                elif fcover_val < 0.05:
                    grav = "AVERTISSEMENT"
                    cause_desc = f"Sol nu persistant sans activité (NDVI={ndvi:.2f}, BSI={bsi:.2f}) - Parcelle jachère ou non implantée"
                else:
                    grav = "INFORMATION"
                    cause_desc = f"Couvert clairsemé / Densité faible (NDVI={ndvi:.2f} < min {ndvi_min_attendu:.2f}) - Végétation espacée (jeunes plants/inter-rangs)"

                alertes_cat_b.append({
                    "site": site, "parcel_id": pid, "date": dt, "culture": culture,
                    "type_alerte": "ALERTE_10_ECART_OCCUPATION_REELLE_VS_DECLAREES",
                    "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_10_ECART_OCCUPATION_REELLE_VS_DECLAREES"]["nom"],
                    "categorie": "B_COMPARAISON", "gravite": grav,
                    "score_confiance": conf["score_confiance"],
                    "niveau_confiance": conf["niveau_confiance"],
                    "familles_impliquees": n_fam, "statut": "DECLENCHEE",
                    "details": cause_desc
                })

    # -------------------------------------------------------------------
    # ÉVALUATION TOUTES ALERTES À L'ÉCHELLE PIXEL 10M (Tous pixels 10m)
    # -------------------------------------------------------------------
    alertes_pixel_10m = []
    if df_pixels_s2 is not None and not df_pixels_s2.empty:
        df_px_eval = df_pixels_s2.copy()
        df_px_eval["date"] = pd.to_datetime(df_px_eval["date"])
        
        # Baselines causales par pixel 10m
        if "NDWI" in df_px_eval.columns:
            df_px_eval["Z_NDWI_px"] = bc.calculer_baseline_glissante_causale(df_px_eval, col_target="NDWI", group_col="parcel_id")
        else:
            df_px_eval["Z_NDWI_px"] = np.nan

        if "NDRE" in df_px_eval.columns:
            df_px_eval["Z_NDRE_px"] = bc.calculer_baseline_glissante_causale(df_px_eval, col_target="NDRE", group_col="parcel_id")
        else:
            df_px_eval["Z_NDRE_px"] = np.nan

        # Anomalie spatiale pixel
        df_px_eval = bc.calculer_anomalie_spatiale_pixel(df_px_eval, col_target="NDVI", buffer_m=10.0, geojson_paths=geojson_paths)

        # Tri chronologique par pixel pour le moteur de mémoire/persistance
        df_px_eval = df_px_eval.sort_values(["parcel_id", "longitude", "latitude", "date"]).reset_index(drop=True)
        pixel_memory = {}

        for idx, row in df_px_eval.iterrows():
            pid = row.get("parcel_id", "inconnu")
            dt = pd.to_datetime(row.get("date"))
            site = row.get("site", "inconnu")
            culture = row.get("culture", "DEFAULT")
            lon = row.get("longitude", np.nan)
            lat = row.get("latitude", np.nan)
            ndvi_px = row.get("NDVI", np.nan)
            ndre_px = row.get("NDRE", np.nan)
            ndwi_px = row.get("NDWI", np.nan)
            lst_eco = row.get("LST_ECOSTRESS_C", np.nan)
            sm_nis = row.get("soil_moisture_vol", np.nan)
            vv_db = row.get("VV_dB", np.nan)
            tmax = row.get("Tmax_C", np.nan)
            z_sp = row.get("Z_spatial", np.nan)
            chute = row.get("chute_pct_vs_parcelle", np.nan)
            est_bordure = row.get("est_bordure", False)

            z_ndwi = row.get("Z_NDWI_px", np.nan)
            z_ndre = row.get("Z_NDRE_px", np.nan)

            alts_px = []
            grav_max = "SAIN"

            # 1. Stress Hydrique Pixel
            if not np.isnan(z_ndwi) and z_ndwi <= -1.5:
                alts_px.append("ALERTE_1_STRESS_HYDRIQUE")
                grav_max = "AVERTISSEMENT"

            # 2. Stress Azoté Pixel
            if not np.isnan(z_ndre) and z_ndre <= -1.5:
                alts_px.append("ALERTE_2_STRESS_AZOTE_FORT")
                grav_max = "AVERTISSEMENT"

            # 3. Stress Canicule Pixel
            if not np.isnan(tmax) and tmax >= 35.0:
                alts_px.append("ALERTE_4_STRESS_THERMIQUE_CANICULE")
                grav_max = "CRITIQUE" if tmax >= 38.0 else "AVERTISSEMENT"

            # 4. Anomalie Spatiale Pixel (Alerte 7)
            if not est_bordure and not np.isnan(z_sp) and z_sp <= -2.0 and not np.isnan(chute) and chute <= -0.20:
                alts_px.append("ALERTE_7_ANOMALIE_NON_ATTRIBUEE")
                grav_max = "CRITIQUE"
                
                # Ajouter aussi à la synthèse Cat A
                conf = cfg_alt.calculer_score_confiance_alerte(n_familles=1, facteur_echelle=1.0)
                alertes_cat_a.append({
                    "site": site, "parcel_id": pid, "date": dt, "culture": culture,
                    "type_alerte": "ALERTE_7_ANOMALIE_NON_ATTRIBUEE",
                    "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_7_ANOMALIE_NON_ATTRIBUEE"]["nom"],
                    "categorie": "A_RISQUES_NATURELS", "gravite": "CRITIQUE",
                    "score_confiance": conf["score_confiance"],
                    "niveau_confiance": conf["niveau_confiance"],
                    "familles_impliquees": 1, "statut": "DECLENCHEE",
                    "details": f"Pixel 10m (lon={lon:.5f}, lat={lat:.5f}) hors bordure avec chute NDVI intra-parcelle -{abs(chute)*100:.1f}% (Z_spatial={z_sp:.2f})"
                })

            # 5. Écart occupation réelle vs déclarée (Alerte 10)
            stades_culture = cfg_alt.STADES_PHENOLOGIQUES_PAR_CULTURE.get(culture, cfg_alt.STADES_PHENOLOGIQUES_PAR_CULTURE.get("DEFAULT", []))
            ndvi_min_attendu = 0.15
            for st in stades_culture:
                if dt.month in st.get("mois", []):
                    ndvi_min_attendu = st.get("ndvi_min", 0.15)
                    break

            if not np.isnan(ndvi_px) and ndvi_px < ndvi_min_attendu:
                alts_px.append("ALERTE_10_ECART_OCCUPATION_REELLE_VS_DECLAREES")
                if grav_max == "SAIN":
                    grav_max = "AVERTISSEMENT"

            # --- ÉVALUATION DU STATUT AGRONOMIQUE RÉEL DU PIXEL & PARCELLE ---
            # Le statut du pixel reflète la santé physiologique et l'état réel du couvert,
            # indépendamment du déclenchement d'une alerte (qui est consigné dans alertes_detectees).
            if np.isnan(ndvi_px) and np.isnan(ndwi_px):
                statut_px = "NON_EVALUABLE"
                conf_score = 0.0
            elif (isinstance(culture, str) and culture.lower() in ["sol nu", "friche", "jachere"]) or (ndvi_px < 0.12 and not np.isnan(ndvi_px)):
                statut_px = "SOL_NU"
                conf_score = 90.0
            elif not np.isnan(z_ndwi) and z_ndwi <= -1.8 and not np.isnan(z_ndre) and z_ndre <= -1.5:
                statut_px = "STRESS_SEVERE"
                conf_score = 85.0
            elif not np.isnan(tmax) and tmax >= 38.0:
                statut_px = "STRESS_THERMIQUE_CRITIQUE"
                conf_score = 90.0
            elif not est_bordure and not np.isnan(z_sp) and z_sp <= -2.0 and not np.isnan(chute) and chute <= -0.20:
                statut_px = "ANOMALIE_LOCALE"
                conf_score = 80.0
            elif not np.isnan(z_ndwi) and z_ndwi <= -1.2:
                statut_px = "STRESS_HYDRIQUE"
                conf_score = 85.0
            elif not np.isnan(z_ndre) and z_ndre <= -1.2:
                statut_px = "STRESS_AZOTE"
                conf_score = 80.0
            elif not np.isnan(tmax) and tmax >= 35.0:
                statut_px = "STRESS_THERMIQUE"
                conf_score = 85.0
            elif (not np.isnan(z_ndwi) and z_ndwi <= -0.8) or (not np.isnan(z_ndre) and z_ndre <= -0.8) or (not np.isnan(ndvi_px) and ndvi_px < ndvi_min_attendu):
                statut_px = "VIGILANCE"
                conf_score = 80.0
            else:
                statut_px = "SAIN"
                conf_score = 100.0

            # --- SYNTHÈSE DES ALERTES DÉTECTÉES ---
            str_alts = "; ".join(alts_px) if alts_px else "AUCUNE_ALERTE"

            alertes_pixel_10m.append({
                "site": site, "parcel_id": pid, "date": dt,
                "longitude": lon, "latitude": lat, "culture": culture,
                "statut_pixel": statut_px,
                "alertes_detectees": str_alts,
                "gravite_max": grav_max,
                "NDVI_pixel": ndvi_px,
                "NDRE_pixel": ndre_px,
                "NDWI_pixel": ndwi_px,
                "LST_ECOSTRESS": lst_eco,
                "SM_NISAR": sm_nis,
                "VV_dB": vv_db,
                "Tmax_C": tmax,
                "Z_spatial": z_sp,
                "chute_pct": chute,
                "score_confiance": conf_score
            })

    # -------------------------------------------------------------------
    # CATÉGORIE C : Cohérence Registre / Satellite (Alertes #11 à #15)
    # -------------------------------------------------------------------
    if registre_taches is not None and not registre_taches.empty:
        reg = registre_taches.copy()
        if "date" not in reg.columns:
            if "date_observation_terrain" in reg.columns:
                reg["date"] = reg["date_observation_terrain"]
            elif "date_debut_signal_satellite" in reg.columns:
                reg["date"] = reg["date_debut_signal_satellite"]
        if "type_tache" not in reg.columns and "categorie_evenement" in reg.columns:
            reg["type_tache"] = reg["categorie_evenement"]
        reg["date"] = pd.to_datetime(reg["date"])
        for idx, r_row in reg.iterrows():
            r_pid = r_row.get("parcel_id")
            r_dt = r_row.get("date")
            r_type = str(r_row.get("type_tache", "")).upper()

            sub_p = df[df["parcel_id"] == r_pid].sort_values("date")
            if sub_p.empty:
                continue

            r_site = sub_p.iloc[0].get("site", "inconnu")
            r_culture = sub_p.iloc[0].get("culture", "DEFAULT")

            # Alerte 11 : Récolte / désherbage déclaré terminé, signal inchangé
            if any(k in r_type for k in ["DESHERBAGE", "NETTOYAGE", "FAUCHE", "RECOLTE_COMPLETE"]):
                sub_post = sub_p[(sub_p["date"] >= r_dt) & (sub_p["date"] <= r_dt + pd.Timedelta(days=7))]
                if not sub_post.empty and "NDVI" in sub_p.columns:
                    pre_ndvi_s = sub_p[sub_p["date"] <= r_dt]["NDVI"].dropna()
                    if not pre_ndvi_s.empty:
                        pre_ndvi = pre_ndvi_s.iloc[-1]
                        post_ndvi_min = sub_post["NDVI"].min()
                        delta_ndvi = post_ndvi_min - pre_ndvi
                        if delta_ndvi > -0.05:
                            conf = cfg_alt.calculer_score_confiance_alerte(n_familles=1, facteur_echelle=1.0)
                            alertes_cat_c.append({
                                "site": r_site, "parcel_id": r_pid, "date": r_dt, "culture": r_culture,
                                "type_alerte": "ALERTE_11_RECOLTE_DESHERBAGE_SANS_CHANGEMENT",
                                "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_11_RECOLTE_DESHERBAGE_SANS_CHANGEMENT"]["nom"],
                                "categorie": "C_COHERENCE_REGISTRE", "gravite": "AVERTISSEMENT",
                                "score_confiance": conf["score_confiance"],
                                "niveau_confiance": conf["niveau_confiance"],
                                "familles_impliquees": 1, "statut": "DECLENCHEE",
                                "details": f"Opération {r_type} déclarée le {r_dt.strftime('%Y-%m-%d')} sans baisse significative de biomasse (ΔNDVI={delta_ndvi:+.3f} > -0.05)"
                            })

            # Alerte 12 : Plantation déclarée sans levée détectée
            if any(k in r_type for k in ["PLANTATION", "SEMIS", "REPIQUAGE"]):
                sub_post_emergence = sub_p[(sub_p["date"] >= r_dt + pd.Timedelta(days=15)) & (sub_p["date"] <= r_dt + pd.Timedelta(days=60))]
                if not sub_post_emergence.empty:
                    pre_savi_s = sub_p[sub_p["date"] <= r_dt]["SAVI"].dropna() if "SAVI" in sub_p.columns else pd.Series(dtype=float)
                    pre_savi = pre_savi_s.iloc[-1] if not pre_savi_s.empty else 0.05
                    max_savi_post = sub_post_emergence["SAVI"].max() if "SAVI" in sub_post_emergence.columns else 0.05
                    max_fc_post = sub_post_emergence["fCover"].max() if "fCover" in sub_post_emergence.columns else 0.0
                    
                    if (max_savi_post - pre_savi) < 0.03 and max_fc_post < 0.05:
                        conf = cfg_alt.calculer_score_confiance_alerte(n_familles=1, facteur_echelle=1.0)
                        alertes_cat_c.append({
                            "site": r_site, "parcel_id": r_pid, "date": r_dt, "culture": r_culture,
                            "type_alerte": "ALERTE_12_PLANTATION_SANS_LEVEE",
                            "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_12_PLANTATION_SANS_LEVEE"]["nom"],
                            "categorie": "C_COHERENCE_REGISTRE", "gravite": "AVERTISSEMENT",
                            "score_confiance": conf["score_confiance"],
                            "niveau_confiance": conf["niveau_confiance"],
                            "familles_impliquees": 1, "statut": "DECLENCHEE",
                            "details": f"Plantation déclarée le {r_dt.strftime('%Y-%m-%d')} sans levée observée après 15-60j (SAVI={max_savi_post:.2f}, fCover={max_fc_post:.2f})"
                        })

            # Alerte 13 : Irrigation déclarée sans réponse hydrique
            if "IRRIGATION" in r_type:
                sub_post = sub_p[(sub_p["date"] >= r_dt) & (sub_p["date"] <= r_dt + pd.Timedelta(days=5))]
                if not sub_post.empty:
                    max_ndwi_diff = sub_post["NDWI"].max() - sub_p[sub_p["date"] <= r_dt]["NDWI"].tail(1).values[0] if "NDWI" in sub_p.columns else 0.0
                    if max_ndwi_diff < 0.05:
                        conf = cfg_alt.calculer_score_confiance_alerte(n_familles=2, facteur_echelle=1.0)
                        alertes_cat_c.append({
                            "site": r_site, "parcel_id": r_pid, "date": r_dt, "culture": r_culture,
                            "type_alerte": "ALERTE_13_IRRIGATION_SANS_REPONSE_HYDRIQUE",
                            "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_13_IRRIGATION_SANS_REPONSE_HYDRIQUE"]["nom"],
                            "categorie": "C_COHERENCE_REGISTRE", "gravite": "CRITIQUE",
                            "score_confiance": conf["score_confiance"],
                            "niveau_confiance": conf["niveau_confiance"],
                            "familles_impliquees": 2, "statut": "DECLENCHEE",
                            "details": f"Irrigation déclarée le {r_dt.strftime('%Y-%m-%d')} sans hausse NDWI (< 5%)"
                        })

            # Alerte 14 : Coupe PAM déclarée sans ΔNDVI caractéristique
            if any(k in r_type for k in ["COUPE", "TAILLE", "RECOLTE"]):
                sub_post = sub_p[(sub_p["date"] >= r_dt) & (sub_p["date"] <= r_dt + pd.Timedelta(days=5))]
                if not sub_post.empty:
                    min_ndvi_diff = sub_post["NDVI"].min() - sub_p[sub_p["date"] <= r_dt]["NDVI"].tail(1).values[0] if "NDVI" in sub_p.columns else 0.0
                    if min_ndvi_diff > -0.10:
                        conf = cfg_alt.calculer_score_confiance_alerte(n_familles=1, facteur_echelle=1.0)
                        alertes_cat_c.append({
                            "site": r_site, "parcel_id": r_pid, "date": r_dt, "culture": r_culture,
                            "type_alerte": "ALERTE_14_COUPE_PAM_SANS_SAUT_NDVI",
                            "nom_alerte": cfg_alt.REGISTRE_ALERTES["ALERTE_14_COUPE_PAM_SANS_SAUT_NDVI"]["nom"],
                            "categorie": "C_COHERENCE_REGISTRE", "gravite": "AVERTISSEMENT",
                            "score_confiance": conf["score_confiance"],
                            "niveau_confiance": conf["niveau_confiance"],
                            "familles_impliquees": 1, "statut": "DECLENCHEE",
                            "details": f"Opération {r_type} le {r_dt.strftime('%Y-%m-%d')} sans chute ΔNDVI ≤ -0.10"
                        })

    # Conversion en DataFrames
    cols_out = [
        "site", "parcel_id", "date", "culture", "type_alerte", "nom_alerte",
        "categorie", "gravite", "score_confiance", "niveau_confiance",
        "familles_impliquees", "statut", "details"
    ]

    cols_px = [
        "site", "parcel_id", "date", "longitude", "latitude", "culture",
        "statut_pixel", "alertes_detectees", "gravite_max",
        "NDVI_pixel", "NDRE_pixel", "NDWI_pixel",
        "LST_ECOSTRESS", "SM_NISAR", "VV_dB", "Tmax_C",
        "Z_spatial", "chute_pct", "score_confiance"
    ]

    df_a = pd.DataFrame(alertes_cat_a, columns=cols_out) if alertes_cat_a else pd.DataFrame(columns=cols_out)
    df_b = pd.DataFrame(alertes_cat_b, columns=cols_out) if alertes_cat_b else pd.DataFrame(columns=cols_out)
    df_c = pd.DataFrame(alertes_cat_c, columns=cols_out) if alertes_cat_c else pd.DataFrame(columns=cols_out)
    df_px = pd.DataFrame(alertes_pixel_10m, columns=cols_px) if alertes_pixel_10m else pd.DataFrame(columns=cols_px)

    return {
        "risques_naturels": df_a,
        "comparaison": df_b,
        "coherence": df_c,
        "alertes_pixel_10m": df_px
    }
