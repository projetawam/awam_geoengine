"""
Suite de tests automatisés (Regression & Verification) pour le pipeline Irrigation GeoAI.
Vérifie la rigueur mathématique, l'idempotence des fonctions de score, la cohérence des colonnes
et l'absence de bruits ou fuites de données.
"""

import sys
import pathlib
import pytest
import pandas as pd
import numpy as np

# Ajouter le répertoire des scripts au path
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import detect_irrigation_vs_pluie_v3 as irr
import detect_besoin_vs_irrigation as bes
import run_irrigation_analysis as run_ana

DATA_DIR = SCRIPT_DIR.parent / "outputs" / "pixel_indices_database" / "clean"


@pytest.fixture(scope="module")
def panel_test():
    """Charge un panel de test réel depuis le dossier clean."""
    if not DATA_DIR.exists():
        pytest.skip(f"Dossier de données introuvable : {DATA_DIR}")
    fichiers = irr.decouvrir_fichiers(DATA_DIR)
    sources = {source: irr.charger_source(paths) for source, paths in fichiers.items()}
    panel = irr.construire_panel(sources)
    return panel, sources


def test_idempotence_score_composite(panel_test):
    """Test #1 : L'exécution répétée de calculer_score_composite sur un panel ne doit PAS accumuler les scores."""
    panel, _ = panel_test
    panel_copy = panel.copy()

    # 1er calcul
    for label, spec in irr.SOURCES_THERMIQUES.items():
        panel_copy, _ = irr.evidence_thermique(panel_copy, label, spec["colonne"], spec["poids"],
                                                colonne_est_kelvin=spec.get("colonne_est_kelvin", False),
                                                resolution_m=irr.SOURCE_SPECS[label]["resolution_m"])
    for colonne, seuil, poids, sens_hausse, _desc in irr.MODULES_OPTIQUES:
        panel_copy, _ = irr.evidence_optique(panel_copy, colonne, poids, seuil, sens_hausse=sens_hausse)
    panel_copy, _ = irr.evidence_humidite_sol(panel_copy)
    panel_copy, _ = irr.evidence_vwc_nisar(panel_copy)

    panel_score1 = irr.calculer_score_composite(panel_copy)
    score1 = panel_score1["score_composite"].copy()

    # 2e calcul (ré-exécution sur le même DataFrame déjà calculé)
    panel_score2 = irr.calculer_score_composite(panel_score1)
    score2 = panel_score2["score_composite"].copy()

    pd.testing.assert_series_equal(score1, score2, check_names=False)


def test_idempotence_score_stress(panel_test):
    """Test #2 : L'exécution répétée de calculer_score_stress ne doit pas gonfler le score_stress."""
    panel, _ = panel_test
    panel_copy = panel.copy()

    panel_copy, _ = bes.evidence_stress_cwsi(panel_copy)
    panel_copy, _ = bes.evidence_stress_smi(panel_copy)
    panel_copy, _ = bes.evidence_stress_soil_moisture(panel_copy)
    for col in ["NDMI", "NDWI", "NDRE", "BSI"]:
        sens = False if col == "BSI" else True
        seuil_rel = 0.04 if col == "BSI" else -0.05
        panel_copy, _ = bes.evidence_stress_optique(panel_copy, col, seuil_rel, 1.5, sens_baisse=sens)

    panel_s1 = bes.calculer_score_stress(panel_copy)
    stress1 = panel_s1["score_stress"].copy()

    # 2e calcul
    panel_s2 = bes.calculer_score_stress(panel_s1)
    stress2 = panel_s2["score_stress"].copy()

    pd.testing.assert_series_equal(stress1, stress2, check_names=False)


def test_plafonnement_famille_thermique(panel_test):
    """Test #3 : La contribution composite plafonnée d'un jour composé UNIQUEMENT de sources thermiques LST ne dépasse pas 2.0."""
    panel, _ = panel_test
    panel_copy = panel.copy()

    for label, spec in irr.SOURCES_THERMIQUES.items():
        panel_copy, _ = irr.evidence_thermique(panel_copy, label, spec["colonne"], spec["poids"],
                                                colonne_est_kelvin=spec.get("colonne_est_kelvin", False),
                                                resolution_m=irr.SOURCE_SPECS[label]["resolution_m"])
    panel_score = irr.calculer_score_composite(panel_copy)

    # Filtrer les colonnes numériques d'évidence non thermiques
    optique_cols = [c for c in panel_score.columns if c.endswith("_evidence") and np.issubdtype(panel_score[c].dtype, np.number) and not any(s in c for s in ["ECOSTRESS", "Landsat-Thermal", "MODIS-LST"])]
    thermic_only = (panel_score[optique_cols].sum(axis=1) == 0) & (panel_score["score_composite"] > 0)

    if thermic_only.any():
        max_thermic_composite = panel_score.loc[thermic_only, "score_composite"].max()
        assert max_thermic_composite <= 2.0001, f"Débordement du plafond thermique composite : {max_thermic_composite} > 2.0"


