#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_alertes_pipeline.py
===================================================================
Pipeline principal d'exécution du Module Autonome d'Alertes Multi-Sources.

Orchestre :
1. La découverte et l'ingestion des 16 fichiers Parquet Clean
2. La construction du panel agrégé multi-sources
3. L'exécution du moteur de détection des 15 alertes (detect_alertes.py)
4. L'exécution du moteur de cascades causales (moteur_cascades.py)
5. La sauvegarde des CSV d'alertes et de la synthèse globale (00_SYNTHESE_ALERTES_GLOBALES.md)

Option --force-refresh
    Supprime tous les caches et résultats précédents avant de relancer
    l'analyse depuis zéro (parquet bruts) :
      - MODULE_ALERTES/output/*.csv et *.md
      - <data-dir>/cache_precip/   (cache météo Open-Meteo partagé)
      - MODULE_ALERTES/__pycache__/
"""

import sys
import os
import shutil
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

MODULE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = MODULE_DIR.parent
PIPELINE_MASTER_DIR = SCRIPTS_DIR / "PIPELINE_MASTER"
IRRIGATION_DIR = SCRIPTS_DIR / "IRRIGATION"
SANTE_DIR = SCRIPTS_DIR / "SANTE_PLANTES"

for p in [str(SCRIPTS_DIR), str(PIPELINE_MASTER_DIR), str(IRRIGATION_DIR), str(SANTE_DIR), str(MODULE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import config_global as cfg
from pipeline_logging import get_logger
from schema_validator import valider_et_nettoyer_panel

logger = get_logger("AWAM.Alertes")

CLEAN_DIR_DEFAULT = cfg.DATA_CLEAN_DIR
OUTPUT_DIR_DEFAULT = cfg.OUTPUT_DIR_ALERTES

import detect_alertes as da
import moteur_cascades as mc
import baselines_communes as bc
try:
    import detect_irrigation_vs_pluie_v3 as irr
except ImportError:
    irr = None


# ===========================================================================
# CACHE CLEARING
# ===========================================================================

def effacer_caches_alertes(output_dir: Path, data_dir: Path) -> None:
    """
    Supprime tous les artefacts mis en cache par le pipeline MODULE_ALERTES :
      - Fichiers CSV et Markdown dans output_dir
      - Cache précipitations Open-Meteo (cache_precip/)
      - Bytecode Python (__pycache__)
    """
    print("\n" + "=" * 80)
    print("  [FORCE-REFRESH] Nettoyage des caches et sorties précédentes (MODULE_ALERTES)...")
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

    # 2. Cache météo Open-Meteo (partagé avec IRRIGATION et SANTE_PLANTES)
    cache_precip = Path(data_dir) / "cache_precip"
    if cache_precip.exists():
        shutil.rmtree(cache_precip)
        print(f"  ✗ Supprimé cache météo : {cache_precip}")
    else:
        print("  (aucun cache météo cache_precip/ trouvé)")

    # 3. __pycache__ du module
    pycache = MODULE_DIR / "__pycache__"
    if pycache.exists():
        shutil.rmtree(pycache)
        print(f"  ✗ Supprimé : {pycache}")
    else:
        print("  (aucun __pycache__ à supprimer)")

    print("  [FORCE-REFRESH] Nettoyage terminé — relance depuis les parquets bruts.")
    print("=" * 80 + "\n")


def executer_pipeline_alertes(clean_dir: Path, output_dir: Path, registre_path: Path = None):
    """Orchestration complète du pipeline d'alertes."""
    print(f"=== Lancement du Module Autonome d'Alertes Multi-Sources ===")
    print(f"Répertoire source clean : {clean_dir}")
    print(f"Répertoire de sortie : {output_dir}")

    # Chargement du registre d'événements terrain central (PIPELINE_MASTER/registre_evenements_terrain.csv)
    df_registre = None
    if registre_path is None:
        registre_path = cfg.REGISTRE_EVENTS_PATH

    if registre_path and registre_path.exists():
        print(f"Fichier de registre d'événements terrain chargé : {registre_path}")
        df_registre = pd.read_csv(registre_path)
    else:
        print(f"⚠️ Fichier de registre d'événements terrain non trouvé à : {registre_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    if not clean_dir.exists():
        print(f"ERREUR : Le répertoire {clean_dir} n'existe pas.")
        return

    # 1. Découverte et chargement des Parquet
    print("\n1. Ingestion et construction du panel multi-sources...")
    if irr is not None:
        dict_files = irr.decouvrir_fichiers(clean_dir)
        dict_sources = {}
        for stype, filepath in dict_files.items():
            df_src = irr.charger_source(filepath)
            dict_sources[stype] = df_src

        df_panel = irr.construire_panel(dict_sources)
        print("\n   [FUSION MULTI-CAPTEURS 10M] Alignement spatial k-d tree sur grille canonique Sentinel-2 10m...")
        df_s2_pixels = bc.fusionner_tous_les_capteurs_sur_grille_pixel_10m(dict_sources)
        print(f"   Grille pixel 10m multi-capteurs construite : {len(df_s2_pixels)} pixels 10m.")
    else:
        print("ATTENTION : Module IRRIGATION introuvable, tentative de chargement direct...")
        df_panel = pd.DataFrame()
        df_s2_pixels = None

    print(f"   Panel parcelle construit : {len(df_panel)} lignes.")

    # 2. Détection des alertes
    parcelles_dir = SCRIPTS_DIR / "parcelles_geojson"
    geojson_all = parcelles_dir / "AWAM_TERRAIN_ALL_ALL_Boundaries_20250501_20260828_v1.0.geojson"
    geojson_sidi = parcelles_dir / "AWAM_TERRAIN_sidi-mechreg_ALL_Boundaries_20250501_20260828_v1.0.geojson"
    geojson_makthar = parcelles_dir / "AWAM_TERRAIN_makthar_ALL_Boundaries_20250501_20260828_v1.0.geojson"
    geojson_paths = [str(geojson_all)] if geojson_all.exists() else [str(geojson_sidi), str(geojson_makthar)]

    res_alertes = da.detecter_toutes_les_alertes(
        df_panel=df_panel,
        df_pixels_s2=df_s2_pixels,
        geojson_paths=geojson_paths,
        registre_taches=df_registre
    )

    df_cat_a = res_alertes["risques_naturels"]
    df_cat_b = res_alertes["comparaison"]
    df_cat_c = res_alertes["coherence"]
    df_pixels_out = res_alertes.get("alertes_pixel_10m", pd.DataFrame())

    # Save Catégories CSVs
    p_cat_a = output_dir / "1_alertes_risques_naturels.csv"
    p_cat_b = output_dir / "2_alertes_comparaison.csv"
    p_cat_c = output_dir / "3_alertes_coherence.csv"
    p_pixels = output_dir / "5_alertes_pixel_10m.csv"

    df_cat_a.to_csv(p_cat_a, index=False, encoding="utf-8")
    df_cat_b.to_csv(p_cat_b, index=False, encoding="utf-8")
    df_cat_c.to_csv(p_cat_c, index=False, encoding="utf-8")
    df_pixels_out.to_csv(p_pixels, index=False, encoding="utf-8")

    print(f"   - Catégorie A (Risques Naturels) : {len(df_cat_a)} alertes -> {p_cat_a.name}")
    print(f"   - Catégorie B (Comparaison)      : {len(df_cat_b)} alertes -> {p_cat_b.name}")
    print(f"   - Catégorie C (Cohérence)        : {len(df_cat_c)} alertes -> {p_cat_c.name}")
    print(f"   - Échelle Pixel 10m (Anomalies)  : {len(df_pixels_out)} pixels -> {p_pixels.name}")

    # 3. Moteur de Cascades Causales
    print("\n3. Exécution du Moteur de Cascades Causales...")
    df_all_alertes = pd.concat([df_cat_a, df_cat_b, df_cat_c], ignore_index=True)
    df_cascades = mc.executer_moteur_cascades(df_all_alertes, df_panel=df_panel)

    p_cascades = output_dir / "4_diagnostics_cascades.csv"
    df_cascades.to_csv(p_cascades, index=False, encoding="utf-8")
    print(f"   - Diagnostics Cascades : {len(df_cascades)} lignes -> {p_cascades.name}")

    # 4. Synthèse Globale Markdown
    print("\n4. Génération de la Synthèse Globale Markdown...")
    p_synth = output_dir / "00_SYNTHESE_ALERTES_GLOBALES.md"
    n_haute = len(df_all_alertes[df_all_alertes["score_confiance"] >= 70.0])
    n_indet = len(df_all_alertes[df_all_alertes["statut"] == "INDETERMINE_DONNEE_MANQUANTE"])

    synth_content = f"""# Synthèse Globale des Alertes Agronomiques Multi-Sources

*Généré automatiquement par `run_alertes_pipeline.py`*

---

## 1. Métriques Clés

- **Nombre Total d'Alertes Déclenchées / Évaluées** : {len(df_all_alertes)}
- **Alertes Confiance Haute (score ≥ 70%)** : {n_haute}
- **Cas INDETERMINE (données manquantes, ex: precip_mm)** : {n_indet}
- **Chaînes causales complexes identifiées** : {len(df_cascades[df_cascades["statut_cascade"] != "ISOLEE"])}

---

## 2. Répartition par Catégorie

| Catégorie | Fichier CSV | Nombre d'Alertes |
|---|---|---:|
| **Catégorie A : Risques Naturels** | `1_alertes_risques_naturels.csv` | {len(df_cat_a)} |
| **Catégorie B : Comparaison** | `2_alertes_comparaison.csv` | {len(df_cat_b)} |
| **Catégorie C : Cohérence Registre** | `3_alertes_coherence.csv` | {len(df_cat_c)} |
| **Diagnostics Cascades** | `4_diagnostics_cascades.csv` | {len(df_cascades)} |

---

## 3. Remarques Qualité & Gardes-Fous

- **Masquage Sol Nu** (`fCover < 0.05`) : les alertes de stress foliaire (#1, #2, #3) sont neutralisées en présence de sol nu dominant.
- **Garde-fou `INDETERMINE`** : Les alertes dépendantes de la pluie (#5, #6, #8) basculent en `INDETERMINE_DONNEE_MANQUANTE` si `precip_mm` est absent du fichier ERA5.
- **Facteur d'Échelle Spatial** : appliqué aux capteurs à résolution métrique supérieure (MODIS 1km, NISAR 200m).
"""
    with open(p_synth, "w", encoding="utf-8") as f:
        f.write(synth_content)

    print(f"   Synthèse enregistrée dans {p_synth.name}")
    print("\n=== Pipeline exécuté avec succès ! ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Alertes Pipeline")
    parser.add_argument("--clean-dir", type=Path, default=CLEAN_DIR_DEFAULT, help="Dossier des parquets clean")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR_DEFAULT, help="Dossier de sortie CSV")
    parser.add_argument("--registre", type=Path, default=cfg.REGISTRE_EVENTS_PATH, help="Chemin du CSV de registre d'événements terrain (default: PIPELINE_MASTER/registre_evenements_terrain.csv)")
    parser.add_argument("--no-purge", action="store_true", help="Désactive la purge automatique des anciennes sorties")
    parser.add_argument("--force-refresh", action="store_true", help="Force la purge complète des caches et sorties (comportement par défaut)")
    args = parser.parse_args()

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Auto-purge par défaut (sauf si --no-purge)
    if not args.no_purge:
        effacer_caches_alertes(output_dir, args.clean_dir)

    executer_pipeline_alertes(args.clean_dir, output_dir, args.registre)
