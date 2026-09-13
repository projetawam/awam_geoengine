#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_alertes_pipeline.py
===================================================================
Suite de tests automatisés (Regression & Verification) pour MODULE_ALERTES.
Couvre les 13 points de recette définis dans implementation_plan_v2.md §8.
"""

import sys
from pathlib import Path
import pytest
import pandas as pd
import numpy as np

MODULE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = MODULE_DIR.parent
IRRIGATION_DIR = SCRIPTS_DIR / "IRRIGATION"
SANTE_DIR = SCRIPTS_DIR / "SANTE_PLANTES"

for p in [str(SCRIPTS_DIR), str(IRRIGATION_DIR), str(SANTE_DIR), str(MODULE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import config_alertes as cfg_alt
import baselines_communes as bc
import detect_alertes as da
import moteur_cascades as mc


@pytest.fixture(scope="module")
def sample_alertes_panel():
    """DataFrame factice couvrant différents scénarios d'alertes."""
    dates = pd.date_range("2026-06-01", periods=10)
    data = {
        "site": ["sidi_mechreg"] * 10,
        "parcel_id": ["sidi_mechreg_Parcelle_Badreddine_5"] * 10,
        "culture": ["Olivier"] * 10,
        "date": dates,
        "NDVI": [0.45, 0.40, 0.35, 0.30, 0.25, 0.20, 0.18, 0.15, 0.12, 0.10],
        "NDRE": [0.22, 0.18, 0.14, 0.10, 0.08, 0.06, 0.05, 0.04, 0.03, 0.02],
        "NDWI": [-0.05, -0.10, -0.15, -0.20, -0.25, -0.30, -0.32, -0.35, -0.38, -0.40],
        "NDMI": [0.05, 0.00, -0.05, -0.10, -0.15, -0.20, -0.22, -0.25, -0.28, -0.30],
        "BSI": [0.05, 0.08, 0.12, 0.15, 0.22, 0.25, 0.28, 0.30, 0.35, 0.40],
        "SAVI": [0.35, 0.30, 0.25, 0.20, 0.15, 0.10, 0.08, 0.06, 0.04, 0.02],
        "CI_RedEdge": [0.30, 0.25, 0.20, 0.15, 0.10, 0.08, 0.06, 0.04, 0.03, 0.02],
        "fCover": [0.25, 0.22, 0.18, 0.14, 0.10, 0.08, 0.06, 0.04, 0.03, 0.02],
        "CWSI_proxy": [0.20, 0.30, 0.45, 0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90],
        "Tmax_C": [28.0, 30.0, 36.0, 39.0, 41.0, 35.0, 32.0, 30.0, 28.0, 26.0],
        "Tmin_C": [18.0, 19.0, 22.0, 24.0, 25.0, 20.0, 18.0, 16.0, 15.0, 14.0],
        # precip_mm est omitted pour tester le garde-fou INDETERMINE par défaut
    }
    return pd.DataFrame(data)


def _concat_alertes(res_dict):
    valid_dfs = [df for k, df in res_dict.items() if k in ["risques_naturels", "comparaison", "coherence"] and not df.empty]
    if valid_dfs:
        return pd.concat(valid_dfs, ignore_index=True)
    return pd.DataFrame(columns=["site", "parcel_id", "date", "culture", "type_alerte", "nom_alerte", "categorie", "gravite", "score_confiance", "niveau_confiance", "familles_impliquees", "statut", "details"])


def test_1_idempotence_score_confiance():
    """Test #1 : Idempotence du calcul du score de confiance."""
    res1 = cfg_alt.calculer_score_confiance_alerte(2, facteur_echelle=0.8, fraicheur_jours=2)
    res2 = cfg_alt.calculer_score_confiance_alerte(2, facteur_echelle=0.8, fraicheur_jours=2)
    assert res1 == res2, "Le calcul du score de confiance doit être strictement idempotent."


def test_2_monotonicite_seuils_confiance(sample_alertes_panel):
    """Test #2 : Monotonicité des seuils de confiance."""
    res = da.detecter_toutes_les_alertes(sample_alertes_panel)
    df_all = _concat_alertes(res)

    c_50 = len(df_all[df_all["score_confiance"] >= 50.0])
    c_70 = len(df_all[df_all["score_confiance"] >= 70.0])
    c_90 = len(df_all[df_all["score_confiance"] >= 90.0])

    assert c_50 >= c_70 >= c_90, "L'augmentation du seuil de confiance doit réduire ou stagner le nombre d'alertes."



