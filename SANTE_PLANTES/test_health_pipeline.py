"""
test_health_pipeline.py
===================================================================
Suite de tests automatisés (Regression & Verification) pour le module Santé des Plantes AWAM.
Vérifie la validité des plages de scores [0, 100], le fonctionnement du modèle LAI,
l'idempotence des fonctions, et la cohérence du marquage de confiance.
"""

import sys
import pathlib
import pytest
import pandas as pd
import numpy as np

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
IRRIGATION_DIR = SCRIPT_DIR.parent / "IRRIGATION"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(IRRIGATION_DIR))

import config_sante as cfg
import lai_model as lai
import compute_health_scores as chs
import compute_awam_index as cai


@pytest.fixture(scope="module")
def sample_health_panel():
    """Crée un DataFrame factice avec différentes combinaisons d'indices pour les tests."""
    data = {
        "site": ["sidi_mechreg"] * 5 + ["makthar"] * 5,
        "parcel_id": ["sidi_mechreg_Parcelle_Badreddine_5"] * 5 + ["makthar_P1"] * 5,
        "culture": ["Olivier"] * 5 + ["Amandier"] * 5,
        "date": pd.date_range("2026-06-01", periods=5).tolist() * 2,
        "NDVI": [0.45, 0.42, 0.38, 0.35, 0.30, 0.12, 0.11, 0.10, 0.09, 0.08],
        "NDRE": [0.22, 0.20, 0.18, 0.15, 0.12, 0.06, 0.05, 0.05, 0.04, 0.04],
        "NDMI": [0.15, 0.12, 0.08, 0.05, 0.01, -0.08, -0.10, -0.12, -0.14, -0.16],
        "NDWI": [0.05, 0.02, -0.01, -0.04, -0.08, -0.15, -0.16, -0.17, -0.18, -0.19],
        "SAVI": [0.35, 0.32, 0.28, 0.25, 0.20, 0.09, 0.08, 0.07, 0.06, 0.05],
        "EVI":  [0.38, 0.34, 0.30, 0.26, 0.22, 0.08, 0.07, 0.06, 0.05, 0.04],
        "VARI": [0.15, 0.12, 0.10, 0.08, 0.05, -0.05, -0.06, -0.07, -0.08, -0.09],
        "fCover": [0.28, 0.25, 0.22, 0.18, 0.14, 0.04, 0.03, 0.03, 0.02, 0.01],
        "SMI":   [0.60, 0.55, 0.50, 0.45, 0.40, 0.25, 0.20, 0.18, 0.15, 0.12],
        "CWSI_proxy": [0.25, 0.30, 0.35, 0.40, 0.50, 0.70, 0.75, 0.80, 0.85, 0.90],
        "Tmax_C": [28.0, 30.0, 34.0, 39.0, 42.0, 35.0, 37.0, 40.0, 41.0, 43.0],
        "Tmin_C": [18.0, 19.0, 21.0, 23.0, 25.0, -1.0, -4.0, 15.0, 16.0, 17.0],
        "precip_mm": [0.0, 0.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    }
    return pd.DataFrame(data)


def test_poids_awam_somme_1():
    """Test #1 : La somme des pondérations de l'Indice AWAM doit valoir 1.0 (100%)."""
    poids = cfg.POIDS_SANTE_AWAM_DEFAUT
    total = sum(poids.values())
    assert abs(total - 1.0) < 1e-6, f"Somme des poids invalide : {total} != 1.0"


def test_lai_sl2p_fcover():
    """Test #2 : Vérifie l'estimation officielle du LAI SL2P à partir du fCover et de la culture."""
    fcover = 0.279831 # ~28%
    lai_val = lai.estimer_lai_sl2p_fcover(fcover, culture="Amandier")
    assert 0.5 <= lai_val <= 0.8, f"Valeur LAI hors bornes attendues : {lai_val}"
    
    # fCover à zero
    lai_zero = lai.estimer_lai_sl2p_fcover(0.0, culture="Olivier")
    assert lai_zero == 0.0, "LAI pour fCover=0 doit être 0.0"

    # Test résolution k-extinction spécifique et polyculture
    k_thym = lai.obtenir_k_extinction("Thym")
    assert k_thym == 0.40, f"k Thym attendu 0.40, obtenu {k_thym}"
    k_citron = lai.obtenir_k_extinction("Citronnelle")
    assert k_citron == 0.60, f"k Citronnelle attendu 0.60, obtenu {k_citron}"
    k_poly = lai.obtenir_k_extinction("Lavande/Romarin/Geranium")
    assert abs(k_poly - np.mean([0.45, 0.45, 0.50])) < 1e-3, f"k polyculture incorrect: {k_poly}"



def test_confiance_labels():
    """Test #3 : Vérifie la classification de confiance selon fCover."""
    assert chs.determiner_confiance_fcover(0.20) == "HAUTE"
    assert chs.determiner_confiance_fcover(0.10) == "MOYENNE"
    assert chs.determiner_confiance_fcover(0.02) == "BASSE"


def test_score_ranges_0_100(sample_health_panel):
    """Test #4 : Tous les scores composites calculés doivent être bornés dans [0, 100]."""
    df_res = chs.calculer_tous_les_scores_sante(sample_health_panel)
    df_awam = cai.calculer_indice_sante_awam(df_res)

    cols_scores = [
        "score_vigueur_vegetative",
        "score_chlorophylle",
        "score_stress_hydrique",
        "score_couverture_canopee",
        "score_suivi_phenologique",
        "score_detection_anomalie",
        "score_risque_maladie",
        "score_qualite_sol",
        "score_temperature_stress",
        "score_sante_awam",
    ]

    for col in cols_scores:
        assert col in df_awam.columns, f"Colonne manquante : {col}"
        vals = df_awam[col].dropna()
        assert (vals >= 0.0).all() and (vals <= 100.0).all(), f"Valeurs hors [0, 100] dans {col}"


def test_idempotence_scores(sample_health_panel):
    """Test #5 : L'exécution répétée du calcul des scores produit le même résultat."""
    res1 = chs.calculer_tous_les_scores_sante(sample_health_panel)
    res2 = chs.calculer_tous_les_scores_sante(res1)
    
    pd.testing.assert_series_equal(res1["score_sante_awam"] if "score_sante_awam" in res1 else res1["score_vigueur_vegetative"],
                                   res2["score_sante_awam"] if "score_sante_awam" in res2 else res2["score_vigueur_vegetative"])


def test_temperature_stress_penalty(sample_health_panel):
    """Test #6 : Vérifie la pénalité pour forte chaleur (Tmax >= 38°C) et gel (Tmin <= -3°C)."""
    df_res = chs.calculer_score_temperature_stress(sample_health_panel)
    
    # Ligne 4 (index 3) a Tmax=39°C -> doit avoir une pénalité
    score_hot = df_res.at[3, "score_temperature_stress"]
    assert score_hot < 100.0, "Une température de 39°C doit générer une pénalité"

    # Ligne 7 (index 6) a Tmin=-4°C -> doit avoir une forte pénalité gel
    score_frost = df_res.at[6, "score_temperature_stress"]
    assert score_frost <= 40.0, "Un gel de -4°C doit générer une pénalité sévère"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
