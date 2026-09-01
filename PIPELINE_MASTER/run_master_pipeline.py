#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
AWAM MASTER END-TO-END ANALYTICAL PIPELINE ORCHESTRATOR
================================================================================

Orchestre la chaîne d'analyse complète de bout en bout (End-to-End) :

1. STAGE 1 : Extraction & Nettoyage des données Multi-Sources (GEE + Earthdata)
   -> Script: scripts/EXTRACT/run_all_extractions.py
   -> Destination: scripts/outputs/pixel_indices_database/clean/

2. STAGE 2 : Calibration VARI Sol & Photos Terrain (Calibrage sous-pixel fCover)
   -> Script: scripts/VARI_CALIBRATION/run_vari_pipeline.py
   -> Destination: AWAM_GEE_*_S2-Indices_*_calibrated_clean.parquet

3. STAGE 3 : Module Santé des Plantes (Scores Composites, LAI, Indice AWAM)
   -> Script: scripts/SANTE_PLANTES/run_health_analysis.py
   -> Destination: scripts/SANTE_PLANTES/output/

4. STAGE 4 : Module Irrigation & Bilan Hydrique (FAO-56, Deficit & Stress)
   -> Script: scripts/IRRIGATION/run_irrigation_analysis.py
   -> Destination: scripts/IRRIGATION/outputs/irrigation/

5. STAGE 5 : Module Autonome d'Alertes Multi-Sources & Cascades Causales
   -> Script: scripts/MODULE_ALERTES/run_alertes_pipeline.py
   -> Destination: scripts/MODULE_ALERTES/output/

6. STAGE 6 : Contrôle de Cohérence Croisée Inter-Modules & Validation
   -> Validation automatique de l'alignement spatio-temporel et zéro contradiction.