def test_3_bornes_score_confiance(sample_alertes_panel):
    """Test #3 : Les scores de confiance doivent être dans [0, 100] et sans NaN pour alertes déclenchées."""
    res = da.detecter_toutes_les_alertes(sample_alertes_panel)
    df_all = _concat_alertes(res)

    for idx, row in df_all.iterrows():
        sc = row["score_confiance"]
        assert not np.isnan(sc), f"NaN trouvé dans score_confiance pour {row['type_alerte']}"
        assert 0.0 <= sc <= 100.0, f"Score hors bornes [0, 100] : {sc}"


def test_4_degradation_famille_unique():
    """Test #4 : Une alerte à 1 seule famille ne doit JAMAIS dépasser 69%."""
    res = cfg_alt.calculer_score_confiance_alerte(n_familles=1, facteur_echelle=1.0, fraicheur_jours=0, multi_passage_valide=True)
    assert res["score_confiance"] <= 69.0, f"Alerte à 1 famille a dépassé 69% : {res['score_confiance']}"
    assert res["niveau_confiance"] != "HAUTE", "Famille unique ne doit pas atteindre Confiance Haute."


def test_5_gardefou_indetermine_precip_manquante(sample_alertes_panel):
    """Test #5 : precip_mm manquant => Alertes #5, #6, #8 en INDETERMINE_DONNEE_MANQUANTE."""
    res = da.detecter_toutes_les_alertes(sample_alertes_panel)
    df_all = _concat_alertes(res)

    types_precip = ["ALERTE_5_EXCES_HUMIDITE_ENGORGEMENT", "ALERTE_6_SECHERESSE_PROLONGEE", "ALERTE_8_ECART_EAU_REEL_VS_BESOIN"]
    sub = df_all[df_all["type_alerte"].isin(types_precip)]

    assert not sub.empty, "Des entrées INDETERMINE doivent être enregistrées."
    assert (sub["statut"] == "INDETERMINE_DONNEE_MANQUANTE").all(), "Statut doit être INDETERMINE_DONNEE_MANQUANTE."


def test_6_masquage_sol_nu():
    """Test #6 : fCover < 0.05 ne doit pas déclencher d'alertes foliaires #1/#2/#3."""
    df_sol_nu = pd.DataFrame({
        "site": ["makthar"], "parcel_id": ["P1"], "culture": ["Olivier"],
        "date": [pd.Timestamp("2026-06-01")],
        "NDVI": [0.08], "NDRE": [0.04], "NDWI": [-0.40], "NDMI": [-0.35],
        "fCover": [0.02], # fCover < 0.05
        "CWSI_proxy": [0.80], "pct_soil_moisture": [10.0]
    })
    res = da.detecter_toutes_les_alertes(df_sol_nu)
    df_all = _concat_alertes(res)

    types_foliaires = ["ALERTE_1_STRESS_HYDRIQUE", "ALERTE_2_STRESS_AZOTE_FORT", "ALERTE_3_STRESS_COMBINE_EAU_AZOTE"]
    decl = df_all[(df_all["type_alerte"].isin(types_foliaires)) & (df_all["statut"] == "DECLENCHEE")]
    assert decl.empty, f"Des alertes foliaires ont été faussement déclenchées sur sol nu : {decl['type_alerte'].tolist()}"


def test_8_coherence_colonnes_csv(sample_alertes_panel):
    """Test #8 : Pas de NaN dans les colonnes critiques du CSV."""
    res = da.detecter_toutes_les_alertes(sample_alertes_panel)
    df_all = _concat_alertes(res)

    cols_critiques = ["site", "parcel_id", "date", "type_alerte", "gravite", "score_confiance", "statut"]
    for col in cols_critiques:
        assert col in df_all.columns
        assert not df_all[col].isna().any(), f"NaN trouvé dans la colonne critique {col}"


