#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_health_analysis.py
===================================================================
Orchestrateur principal du module Santé des Plantes AWAM.

Exécute la chaîne complète :
1. Découverte et chargement du panel multi-capteurs (S1, S2, MODIS, Landsat, ECOSTRESS, NISAR, ERA5)
2. Estimation du LAI (Loi de Beer-Lambert inversée + fallbacks)
3. Calcul des 7 scores composites + 2 ajouts méthodologiques (Sol & Température)
4. Agrégation en Indice de Santé AWAM (0-100) avec attribution des pastilles 🟢🟡🔴
5. Génération des rapports CSV et du document de synthèse `00_SYNTHESE_SANTE_PARCELLES.md`

Option --force-refresh
    Supprime tous les caches et résultats précédents avant de relancer
    l'analyse depuis zéro (parquet bruts) :
      - SANTE_PLANTES/output/*.csv et *.md
      - <data-dir>/cache_precip/   (cache météo Open-Meteo partagé)
      - SANTE_PLANTES/__pycache__/
    L'option --from-cache est ignorée si --force-refresh est actif.

Usage:
    python run_health_analysis.py --data-dir ../outputs/pixel_indices_database/clean
    python run_health_analysis.py --dry-run
    python run_health_analysis.py --force-refresh
"""

import sys
import time
import argparse
import pickle
import shutil
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

# Import des modules de configuration, logging et validation unifiés
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent
PIPELINE_MASTER_DIR = SCRIPTS_DIR / "PIPELINE_MASTER"
IRRIGATION_DIR = SCRIPTS_DIR / "IRRIGATION"

for p in [str(SCRIPTS_DIR), str(PIPELINE_MASTER_DIR), str(IRRIGATION_DIR), str(SCRIPT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import config_global as cfg
from pipeline_logging import get_logger
from schema_validator import valider_et_nettoyer_panel

logger = get_logger("AWAM.Health")

try:
    import detect_irrigation_vs_pluie_v3 as irr
except ImportError:
    irr = None

from compute_health_scores import calculer_tous_les_scores_sante
from compute_awam_index import calculer_indice_sante_awam


# ===========================================================================
# CACHE CLEARING
# ===========================================================================

def effacer_caches_sante(output_dir: Path, data_dir: str, cache_panel_path: str = None) -> None:
    """
    Supprime tous les artefacts mis en cache par le pipeline SANTE_PLANTES :
      - Fichiers CSV et Markdown dans output_dir
      - Cache panel .pkl (si spécifié via --cache-panel)
      - Cache précipitations Open-Meteo (cache_precip/)
      - Bytecode Python (__pycache__)
    """
    print("\n" + "=" * 80)
    print("  [FORCE-REFRESH] Nettoyage des caches et sorties précédentes (SANTE_PLANTES)...")
    print("=" * 80)

    # 1. Outputs CSV / Markdown
    n_out = 0
    for ext in ("*.csv", "*.md"):
        for f in output_dir.glob(ext):
            f.unlink()
            print(f"  ✗ Supprimé : {f.name}")
            n_out += 1
    if n_out == 0:
        print("  (aucun fichier de sortie à supprimer)")

    # 2. Cache panel .pkl (si l'utilisateur avait passé --cache-panel)
    if cache_panel_path:
        pkl = Path(cache_panel_path)
        if pkl.exists():
            pkl.unlink()
            print(f"  ✗ Supprimé cache panel : {pkl}")
        else:
            print(f"  (cache panel {pkl} introuvable)")

    # 3. Cache météo Open-Meteo
    cache_precip = Path(data_dir) / "cache_precip"
    if cache_precip.exists():
        shutil.rmtree(cache_precip)
        print(f"  ✗ Supprimé cache météo : {cache_precip}")
    else:
        print("  (aucun cache météo cache_precip/ trouvé)")

    # 4. __pycache__ du module
    pycache = SCRIPT_DIR / "__pycache__"
    if pycache.exists():
        shutil.rmtree(pycache)
        print(f"  ✗ Supprimé : {pycache}")
    else:
        print("  (aucun __pycache__ à supprimer)")

    print("  [FORCE-REFRESH] Nettoyage terminé — relance depuis les parquets bruts.")
    print("=" * 80 + "\n")


def charger_registre_evenements(output_dir: Path = None) -> pd.DataFrame:
    """
    Charge le registre officiel central des événements terrain (CSV).
    Fichier attendu : PIPELINE_MASTER/registre_evenements_terrain.csv
    """
    script_dir = Path(__file__).resolve().parent
    registre_path = script_dir.parent / "PIPELINE_MASTER" / "registre_evenements_terrain.csv"
    if not registre_path.exists():
        registre_path = script_dir.parent / "registre_evenements_terrain.csv"

    if registre_path.exists():
        df = pd.read_csv(registre_path, dtype=str, encoding="utf-8")
        print(f"  ✓ Registre d'événements terrain chargé : {len(df)} événements depuis {registre_path.name}")
        return df
    else:
        print(f"  ⚠ Aucun registre d'événements terrain trouvé ({registre_path.name}). Synthèse sans annotations événementielles.")
        return pd.DataFrame()


def construire_synthese_sante(df_health, df_evenements=None):
    """
    Génère un rapport de synthèse lisible au format Markdown pour toutes les parcelles.
    Intègre les annotations du registre officiel d'événements terrain si disponible.
    """
    lignes = [
        "# 🌿 Synthèse de Santé des Plantes AWAM — Suivi Multi-Capteurs",
        f"\n*Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "\nCe document présente le diagnostic complet de santé des cultures pour les sites de **Makthar** et **Sidi Mechreg**.",
        "Il combine 7 scores composites (Vigueur, Chlorophylle, Stress Hydrique, Canopée, Phénologie, Anomalies, Risque Maladies) "
        "et 2 évaluations complémentaires (Qualité du Sol & Stress Température) pour produire l'**Indice de Santé AWAM (0-100)**.\n"
    ]

    if df_evenements is None:
        df_evenements = pd.DataFrame()

    if df_health.empty or "parcel_id" not in df_health.columns:
        lignes.append("\n**Aucune donnée de santé disponible.**")
        return "\n".join(lignes)

    parcelles = sorted(df_health["parcel_id"].unique())

    for pid in parcelles:
        sous = df_health[df_health["parcel_id"] == pid].sort_values("date")
        if sous.empty:
            continue

        culture = sous["culture"].iloc[0] if "culture" in sous.columns and sous["culture"].notna().any() else "Inconnue"
        site = sous["site"].iloc[0] if "site" in sous.columns and sous["site"].notna().any() else "Inconnu"

        # Dernier état disponible
        derniere_row = sous.iloc[-1]
        score_recent = derniere_row.get("score_sante_awam", np.nan)
        pastille = derniere_row.get("pastille_sante", "⚪ NON_EVALUABLE")
        confiance = derniere_row.get("confiance_signal", "BASSE")
        mode = derniere_row.get("mode_confiance", "SUIVI_BRUT")

        lignes.append(f"\n## 📌 Parcelle : {pid} — *{culture}* ({site})")
        lignes.append(f"- **Indice de Santé AWAM Actuel** : **{score_recent} / 100** -> {pastille}")
        lignes.append(f"- **Niveau de Confiance** : **{confiance}** (Mode: `{mode}`)")
        lignes.append(f"- **Période observée** : {sous['date'].min().date()} au {sous['date'].max().date()} ({len(sous)} observations)")

        # Tableau récapitulatif des composantes moyennes sur les 30 derniers jours
        d_max = sous["date"].max()
        sous_30j = sous[sous["date"] >= d_max - pd.Timedelta(days=30)]

        lignes.append("\n### 📊 Composantes de Santé (Moyennes 30 derniers jours)")
        lignes.append("| Score Composite | Valeur Moyenne | Évaluation |")
        lignes.append("| :--- | ---: | :--- |")

        cols_composites = [
            ("score_vigueur_vegetative", "Vigueur Végétative (NDVI, SAVI, EVI, VARI)"),
            ("score_chlorophylle", "Chlorophylle & Nutrition (NDRE, CI_RedEdge)"),
            ("score_stress_hydrique", "Statut Hydrique (NDMI, CWSI, SMI, NISAR)"),
            ("score_couverture_canopee", "Couverture Canopée (fCover, LAI)"),
            ("score_suivi_phenologique", "Conformité Phénologique (Stade attendu vs observé)"),
            ("score_detection_anomalie", "Absence d'Anomalies (Stabilité temporelle)"),
            ("score_risque_maladie", "Pression Pathogène / Risque Maladie"),
            ("score_qualite_sol", "Qualité du Sol (pH, MO%, Salinité, Nitrates)"),
            ("score_temperature_stress", "Résilience Température (Gel / Canicule ERA5)"),
        ]

        for col_name, col_label in cols_composites:
            if col_name in sous_30j.columns:
                m_val = sous_30j[col_name].mean()
                if not pd.isna(m_val):
                    eval_str = "🟢 Bon" if m_val >= 70 else ("🟡 Modéré" if m_val >= 50 else "🔴 Faible/Alerte")
                    lignes.append(f"| {col_label} | {m_val:.1f} / 100 | {eval_str} |")
                else:
                    lignes.append(f"| {col_label} | n/d | ⚪ Données insuffisantes |")

        # Analyse du fCover et LAI
        if "fCover" in sous_30j.columns and sous_30j["fCover"].notna().any():
            fc_m = sous_30j["fCover"].mean()
            lai_m = sous_30j["LAI"].mean() if "LAI" in sous_30j.columns else np.nan
            lignes.append(f"\n- **fCover Moyen** : {fc_m:.2f} ({fc_m*100:.1f}% de couverture du sol)")
            if not pd.isna(lai_m):
                lignes.append(f"- **LAI Estimé (Beer-Lambert)** : {lai_m:.2f} m²/m²")

        # Injection dynamique des événements terrain depuis le registre CSV officiel
        if not df_evenements.empty and "parcel_id" in df_evenements.columns:
            evts_parcelle = df_evenements[df_evenements["parcel_id"] == pid]
            for _, evt in evts_parcelle.iterrows():
                cat = str(evt.get("categorie_evenement", ""))
                grav = str(evt.get("gravite", ""))
                nom = str(evt.get("nom_evenement", ""))
                date_obs = str(evt.get("date_observation_terrain", ""))
                impact = str(evt.get("impact_agronomique", ""))
                pathogene = str(evt.get("pathogene_identifie", ""))
                action = str(evt.get("action_terrain", ""))
                statut = str(evt.get("statut", ""))
                evt_id = str(evt.get("evt_id", ""))

                if cat == "PHYTOSANITAIRE":
                    icon = "🚨" if grav == "CRITIQUE" else "⚠️"
                    lignes.append(f"\n> {icon} **Événement Phytosanitaire [{evt_id}]** ({date_obs}) : "
                                  f"**{nom}** — Pathogène : *{pathogene}*. "
                                  f"Impact : {impact}. Action : {action}. Statut : `{statut}`.")
                elif cat == "STRESS_HYDRIQUE_SEVERE":
                    lignes.append(f"\n> 🚨 **Événement Hydrique [{evt_id}]** ({date_obs}) : "
                                  f"**{nom}** — Impact : {impact}. Statut : `{statut}`.")
                elif cat == "IRRIGATION" and grav != "INFORMATION":
                    lignes.append(f"\n> ℹ️ **Événement Irrigation [{evt_id}]** ({date_obs}) : "
                                  f"**{nom}** — Statut : `{statut}`.")


        # Recommandations et avertissements
        if confiance == "BASSE":
            lignes.append("\n> ⚠️ **Avertissement de résolution** : Le fCover moyen de cette parcelle est très faible (<5%). "
                          "Les valeurs spectrales sont dominées par la réflectance du sol nu. Les variations du score de vigueur "
                          "reflètent l'humidité du sol plutôt qu'un réel changement de masse foliaire.")
        elif pastille.startswith("🔴"):
            lignes.append("\n> 🚨 **Alerte Santé** : Un score critique a été détecté durant les 30 derniers jours. "
                          "Consulter le détail des anomalies pour identifier s'il s'agit d'un choc thermique ou d'un stress hydrique sévère.")

    return "\n".join(lignes)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=str(SCRIPT_DIR.parent / "outputs" / "pixel_indices_database" / "clean"),
                    help="Dossier contenant les .parquet nettoyés")
    ap.add_argument("--output-dir", "-o", default=str(SCRIPT_DIR / "output"),
                    help="Dossier de sortie (défaut: SANTE_PLANTES/output)")
    ap.add_argument("--dry-run", action="store_true", help="Exécute l'analyse sans écrire de fichier")
    ap.add_argument("--no-api", action="store_true", help="Désactive Open-Meteo")
    ap.add_argument("--precip", default=None, help="CSV de précipitation")
    ap.add_argument("--cache-panel", default=None, help="Sauvegarde du panel calculé (.pkl)")
    ap.add_argument("--from-cache", default=None, help="Charge un panel pré-calculé (.pkl)")
    ap.add_argument("--no-purge", action="store_true", help="Désactive la purge automatique des anciennes sorties")
    ap.add_argument("--force-refresh", action="store_true", help="Force la purge complète des caches et sorties (comportement par défaut)")
    args = ap.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Auto-purge par défaut (sauf si --no-purge ou chargement explicite depuis --from-cache)
    if not args.no_purge and not args.from_cache:
        effacer_caches_sante(output_dir, args.data_dir, args.cache_panel)

    print("=" * 80)
    print(" 🌿 MODULE DE SANTÉ DES PLANTES AWAM — AGGREGATION & DIAGNOSTIC v1")
    print("=" * 80)

    # 1. Chargement du panel
    if args.from_cache:
        print(f"\n[CACHE] Chargement du panel depuis {args.from_cache}...")
        with open(args.from_cache, "rb") as f:
            panel = pickle.load(f)
            if isinstance(panel, tuple):
                panel = panel[0]
        print(f"  ✓ {len(panel)} lignes chargées, {panel['parcel_id'].nunique()} parcelles.")
    else:
        if irr is None:
            raise SystemExit("Impossible d'importer detect_irrigation_vs_pluie_v3.py. Assurez-vous qu'il est présent dans scripts/IRRIGATION/.")
        
        fichiers = irr.decouvrir_fichiers(args.data_dir)
        sources_brutes = {source: irr.charger_source(paths) for source, paths in fichiers.items()}
        print("\n[PANEL] Construction du panel multi-capteurs...")
        panel = irr.construire_panel(sources_brutes)
        print(f"  ✓ {len(panel)} lignes (parcelle x date), {panel['parcel_id'].nunique()} parcelles.")

        if args.cache_panel:
            with open(args.cache_panel, "wb") as f:
                pickle.dump(panel, f)
            print(f"  ✓ Panel mis en cache -> {args.cache_panel}")

    # 2. Validation du schéma & sanitization des bornes
    panel = valider_et_nettoyer_panel(panel)

    # 3. Calcul des scores composites et ajouts méthodologiques
    print("\n[SCORES] Calcul des 7 scores composites + Sol & Température...")
    t0 = time.perf_counter()
    df_health = calculer_tous_les_scores_sante(panel)

    # 3. Agrégation de l'Indice AWAM
    print("[AWAM] Agrégation de l'Indice de Santé AWAM (0-100)...")
    df_health = calculer_indice_sante_awam(df_health)
    t1 = time.perf_counter()
    print(f"  ✓ Calcul terminé en {t1 - t0:.2f} s.")

    # Validation dry-run
    if args.dry_run:
        print("\n[DRY-RUN] Aperçu des résultats :")
        cols_summary = ["parcel_id", "date", "fCover", "LAI", "score_sante_awam", "pastille_sante", "confiance_signal"]
        print(df_health[cols_summary].dropna(subset=["score_sante_awam"]).head(10).to_string())
        print("\n[DRY-RUN] Succès — aucun fichier écrit.")
        return

    # 4. Sauvegarde des résultats CSV
    out_scores_csv = output_dir / "1_scores_sante_composites.csv"
    out_alertes_csv = output_dir / "2_alertes_anomalies_sante.csv"
    out_pheno_csv = output_dir / "3_suivi_phenologique_sante.csv"
    out_synthese_md = output_dir / "00_SYNTHESE_SANTE_PARCELLES.md"

    # Export 1: Scores composites & AWAM
    df_health.to_csv(out_scores_csv, index=False)

    # Export 2: Alertes anomalies & dégradations de santé
    # Inclut les départs sous-scores (< 80) et les dégradations globales de santé AWAM (< 70, pastille ATTENTION/CRITIQUE)
    df_alertes = df_health[
        (df_health["score_detection_anomalie"] < 80) |
        (df_health["score_risque_maladie"] < 80) |
        (df_health["score_temperature_stress"] < 80) |
        (df_health["score_sante_awam"] < 70)
    ].copy()
    df_alertes.to_csv(out_alertes_csv, index=False)

    # Export 3: Suivi phénologique
    cols_pheno = ["site", "parcel_id", "culture", "date", "NDVI", "NDRE", "fCover", "stade_phenologique_attendu", "score_suivi_phenologique"]
    cols_pheno_present = [c for c in cols_pheno if c in df_health.columns]
    df_health[cols_pheno_present].to_csv(out_pheno_csv, index=False)

    # 5. Chargement du registre officiel d'événements terrain
    print("\n[ÉVÉNEMENTS] Chargement du registre d'événements terrain...")
    df_evenements = charger_registre_evenements(output_dir)

    # 6. Génération du document de synthèse Markdown
    print("\n[SYNTHÈSE] Génération du document Markdown...")
    synthese_md = construire_synthese_sante(df_health, df_evenements)
    out_synthese_md.write_text(synthese_md, encoding="utf-8")

    print(f"\n{'=' * 80}")
    print(f" RÉSULTATS ÉCRITS DANS : {output_dir}")
    print(f"{'=' * 80}")
    print(f"  - {out_synthese_md.name}")
    print(f"  - {out_scores_csv.name} ({len(df_health)} lignes)")
    print(f"  - {out_alertes_csv.name} ({len(df_alertes)} alertes)")
    print(f"  - {out_pheno_csv.name} ({len(df_health)} lignes)")


if __name__ == "__main__":
    main()
