#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_master_pipeline.py
===================================================================
Suite de tests automatisés (Regression & Verification) pour le Master Pipeline GeoAI.
Vérifie l'existence des 5 sous-pipelines, la cohérence des dossiers source/sortie,
l'alignement spatio-temporel inter-modules et l'absence de contradictions.
"""

import sys
import os
import pathlib
import pytest
import pandas as pd
import numpy as np

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent if SCRIPT_DIR.name == "PIPELINE_MASTER" else SCRIPT_DIR
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

import run_master_pipeline as rmp

DATA_CLEAN_DIR = SCRIPTS_DIR / "outputs" / "pixel_indices_database" / "clean"
SANTE_OUT_DIR = SCRIPTS_DIR / "SANTE_PLANTES" / "output"
IRRIG_OUT_DIR = SCRIPTS_DIR / "IRRIGATION" / "outputs" / "irrigation"
ALERT_OUT_DIR = SCRIPTS_DIR / "MODULE_ALERTES" / "output"


def test_1_sous_pipelines_exist():
    """Test #1 : Vérifie que tous les sous-scripts de pipeline existent."""
    assert rmp.STAGE1_EXTRACT.exists(), f"Script manquant : {rmp.STAGE1_EXTRACT}"
    assert rmp.STAGE2_VARI.exists(), f"Script manquant : {rmp.STAGE2_VARI}"
    assert rmp.STAGE3_SANTE.exists(), f"Script manquant : {rmp.STAGE3_SANTE}"
    assert rmp.STAGE4_IRRIG.exists(), f"Script manquant : {rmp.STAGE4_IRRIG}"
    assert rmp.STAGE5_ALERTES.exists(), f"Script manquant : {rmp.STAGE5_ALERTES}"


def test_2_base_donnees_clean_existe():
    """Test #2 : Vérifie la présence des parquets nettoyés dans outputs/pixel_indices_database/clean."""
    assert DATA_CLEAN_DIR.exists(), f"Dossier introuvable : {DATA_CLEAN_DIR}"
    parquets = list(DATA_CLEAN_DIR.glob("*.parquet"))
    assert len(parquets) > 0, "Aucun fichier parquet trouvé dans le dossier clean."


def test_3_coherence_colonnes_fichiers_sorties():
    """Test #3 : Vérifie la validité des colonnes dans les CSV générés par les 3 modules."""
    sante_csv = SANTE_OUT_DIR / "1_scores_sante_composites.csv"
    irrig_csv = IRRIG_OUT_DIR / "1_suivi_besoins_plante.csv"
    alert_csv = ALERT_OUT_DIR / "5_alertes_pixel_10m.csv"

    if not (sante_csv.exists() and irrig_csv.exists() and alert_csv.exists()):
        pytest.skip("CSV de sortie non trouvés pour le test de colonnes.")

    df_sante = pd.read_csv(sante_csv)
    df_irrig = pd.read_csv(irrig_csv)
    df_alert = pd.read_csv(alert_csv)

    for col in ["site", "parcel_id", "date", "score_sante_awam", "pastille_sante"]:
        assert col in df_sante.columns, f"Colonne santé manquante : {col}"

    for col in ["site", "parcel_id", "date", "score_stress", "STATUT_BESOIN"]:
        assert col in df_irrig.columns, f"Colonne irrigation manquante : {col}"

    for col in ["site", "parcel_id", "date", "statut_pixel", "alertes_detectees"]:
        assert col in df_alert.columns, f"Colonne alerte manquante : {col}"


def test_4_alignement_spatial_et_temporel_parcelles():
    """Test #4 : Vérifie que les 11 parcelles sont 100% identiques entre Santé, Irrigation et Alertes."""
    sante_csv = SANTE_OUT_DIR / "1_scores_sante_composites.csv"
    irrig_csv = IRRIG_OUT_DIR / "1_suivi_besoins_plante.csv"
    alert_csv = ALERT_OUT_DIR / "5_alertes_pixel_10m.csv"

    if not (sante_csv.exists() and irrig_csv.exists() and alert_csv.exists()):
        pytest.skip("CSV de sortie non trouvés pour l'alignement spatial.")

    df_sante = pd.read_csv(sante_csv)
    df_irrig = pd.read_csv(irrig_csv)
    df_alert = pd.read_csv(alert_csv)

    p_sante = set(df_sante["parcel_id"].unique())
    p_irrig = set(df_irrig["parcel_id"].unique())
    p_alert = set(df_alert["parcel_id"].unique())

    assert p_sante == p_irrig == p_alert, "Incohérence dans le jeu de parcelles inter-modules."
    assert len(p_sante) == 11, f"Nombre de parcelles inattendu : {len(p_sante)} (11 attendues)"


def test_5_regle_non_contradiction():
    """Test #5 : Vérifie l'absence de contradiction logique (Irrigation Besoin Critique MAIS Santé >= 80%)."""
    sante_csv = SANTE_OUT_DIR / "1_scores_sante_composites.csv"
    irrig_csv = IRRIG_OUT_DIR / "1_suivi_besoins_plante.csv"

    if not (sante_csv.exists() and irrig_csv.exists()):
        pytest.skip("CSV de sortie manquants.")

    df_sante = pd.read_csv(sante_csv)
    df_irrig = pd.read_csv(irrig_csv)

    df_sante["date"] = pd.to_datetime(df_sante["date"])
    df_irrig["date"] = pd.to_datetime(df_irrig["date"])

    m = pd.merge(
        df_sante[["parcel_id", "date", "score_sante_awam"]],
        df_irrig[["parcel_id", "date", "STATUT_BESOIN"]],
        on=["parcel_id", "date"], how="inner"
    )

    inc = m[(m["STATUT_BESOIN"] == "BESOIN_CRITIQUE") & (m["score_sante_awam"] >= 80.0)]
    assert inc.empty, f"Contradictions détectées : {len(inc)} cas où le besoin est critique mais la santé est >= 80%"


if __name__ == "__main__":
    print("Exécution des tests automatisés du Master Pipeline...")
    pytest.main(["-v", __file__])