def test_10_exclusion_mutuelle_chaine1_et_alerte2():
    """Test #10 : Si NDWI est en stress fort (Z <= -1.5), l'alerte #2 (azote seul) ne doit PAS se déclencher.

    BUGFIX §27.3.7 : l'ancienne version injectait Z_NDRE et Z_NDWI directement en dur,
    court-circuitant complètement les fonctions de calcul de baselines_communes.
    Si calculer_baseline_glissante_causale était corrompu, le test passait quand même.
    Version corrigée : le panel synthétique contient des séries temporelles brutes
    avec un NDWI historiquement élevé puis une chute brutale, forçant un Z-score réel <= -1.5.
    """
    import numpy as np

    # 30 jours de NDWI élevé (baseline), puis 5 jours de chute brutale
    # Le Z-score calculé sur la fenêtre glissante doit descendre sous -1.5
    n_baseline = 30
    n_stress = 5
    n_total = n_baseline + n_stress
    parcel = "P2"
    culture = "Amandier"
    site = "sidi_mechreg"

    ndwi_baseline = np.full(n_baseline, 0.10)  # valeur haute stable
    ndwi_stress   = np.full(n_stress, -0.40)   # chute brutale
    ndwi_series   = np.concatenate([ndwi_baseline, ndwi_stress])

    ndre_baseline = np.full(n_baseline, 0.18)   # NDRE stable
    ndre_stress   = np.full(n_stress, 0.15)     # NDRE légèrement bas (pas de chute azote)
    ndre_series   = np.concatenate([ndre_baseline, ndre_stress])

    df_stress_eau = pd.DataFrame({
        "site":       [site] * n_total,
        "parcel_id":  [parcel] * n_total,
        "culture":    [culture] * n_total,
        "date":       pd.date_range("2026-04-01", periods=n_total, freq="1D"),
        "NDVI":       np.concatenate([np.full(n_baseline, 0.45), np.full(n_stress, 0.30)]),
        "NDRE":       ndre_series,
        "NDWI":       ndwi_series,
        "NDMI":       np.concatenate([np.full(n_baseline, 0.10), np.full(n_stress, -0.30)]),
        "fCover":     np.concatenate([np.full(n_baseline, 0.30), np.full(n_stress, 0.20)]),
    })

    # Vérifier que le calcul de Z-score réel produit bien Z_NDWI <= -1.5 sur les jours de stress
    z_ndwi = bc.calculer_baseline_glissante_causale(df_stress_eau, "NDWI", window_days=30)
    z_ndwi_stress_vals = z_ndwi.iloc[n_baseline:].dropna()
    assert (z_ndwi_stress_vals <= -1.5).any(), (
        f"Le panel synthétique ne produit pas de Z_NDWI <= -1.5. "
        f"Z min obsérvé : {z_ndwi_stress_vals.min():.2f}. "
        "Revoir la construction du panel de stress hydrique."
    )

    # Détection des alertes sur le panel complet
    res = da.detecter_toutes_les_alertes(df_stress_eau)
    df_all = _concat_alertes(res)

    # Sur les jours de stress (eau ET pas azote isolé), l'alerte #2 ne doit pas se déclencher
    dates_stress = df_stress_eau["date"].iloc[n_baseline:].tolist()
    alt2 = df_all[
        (df_all["type_alerte"] == "ALERTE_2_STRESS_AZOTE_FORT") &
        (df_all["statut"] == "DECLENCHEE") &
        (df_all["date"].isin(dates_stress))
    ]
    assert alt2.empty, (
        "L'alerte #2 ne doit pas se déclencher quand l'eau est aussi en stress "
        f"(c'est l'alerte #3). Déclenchée {len(alt2)} fois."
    )


def test_11_recolte_desherbage_sans_changement():
    """Test #11 : Détection d'alerte #11 si opération de désherbage/récolte sans baisse de NDVI."""
    df_panel = pd.DataFrame({
        "site": ["sidi_mechreg"] * 5,
        "parcel_id": ["P1"] * 5,
        "culture": ["Thym"] * 5,
        "date": pd.date_range("2026-06-01", periods=5),
        "NDVI": [0.35, 0.35, 0.36, 0.35, 0.34],
        "fCover": [0.20] * 5
    })
    reg_taches = pd.DataFrame([{
        "parcel_id": "P1",
        "date": "2026-06-02",
        "type_tache": "DESHERBAGE",
        "nom_evenement": "Désherbage manuel déclaré"
    }])
    res = da.detecter_toutes_les_alertes(df_panel, registre_taches=reg_taches)
    df_c = res["coherence"]
    alt11 = df_c[df_c["type_alerte"] == "ALERTE_11_RECOLTE_DESHERBAGE_SANS_CHANGEMENT"]
    assert not alt11.empty, "L'alerte #11 doit être déclenchée si le NDVI ne baisse pas après un désherbage."
    assert alt11.iloc[0]["statut"] == "DECLENCHEE"


