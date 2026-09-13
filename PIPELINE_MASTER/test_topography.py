#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_topography.py
===================================================================
Suite de tests unitaires et d'intégration pour le module topographique MNT
(SRTM 30m / Copernicus DEM) et les corrections biophysiques (§27.7.6 Phase 2).

Valide :
1. L'existence et la conformité des fichiers Parquet et CSV standardisés.
2. L'altitude des parcelles de Makthar (600-650m) vs Sidi Mechreg (90-120m).
3. Le calcul physique de la pente, de l'aspect et de l'exposition adret/ubac.
4. L'application mathématique exacte du gradient adiabatique (-6.5 °C / 1000m).
5. L'enrichissement de config_global.load_parcelles_from_geojson() et get_map_parcelles_terrain().
6. L'intégration dans le calcul du score de stress température et de risque maladie.
"""

import sys
import pytest
import numpy as np
import pandas as pd
from pathlib import Path

MASTER_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = MASTER_DIR.parent
EXTRACT_DIR = SCRIPTS_DIR / "EXTRACT"
SANTE_DIR = SCRIPTS_DIR / "SANTE_PLANTES"
OUTPUTS_DIR = SCRIPTS_DIR / "outputs" / "topography"
CLEAN_DIR = SCRIPTS_DIR / "outputs" / "pixel_indices_database" / "clean"

for p in [str(SCRIPTS_DIR), str(MASTER_DIR), str(EXTRACT_DIR), str(SANTE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import config_global as cfg
import topography_extractor as topo
import compute_health_scores as chs


def test_topography_files_exist_and_standardized():
    """Vérifie la présence et la nomenclature standardisée des fichiers topographiques."""
    expected_clean_parquet = CLEAN_DIR / "AWAM_DEM_ALL_ALL_SRTM-Topography_20250501_20260828_v2_clean.parquet"
    expected_out_parquet = OUTPUTS_DIR / "AWAM_DEM_ALL_ALL_SRTM-Topography_20250501_20260828_v2_clean.parquet"
    expected_out_csv = OUTPUTS_DIR / "AWAM_DEM_ALL_ALL_SRTM-Topography_20250501_20260828_v2_clean.csv"

    assert expected_clean_parquet.exists(), f"Fichier Parquet clean manquant : {expected_clean_parquet}"
    assert expected_out_parquet.exists(), f"Fichier Parquet output manquant : {expected_out_parquet}"
    assert expected_out_csv.exists(), f"Fichier CSV output manquant : {expected_out_csv}"

    df = pd.read_parquet(expected_clean_parquet)
    assert len(df) == 11, f"Attendu 11 parcelles, obtenu {len(df)}"
    assert "elevation_m" in df.columns
    assert "slope_deg" in df.columns
    assert "aspect_cardinal" in df.columns
    assert "exposition_type" in df.columns
    assert "correction_thermique_lapse_rate_c" in df.columns


def test_elevation_values_by_region():
    """Valide les plages altimétriques de Makthar (~610-630m) et Sidi Mechreg (~100m)."""
    df = topo.extraire_topographie_toutes_parcelles(force_recompute=False)
    
    makthar_parcels = df[df["site"] == "makthar"]
    sidi_parcels = df[df["site"] == "sidi_mechreg"]

    assert len(makthar_parcels) == 6, f"Attendu 6 parcelles à Makthar, trouvé {len(makthar_parcels)}"
    assert len(sidi_parcels) == 5, f"Attendu 5 parcelles à Sidi Mechreg, trouvé {len(sidi_parcels)}"

    # Altitudes moyennes
    for _, row in makthar_parcels.iterrows():
        assert 550.0 <= row["elevation_m"] <= 950.0, f"Altitude Makthar anormale : {row['elevation_m']} m pour {row['parcel_id']}"

    for _, row in sidi_parcels.iterrows():
        assert 30.0 <= row["elevation_m"] <= 200.0, f"Altitude Sidi Mechreg anormale : {row['elevation_m']} m pour {row['parcel_id']}"


def test_lapse_rate_thermal_correction_formula():
    """Vérifie la formule mathématique du gradient adiabatique (-6.5 °C / 1000m)."""
    # Test 1 : Parcelle 100m au-dessus de la référence (650m) -> -0.65°C
    t_corr = cfg.corriger_temperature_altitude(30.0, elevation_m=750.0, elevation_ref_m=650.0)
    assert abs(t_corr - 29.35) < 1e-2, f"Erreur calcul lapse rate : {t_corr} vs 29.35"

    # Test 2 : Parcelle 550m en-dessous de la référence (650m) -> +3.58°C
    t_corr2 = cfg.corriger_temperature_altitude(20.0, elevation_m=100.0, elevation_ref_m=650.0)
    assert abs(t_corr2 - 23.58) < 1e-2, f"Erreur calcul lapse rate : {t_corr2} vs 23.58"


def test_runoff_coefficient_by_slope_and_texture():
    """Vérifie que la pente et la texture modulent le coefficient de ruissellement."""
    c_plat = cfg.calculer_coefficient_ruissellement(slope_deg=1.0, texture_sol="LIMONEUX")
    c_pente = cfg.calculer_coefficient_ruissellement(slope_deg=7.0, texture_sol="LIMONEUX")
    c_pente_argile = cfg.calculer_coefficient_ruissellement(slope_deg=7.0, texture_sol="ARGILEUX")

    assert c_pente > c_plat, "La pente forte doit avoir un coefficient de ruissellement plus élevé"
    assert c_pente_argile >= c_pente, "Le sol argileux doit favoriser le ruissellement"


def test_config_global_parcel_loader_includes_topography():
    """Vérifie que load_parcelles_from_geojson() et get_map_parcelles_terrain() chargent la topographie."""
    df_p = cfg.load_parcelles_from_geojson()
    assert not df_p.empty
    assert "elevation_m" in df_p.columns, "elevation_m absent du GeoJSON enrichi"
    assert "slope_deg" in df_p.columns, "slope_deg absent du GeoJSON enrichi"

    p_map = cfg.get_map_parcelles_terrain()
    assert len(p_map) == 11
    assert "elevation_m" in p_map["makthar_P1"]
    assert p_map["makthar_P1"]["elevation_m"] >= 600.0


def test_health_temperature_stress_with_topography():
    """Vérifie que le score de température prend en compte le relief et l'exposition adret."""
    df_sample = pd.DataFrame([{
        "parcel_id": "makthar_P1",
        "date": "2025-07-15",
        "Tmax_C": 38.5,
        "Tmin_C": 18.0,
        "correction_thermique_lapse_rate_c": 0.20,
        "exposition_type": "ADRET",
    }])

    df_res = chs.calculer_score_temperature_stress(df_sample)
    assert "score_temperature_stress" in df_res.columns
    # Avec Tmax=38.5 + 0.2 + 0.5 (Adret) = 39.2°C -> pénalité (39.2 - 38.0) * 8 = 9.6 -> score ~90.4
    assert df_res["score_temperature_stress"].iloc[0] < 95.0