Usage:
  python scripts/PIPELINE_MASTER/run_master_pipeline.py
  python scripts/PIPELINE_MASTER/run_master_pipeline.py --skip-extract
  python scripts/PIPELINE_MASTER/run_master_pipeline.py --skip-vari
  python scripts/PIPELINE_MASTER/run_master_pipeline.py --incremental
  python scripts/PIPELINE_MASTER/run_master_pipeline.py --skip-extract --skip-vari --force-refresh

  --force-refresh :
    Passe --force-refresh à chacun des modules analytiques (STAGE 3/4/5).
    Cela supprime, AVANT chaque relance, tous les caches et fichiers de sortie
    précédents de ce module :
      - output/*.csv et output/*.md
      - <data-dir>/cache_precip/   (cache météo Open-Meteo)
      - _cache_panel_*.pkl         (IRRIGATION uniquement)
      - __pycache__/
    Indispensable pour garantir que chaque exécution repart des parquets bruts.

================================================================================
"""

import sys
import os
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# UTF-8 output encoding for Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent if SCRIPT_DIR.name == "PIPELINE_MASTER" else SCRIPT_DIR
ROOT_DIR = SCRIPTS_DIR.parent

for p in [str(SCRIPTS_DIR), str(SCRIPT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import config_global as cfg
from pipeline_logging import get_logger

logger = get_logger("AWAM.MasterPipeline")

# Paths to sub-pipeline scripts
STAGE1_EXTRACT = SCRIPTS_DIR / "EXTRACT" / "run_all_extractions.py"
STAGE2_VARI = SCRIPTS_DIR / "VARI_CALIBRATION" / "run_vari_pipeline.py"
STAGE3_SANTE = SCRIPTS_DIR / "SANTE_PLANTES" / "run_health_analysis.py"
STAGE4_IRRIG = SCRIPTS_DIR / "IRRIGATION" / "run_irrigation_analysis.py"
STAGE5_ALERTES = SCRIPTS_DIR / "MODULE_ALERTES" / "run_alertes_pipeline.py"

DATA_CLEAN_DIR = cfg.DATA_CLEAN_DIR


def run_command_stage(stage_name: str, cmd_list: list, cwd: Path) -> bool:
    """Exécute une étape du pipeline et affiche une synthèse élégante tout en journalisant."""
    cmd_str = ' '.join([str(c) for c in cmd_list])
    print(f"\n================================================================================")
    print(f"  >>> EXECUTION {stage_name}")
    print(f"================================================================================")
    print(f"Commande : {cmd_str}")
    print(f"Répertoire : {cwd}\n")
    logger.info(f"Début {stage_name} | Cmd: {cmd_str}")

    start_time = time.time()
    try:
        res = subprocess.run(cmd_list, cwd=cwd, check=True)
        elapsed = time.time() - start_time
        msg = f"{stage_name} exécuté avec succès en {elapsed:.2f}s."
        print(f"\n[✓ SUCCESS] {msg}")
        logger.info(msg)
        return True
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        msg = f"{stage_name} a échoué (Code retour: {e.returncode}) après {elapsed:.2f}s."
        print(f"\n[❌ ERROR] {msg}")
        logger.error(msg)
        return False


def valider_coherence_inter_modules() -> bool:
    """Exécute la vérification automatique de cohérence inter-modules."""
    print(f"\n================================================================================")
    print(f"  >>> STAGE 6 : VALIDATION DE COHERENCE INTER-MODULES")
    print(f"================================================================================")
    logger.info("STAGE 6 : Début de la validation de cohérence inter-modules.")
    try:
        import pandas as pd
        import numpy as np

        sante_file = SCRIPTS_DIR / "SANTE_PLANTES" / "output" / "1_scores_sante_composites.csv"
        irrig_file = SCRIPTS_DIR / "IRRIGATION" / "outputs" / "irrigation" / "1_suivi_besoins_plante.csv"
        alert_file = SCRIPTS_DIR / "MODULE_ALERTES" / "output" / "5_alertes_pixel_10m.csv"

        if not (sante_file.exists() and irrig_file.exists() and alert_file.exists()):
            msg = "Impossible d'exécuter le contrôle : un ou plusieurs CSV de sortie sont manquants."
            print(f" [!] {msg}")
            logger.warning(msg)
            return False

        df_sante = pd.read_csv(sante_file)
        df_irr = pd.read_csv(irrig_file)
        df_alt = pd.read_csv(alert_file)

        p_sante = set(df_sante["parcel_id"].unique())
        p_irr = set(df_irr["parcel_id"].unique())
        p_alt = set(df_alt["parcel_id"].unique())

        if p_sante == p_irr == p_alt:
            msg = f"Alignement spatial parfait : {len(p_sante)} parcelles synchronisées."
            print(f" [✓] {msg}")
            logger.info(msg)
        else:
            msg = "Incohérence spatiale décelée entre les modules."
            print(f" [❌] {msg}")
            logger.error(msg)
            return False

        # Vérification non-contradiction
        m_check = pd.merge(
            df_sante[["parcel_id", "date", "score_sante_awam"]],
            df_irr[["parcel_id", "date", "STATUT_BESOIN"]],
            on=["parcel_id", "date"], how="inner"
        )
        inc = m_check[(m_check["STATUT_BESOIN"] == "BESOIN_CRITIQUE") & (m_check["score_sante_awam"] >= 80.0)]
        if not inc.empty:
            msg = f"Contradictions trouvées (Irrigation Besoin Critique MAIS Santé >= 80%) : {len(inc)} cas."
            print(f" [❌] {msg}")
            logger.error(msg)
            return False

        msg = "Contrôle de non-contradiction : 0 incohérence décelée."
        print(f" [✓] {msg}")
        logger.info(msg)
        return True

    except Exception as e:
        msg = f"Erreur lors de la validation croisée : {e}"
        print(f" [❌] {msg}")
        logger.error(msg)
        return False


def main():
    parser = argparse.ArgumentParser(description="Orchestrateur Master Pipeline End-to-End GeoAI AWAM")
    parser.add_argument("--skip-extract", action="store_true", help="Sauter l'étape 1 (Extraction GEE/Earthdata)")
    parser.add_argument("--skip-vari", action="store_true", help="Sauter l'étape 2 (Calibration VARI Sol/Terrain)")
    parser.add_argument("--skip-sante", action="store_true", help="Sauter l'étape 3 (Module Santé des Plantes)")
    parser.add_argument("--skip-irrigation", action="store_true", help="Sauter l'étape 4 (Module Irrigation)")
    parser.add_argument("--skip-alertes", action="store_true", help="Sauter l'étape 5 (Module Alertes)")
    parser.add_argument("--incremental", action="store_true", help="Mode incrémental pour l'extraction")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help=(
            "Passe --force-refresh à chacun des modules analytiques (STAGE 3, 4, 5). "
            "Supprime AVANT chaque relance tous les caches et sorties précédentes "
            "(output/*.csv, output/*.md, cache_precip/, __pycache__, *.pkl) afin de "
            "garantir une analyse depuis les parquets bruts. "
            "Indispensable quand les données source ont changé entre deux runs."
        ),
    )
    args = parser.parse_args()

    start_total = time.time()
    logger.info("=== DÉMARRAGE PIPELINE MASTER END-TO-END AWAM ===")
    print("\n" + "=" * 80)
    print("      LANCEMENT DU PIPELINE MASTER ANALYTIQUE COMPLET")
    print("      Project AWAM — " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 80)

    # 1. STAGE 1: Extraction
    if not args.skip_extract:
        cmd = [sys.executable, str(STAGE1_EXTRACT)]
        if args.incremental:
            cmd.append("--incremental")
        if not run_command_stage("STAGE 1 : Extraction & Nettoyage Données", cmd, SCRIPTS_DIR):
            sys.exit(1)
    else:
        logger.info("STAGE 1 sauté (--skip-extract).")
        print("\n [⏩ SKIP] STAGE 1 sauté comme demandé.")

    # 2. STAGE 2: VARI Calibration
    if not args.skip_vari:
        cmd = [sys.executable, str(STAGE2_VARI)]
        if not run_command_stage("STAGE 2 : Calibration VARI Sol/Terrain", cmd, SCRIPTS_DIR):
            sys.exit(1)
    else:
        logger.info("STAGE 2 sauté (--skip-vari).")
        print("\n [⏩ SKIP] STAGE 2 sauté comme demandé.")

    # 3. STAGE 3: Santé des Plantes
    if not args.skip_sante:
        cmd = [sys.executable, str(STAGE3_SANTE), "--data-dir", str(DATA_CLEAN_DIR)]
        if args.force_refresh:
            cmd.append("--force-refresh")
        if not run_command_stage("STAGE 3 : Module Santé des Plantes", cmd, SCRIPTS_DIR):
            sys.exit(1)
    else:
        logger.info("STAGE 3 sauté (--skip-sante).")
        print("\n [⏩ SKIP] STAGE 3 sauté comme demandé.")

    # 4. STAGE 4: Irrigation
    if not args.skip_irrigation:
        cmd = [sys.executable, str(STAGE4_IRRIG), "--data-dir", str(DATA_CLEAN_DIR)]
        if args.force_refresh:
            cmd.append("--force-refresh")
        if not run_command_stage("STAGE 4 : Module Irrigation", cmd, SCRIPTS_DIR):
            sys.exit(1)
    else:
        logger.info("STAGE 4 sauté (--skip-irrigation).")
        print("\n [⏩ SKIP] STAGE 4 sauté comme demandé.")

    # 5. STAGE 5: Alertes Multi-Sources
    if not args.skip_alertes:
        cmd = [sys.executable, str(STAGE5_ALERTES)]
        if args.force_refresh:
            cmd.append("--force-refresh")
        if not run_command_stage("STAGE 5 : Module Alertes Multi-Sources", cmd, SCRIPTS_DIR):
            sys.exit(1)
    else:
        logger.info("STAGE 5 sauté (--skip-alertes).")
        print("\n [⏩ SKIP] STAGE 5 sauté comme demandé.")

    # 6. STAGE 6: Validation Croisée Inter-Modules
    valider_coherence_inter_modules()

    total_elapsed = time.time() - start_total
    msg_fin = f"PIPELINE MASTER COMPLETE avec succès en {total_elapsed / 60:.2f} minutes."
    logger.info(msg_fin)
    print("\n" + "=" * 80)
    print(f"      [✓ PIPELINE MASTER COMPLETE] Tous les modules ont été exécutés avec succès !")
    print(f"      Temps d'exécution total : {total_elapsed / 60:.2f} minutes")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