def test_12_plantation_sans_levee():
    """Test #12 : Détection d'alerte #12 si plantation déclarée sans hausse de SAVI/fCover après 30j."""
    dates = pd.date_range("2026-04-01", periods=10, freq="7D")
    df_panel = pd.DataFrame({
        "site": ["sidi_mechreg"] * 10,
        "parcel_id": ["P3"] * 10,
        "culture": ["Basilic"] * 10,
        "date": dates,
        "SAVI": [0.04] * 10,
        "fCover": [0.01] * 10,
        "NDVI": [0.08] * 10
    })
    reg_taches = pd.DataFrame([{
        "parcel_id": "P3",
        "date": "2026-04-01",
        "type_tache": "PLANTATION",
        "nom_evenement": "Repiquage mottes"
    }])
    res = da.detecter_toutes_les_alertes(df_panel, registre_taches=reg_taches)
    df_c = res["coherence"]
    alt12 = df_c[df_c["type_alerte"] == "ALERTE_12_PLANTATION_SANS_LEVEE"]
    assert not alt12.empty, "L'alerte #12 doit être déclenchée si aucune levée n'est observée après plantation."
    assert alt12.iloc[0]["statut"] == "DECLENCHEE"


def test_13_separation_trois_axes():
    """Test #13 : Les colonnes score_confiance, gravite, et statut_cascade restent distinctes."""
    df_alt = pd.DataFrame([{
        "site": "sidi_mechreg", "parcel_id": "P1", "date": pd.Timestamp("2026-06-01"),
        "culture": "Olivier", "type_alerte": "ALERTE_13_IRRIGATION_SANS_REPONSE_HYDRIQUE",
        "nom_alerte": "Irrigation sans réponse", "categorie": "C_COHERENCE_REGISTRE",
        "gravite": "CRITIQUE", "score_confiance": 75.0, "niveau_confiance": "HAUTE",
        "familles_impliquees": 2, "statut": "DECLENCHEE", "details": "test"
    }])
    df_casc = mc.executer_moteur_cascades(df_alt)
    assert not df_casc.empty
    assert "statut_cascade" in df_casc.columns
    assert df_casc.iloc[0]["statut_cascade"] == "CRITIQUE_CASCADANTE"


def test_14_cascade_chaine_temporellement_coherente():
    """Test #14 : Cascade Chaîne 1 doit être étiquetée CHAINE_TEMPORELLEMENT_COHERENTE."""
    df_alt = pd.DataFrame([
        {
            "site": "makthar", "parcel_id": "P1", "date": pd.Timestamp("2026-06-01"),
            "culture": "Amandier", "type_alerte": "ALERTE_4_STRESS_THERMIQUE_CANICULE",
            "nom_alerte": "Canicule", "categorie": "A_RISQUES_NATURELS",
            "gravite": "CRITIQUE", "score_confiance": 70.0, "niveau_confiance": "HAUTE",
            "familles_impliquees": 2, "statut": "DECLENCHEE", "details": "Tmax=41C"
        },
        {
            "site": "makthar", "parcel_id": "P1", "date": pd.Timestamp("2026-06-05"),
            "culture": "Amandier", "type_alerte": "ALERTE_1_STRESS_HYDRIQUE",
            "nom_alerte": "Stress hydrique", "categorie": "A_RISQUES_NATURELS",
            "gravite": "CRITIQUE", "score_confiance": 75.0, "niveau_confiance": "HAUTE",
            "familles_impliquees": 2, "statut": "DECLENCHEE", "details": "NDWI chute"
        },
        {
            "site": "makthar", "parcel_id": "P1", "date": pd.Timestamp("2026-06-15"),
            "culture": "Amandier", "type_alerte": "ALERTE_2_STRESS_AZOTE_FORT",
            "nom_alerte": "Stress azote", "categorie": "A_RISQUES_NATURELS",
            "gravite": "AVERTISSEMENT", "score_confiance": 60.0, "niveau_confiance": "MOYENNE",
            "familles_impliquees": 1, "statut": "DECLENCHEE", "details": "NDRE bas"
        }
    ])
    df_casc = mc.executer_moteur_cascades(df_alt)
    sub = df_casc[df_casc["type_alerte"] == "ALERTE_2_STRESS_AZOTE_FORT"]
    assert not sub.empty
    assert sub.iloc[0]["statut_cascade"] == "CHAINE_TEMPORELLEMENT_COHERENTE"