def test_monotonicite_seuils_irrigation(panel_test):
    """Test #4 : Quand le seuil de score composite augmente, le nombre d'irrigations détectées doit baisser ou stagner."""
    panel, _ = panel_test
    panel_copy = panel.copy()

    for label, spec in irr.SOURCES_THERMIQUES.items():
        panel_copy, _ = irr.evidence_thermique(panel_copy, label, spec["colonne"], spec["poids"],
                                                colonne_est_kelvin=spec.get("colonne_est_kelvin", False),
                                                resolution_m=irr.SOURCE_SPECS[label]["resolution_m"])
    for colonne, seuil, poids, sens_hausse, _desc in irr.MODULES_OPTIQUES:
        panel_copy, _ = irr.evidence_optique(panel_copy, colonne, poids, seuil, sens_hausse=sens_hausse)
    panel_copy, _ = irr.evidence_humidite_sol(panel_copy)
    panel_copy, _ = irr.evidence_vwc_nisar(panel_copy)
    panel_score = irr.calculer_score_composite(panel_copy)

    seuils = [0.8, 1.0, 1.2, 1.5, 1.8, 2.2]
    counts = [(panel_score["score_composite"] >= s).sum() for s in seuils]

    # Vérifier la décroissance stricte ou constante
    for i in range(len(counts) - 1):
        assert counts[i] >= counts[i + 1], f"Non-monotonicité du seuil : s={seuils[i]} ({counts[i]}) vs s={seuils[i+1]} ({counts[i+1]})"


def test_coherence_colonnes_csv_besoin():
    """Test #5 : Vérifie que 1_suivi_besoins_plante.csv ne contient aucun NaN dans les colonnes critiques."""
    out_dir = SCRIPT_DIR / "outputs" / "irrigation"
    file_path = out_dir / "1_suivi_besoins_plante.csv"

    if not file_path.exists():
        pytest.skip(f"Fichier CSV non généré : {file_path}")

    df = pd.read_csv(file_path)
    cols_critiques = ["site", "parcel_id", "date", "score_stress", "STATUT_BESOIN", "STATUT_APPORT_EAU", "EFFET_SUR_LE_STRESS"]

    for col in cols_critiques:
        assert col in df.columns, f"Colonne manquante : {col}"
        assert df[col].notna().all(), f"Valeurs nulles trouvées dans la colonne : {col}"


def test_generation_alerte_dynamique():
    """Test #6 : La boîte d'alerte dynamique extrait correctement les dates réelles du DataFrame sans hardcoding."""
    df_dummy = pd.DataFrame({
        "parcel_id": ["makthar_P1"] * 5,
        "date": ["2026-07-20", "2026-07-23", "2026-07-29", "2026-08-02", "2026-08-08"],
        "STATUT_APPORT_EAU": [
            "AUCUN_APPORT_DETECTE",
            "APPORT_EAU_DETECTE (irrigation detectee a J+0)",
            "AUCUN_APPORT_DETECTE",
            "AUCUN_APPORT_DETECTE",
            "AUCUN_APPORT_DETECTE"
        ]
    })

    alerte = run_ana._generer_alerte_coupure_dynamique(df_dummy)
    assert alerte is not None, "L'alerte dynamique aurait dû être générée !"
    assert "23/07/2026" in alerte, "La date de dernière irrigation corroborée 23/07/2026 doit figurer !"
    assert "29/07/2026 au 08/08/2026" in alerte, "La plage de dates sans apport 29/07 au 08/08 doit figurer !"
    assert "11 jours" in alerte, "Le décompte dynamique de 11 jours doit figurer !"


if __name__ == "__main__":
    print("Exécution des tests automatisés du pipeline Irrigation...")
    pytest.main(["-v", __file__])
