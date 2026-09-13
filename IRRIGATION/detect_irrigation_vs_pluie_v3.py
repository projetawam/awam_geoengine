#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_irrigation_vs_pluie_v3.py
===================================================================
V3 : passage d'un détecteur MONO-CAPTEUR (Sentinel-1 SAR seul) à un
détecteur MULTI-CAPTEUR, conformément à la Recommandation §6.3 du
rapport `rapport_analyse_irrigation_vs_pluie.md` :

    "Pour les parcelles en goutte-à-goutte comme Kemel 1 et Yahia 4,
    la détection doit s'appuyer sur la complémentarité des données...
    NDMI/NDWI (Sentinel-2), LST (ECOSTRESS/Landsat/MODIS), fCover/NDVI."

POURQUOI CE CHANGEMENT (constats faits sur VOS fichiers réels) :
------------------------------------------------------------------
1. BUG BLOQUANT du v2 : chemins Windows codés en dur
   (`C:\\Users\\Dell\\...`) et noms de fichiers qui pointaient sur
   `*_S1-SAR_*.parquet`, un fichier que vous n'avez PAS fourni cette
   fois-ci (vous avez donné ERA5-Meteo + Landsat-Thermal, pas le SAR).
   Le v2 s'arrêtait donc immédiatement avec `SystemExit`. -> corrigé
   par une DÉCOUVERTE AUTOMATIQUE des fichiers disponibles (voir §1),
   quel que soit le sous-ensemble de capteurs fourni, et avec un
   chemin par défaut relatif (plus de chemin Windows en dur).

2. `precip_mm` ATTENDU MAIS ABSENT : la documentation
   (`documentation_pipeline_extraction_spatial_v2.md`, §3.1 et §7.2)
   indique que `ERA5-Meteo` contient `Tmin_C, Tmax_C, precip_mm,
   GDD_cumul, frost_risk`. Or vos deux fichiers ERA5-Meteo fournis
   NE CONTIENNENT PAS `precip_mm` (seulement Tmin_C, Tmax_C,
   GDD_cumul, frost_risk). C'est très probablement un bug dans
   `clean_extracted_data.py` ou dans l'export GEE de CE run précis
   -> À VÉRIFIER CÔTÉ PIPELINE D'EXTRACTION. En attendant, ce script :
     a) utilise `precip_mm` directement s'il est présent (le nouveau
        cas normal, 0 appel réseau nécessaire, contrairement au v2
        qui appelait systématiquement Open-Meteo) ;
     b) sinon retombe sur l'API Open-Meteo (comme le v2) ;
     c) sinon marque INDETERMINE (jamais 0 mm par défaut, cf. le
        bug corrigé en v2 -- ce garde-fou est conservé).

3. LE SAR N'EST PLUS LA SEULE PREUVE. Le rapport a montré que sur
   Kemel/Yahia (goutte-à-goutte sur sol nu), le radar ne réagit pas :
   même désagrégé pixel par pixel, l'écart reste sous le seuil
   (2.4% et 0.6% des pixels, Δσ⁰max +1.77/+2.33 dB). Ce script
   combine maintenant PLUSIEURS preuves indépendantes, chacune
   pondérée par sa fiabilité physique pour le contexte de la parcelle
   (culture, couvert végétal) :
     - Radar SAR S1 (si fichier fourni) — pics pixel, comme le v2.
     - Rétrodiffusion NISAR (si fournie) — même logique pixel.
     - Humidité de surface directe NISAR SME2 (si fournie) — preuve
       la plus directe si disponible (mesure volumétrique en m³/m³).
     - Indices optiques SWIR Sentinel-2 NDMI/NDWI (si fournis) —
       sensibles à l'humidité de surface, recommandation #1 du rapport.
     - Rafraîchissement évaporatif LST (Landsat-Thermal, ECOSTRESS,
       MODIS -- CE QUE VOUS AVEZ FOURNI CETTE FOIS) : proxy CWSI
       ΔTs = LST - Tmax_C air, dont la CHUTE (le sol/couvert se
       rapproche de la température de l'air) est le signe attendu
       d'un apport d'eau (recommandation #2 du rapport).
     - Croissance NDVI/fCover a posteriori (corroboration différée,
       pas un déclencheur à elle seule -- la végétation réagit avec
       un délai de plusieurs jours à semaines).
   Le score composite s'ADAPTE au contexte : le poids du SAR est
   automatiquement réduit sur les parcelles à faible couvert
   (`culture` contenant "Sol nu", ou NDVI médian < 0.2 utilisé comme
   proxy de fCover quand fCover n'est pas disponible), conformément
   à la conclusion physique du rapport (§4.2 : empreinte goutte-à-
   goutte 2-5% d'un pixel de 100 m², donc de tout pixel à peu près).

4. AUTO-VALIDATION SUR VOS DONNÉES RÉELLES (calcul fait pendant
   l'écriture de ce script, sur vos deux fichiers Landsat-Thermal +
   ERA5-Meteo de sidi_mechreg) :
   Passage Landsat le plus proche de l'installation (8-11/06/2026) :
   2026-06-12 (J+1 à J+4 après la fin de pose). ΔTs = LST - Tmax :
     - Kemel_1 : 12.10°C (04/06, avant) -> 13.09°C (12/06, après) :
       AUCUN refroidissement, ΔTs augmente même légèrement.
     - Kemel_2 : 13.13°C -> 12.97°C : quasi stable (-0.16°C).
     - Yahia_4  : 11.03°C -> 10.19°C : léger refroidissement
       (-0.84°C), sous le seuil par défaut de ce script (1.5°C) mais
       dans le bon sens.
   -> CONCLUSION IDENTIQUE À CELLE DU RAPPORT, avec un second capteur
   indépendant : même la thermie Landsat à 30 m ne capte pas
   clairement cet événement (l'empreinte du goutteur, 2-5 m², est
   encore plus diluée dans un pixel de 900 m² que dans un pixel SAR
   de 100 m²). Ce n'est PAS un bug du script : c'est physique, et
   cela confirme la recommandation du rapport de basculer vers
   NDMI/NDWI (Sentinel-2, 10 m) et/ou ECOSTRESS (70 m, mais revisite
   plus fréquente) -- fichiers que vous n'avez pas fournis cette
   fois-ci. Le script les utilisera automatiquement dès qu'ils seront
   disponibles (voir §1, découverte automatique), sans modification
   de code nécessaire.

CE QUI N'A PAS CHANGÉ PAR RAPPORT AU V2 (repris tel quel, logique déjà
validée) :
   - Grille canonique + appariement k-d tree pour les capteurs pixel
     (SAR, NISAR-Backscatter) -- tol=7 m.
   - Baseline glissante 30 j, seuil de pic pixel 1.5 dB, seuil de
     parcelle 10% des pixels.
   - Table de classification Pluie/Irrigation (seuils 5 mm / 15 mm,
     été = Mai-Oct) -- Section D du rapport, reprise à l'identique.
   - Garde-fou INDETERMINE si la pluie est inconnue (jamais 0 mm par
     défaut).

USAGE
-----
    python detect_irrigation_vs_pluie.py --dry-run
        Validation multi-capteur sur l'événement connu (Kemel/Yahia),
        avec téléchargement automatique de la pluie si nécessaire.

    python detect_irrigation_vs_pluie_v3.py --data-dir /chemin/vers/vos/parquet
        Détection complète sur toute la période, tous les capteurs
        DISPONIBLES dans /chemin/vers/vos/parquet (n'importe quel
        sous-ensemble des 8 sources documentées -- le script s'adapte).

    python detect_irrigation_vs_pluie_v3.py --precip precipitation_awam.csv
        Utilise un CSV de pluie déjà préparé au lieu d'ERA5/Open-Meteo.

Dépendances : pip install scipy requests pandas pyarrow
(scipy et requests sont optionnels -- le script continue en mode
dégradé s'ils sont absents, avec un avertissement clair).
"""

import sys
import re
import time
import argparse
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent
PIPELINE_MASTER_DIR = SCRIPTS_DIR / "PIPELINE_MASTER"

for p in [str(SCRIPTS_DIR), str(PIPELINE_MASTER_DIR), str(SCRIPT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import pandas as pd

try:
    from scipy.spatial import cKDTree
except ImportError:
    cKDTree = None  # le module pixel (SAR / NISAR-Backscatter) sera désactivé

try:
    import requests
except ImportError:
    requests = None  # l'API Open-Meteo sera simplement indisponible


# ===========================================================================
# 0. CONFIGURATION GÉNÉRALE
# ===========================================================================

# Répertoire par défaut : celui où se trouve ce script. Modifiable via
# --data-dir. Le script cherche récursivement (rglob) tous les .parquet
# en dessous, donc une arborescence outputs/pixel_indices_database/{raw,clean}
# fonctionne aussi bien qu'un dossier plat.
DEFAULT_DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR_NAME = "cache_precip"

# --- Paramètres de détection (repris du v2, Section B/C du rapport) ---
BASELINE_JOURS = 30            # médiane glissante -- ligne de base "sol sec normal"
SEUIL_PIC_DB = 1.5             # écart (dB) au-dessus de la baseline pour un pic SAR/NISAR pixel
SEUIL_PCT_PIXELS = 10.0        # % minimum de pixels en pic pour flaguer un jour de parcelle (SAR/NISAR)
TOL_SNAP_M = 7.0               # tolérance (m) d'appariement pixel -> grille canonique

# --- Paramètres thermiques (nouveaux en v3) ---
BASELINE_JOURS_THERMIQUE = 45  # les passages Landsat/ECOSTRESS/MODIS sont plus rares que S1 -> fenêtre plus large
SEUIL_CHUTE_DTS_C = 1.5        # chute (°C) de ΔTs=LST-Tair sous la baseline propre à la parcelle pour évoquer un refroidissement évaporatif
SEUIL_Z_SITE = 1.0             # z-score minimal (parcelle vs ses pairs du même site, même date) pour corroborer

# --- Paramètres optiques (nouveaux en v3, utilisés si S2-Indices fourni) ---
BASELINE_JOURS_OPTIQUE = 30
SEUIL_HAUSSE_NDMI = 0.05
SEUIL_HAUSSE_NDWI = 0.05

# --- Paramètres humidité du sol (nouveaux en v3, si NISAR-SoilMoisture fourni) ---
SEUIL_HAUSSE_SM = 0.02         # m3/m3

# --- Seuil de score composite pour flaguer un jour "candidat" (irrigation OU pluie) ---
SEUIL_SCORE_COMPOSITE = 1.5

# --- Seuil "sol nu / faible couvert" -- downweight du SAR (§4.2 du rapport) ---
SEUIL_NDVI_SOL_NU = 0.20       # proxy fCover quand fCover réel indisponible
MOTS_CLES_SOL_NU = ("sol nu", "aucune")

# --- Classification pluie / irrigation (Section D du rapport, INCHANGÉ) ---
# SEUIL_PLUIE_MM = 5.0 mm cumulés sur la fenêtre antécédente (FENETRE_PRECIP_JOURS = 5 jours) :
# Seuil agronomique standard méditerranéen / FAO pour distinguer un épisode pluvieux significatif
# (humectation superficielle du sol masquant l'irrigation) d'un sol sec nécessitant un apport artificiel.
SEUIL_PLUIE_MM = 5.0
FENETRE_PRECIP_JOURS = 5
SEUIL_AMBIANT_HUMIDE_MM = 15
FENETRE_AMBIANTE_JOURS = 30

DATE_DEBUT = "2025-05-01"  # Date de début de la saison de référence (configurable)
# BUGFIX §27.1.5 : DATE_FIN était codée en dur ("2026-08-12"), figeant le pipeline
# et l'empêchant d'intégrer les nouvelles scènes satellites arrivant après cette date.
# Remplacement par la date UTC du jour, mise à jour à chaque exécution.
# BUGFIX warning Python 3.12+ : utcnow() est déprécié → datetime.now(timezone.utc)
try:
    from datetime import datetime as _dt, timezone as _tz
    DATE_FIN = _dt.now(_tz.utc).strftime("%Y-%m-%d")
except Exception:
    DATE_FIN = "2026-08-12"  # fallback de sécurité uniquement

# Événements connus utilisés pour l'auto-validation (Planning WWC).
# Chargés dynamiquement depuis le registre central PIPELINE_MASTER/registre_evenements_terrain.csv
def charger_evenements_connus_depuis_csv(csv_path: Path = None) -> list:
    """
    Charge dynamiquement les événements d'irrigation connus depuis le CSV central
    PIPELINE_MASTER/registre_evenements_terrain.csv.
    """
    script_dir = Path(__file__).resolve().parent
    if csv_path is None:
        csv_path = script_dir.parent / "PIPELINE_MASTER" / "registre_evenements_terrain.csv"
    
    if not csv_path.exists():
        alt_path = script_dir.parent / "registre_evenements_terrain.csv"
        if alt_path.exists():
            csv_path = alt_path
        else:
            print("  [ℹ] registre_evenements_terrain.csv non trouvé — validation des événements connus désactivée.")
            return []

    try:
        df = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
        df_irrig = df[df["categorie_evenement"] == "IRRIGATION"].copy()
        
        groupes = {}
        for _, row in df_irrig.iterrows():
            nom = str(row.get("nom_evenement", "Événement Irrigation"))
            d_debut = str(row.get("date_debut_signal_satellite") or row.get("date_observation_terrain"))
            d_fin = str(row.get("date_fin_signal_satellite") or d_debut)
            pid = str(row.get("parcel_id", ""))
            culture = str(row.get("culture", pid))
            statut = str(row.get("statut", ""))
            
            clé = (nom, d_debut, d_fin)
            if clé not in groupes:
                groupes[clé] = {
                    "nom": nom,
                    "date_debut": d_debut,
                    "date_fin": d_fin,
                    "parcelles": {},
                    "attendu_detectable": False if "NON_DETECTABLE" in statut else True
                }
            groupes[clé]["parcelles"][pid] = f"{pid} ({culture})"
            
        return list(groupes.values())
    except Exception as e:
        print(f"  [⚠] Erreur lors du chargement des événements depuis {csv_path}: {e}")
        return []

EVENEMENTS_CONNUS = charger_evenements_connus_depuis_csv()
CONTROLE_DEJA_IRRIGUE = {
    "nom": "Badreddine (irrigation déjà active avant la période observée)",
    "parcel_id": "sidi_mechreg_Parcelle_Badreddine_5",
}

# ===========================================================================
# MÉTADONNÉES TERRAIN (source : Fiche_de_production_PAM.xlsx, feuille
# "FICHE DE SUIVI DES PARCELLES", mise à jour 2026-06-03 -- SEULE donnée
# terrain disponible à ce jour). Superficie RÉELLEMENT exploitée par
# parcelle (pas la superficie totale de la zone), utilisée pour pondérer
# la fiabilité des capteurs à faible résolution : MODIS-LST = 1 km = 100 ha
# de pixel, alors que Kemel_1/Yahia_4/Badreddine_5 font 0.5 à 2 ha. Un
# pixel MODIS mélange donc très majoritairement du signal HORS parcelle.
# `cultures_terrain` sert à CROISER (pas remplacer aveuglément) la colonne
# `culture` du panel satellite -- un écart entre les deux est imprimé au
# démarrage plutôt que silencieusement ignoré.
#
# NOTE (écart constaté) : la fiche terrain ne mentionne PAS de Sauge sur
# Yahia_4 au 2026-06-03 (0 plant), alors que la synthèse du pipeline
# satellite libelle cette parcelle "Lavande/Romarin/Geranium/Sauge" --
# à vérifier auprès du terrain (culture ajoutée après le 03/06, erreur de
# métadonnée côté pipeline, ou parcelle voisine confondue).
#
# CORRECTIF 2026-08-12 : les parcelles makthar_P1..P6 et sidi_mechreg_
# Parcelle_Kemel_2/3 N'ONT PAS de fiche PAM (feuille PAM = plantes
# aromatiques/médicinales uniquement ; Amandier/Olivier/Caroubier/sol nu
# n'en sont pas), mais elles ont maintenant une entrée approximative
# ci-dessous basée sur la surface réelle du polygone geojson, pour activer
# le facteur d'échelle (auparavant facteur=1.0, aucune correction, alors
# que ce sont justement les parcelles les plus petites par rapport au
# pixel MODIS-LST -- voir note dans chaque entrée).
# ===========================================================================
import unicodedata

def normaliser_mot_culture(c):
    """Normalise un mot de culture : retire les accents, passe en minuscules,
    et traite les variantes orthographiques connues (ex: Vervaine -> Verveine)."""
    if not isinstance(c, str):
        return ""
    c_clean = "".join(ch for ch in unicodedata.normalize("NFD", c) if unicodedata.category(ch) != "Mn")
    c_clean = c_clean.lower().strip()
    if c_clean in ("vervaine", "verveine"):
        return "verveine"
    return c_clean


# ===========================================================================
# MÉTADONNÉES TERRAIN OFFICIELLES
# Dictionnaire par défaut de secours + chargement dynamique depuis GeoJSON.
# ===========================================================================
PARCELLES_TERRAIN_DEFAUT = {
    "sidi_mechreg_Parcelle_Kemel_1": {
        "superficie_exploitee_ha": 0.8433, "superficie_zone_ha": 0.8433,
        "cultures_terrain": ["Lavande", "Romarin", "Géranium"],
        "irrigation_continue_declaree": True, "type_irrigation": "Manuel au pied / Citerne",
    },
    "sidi_mechreg_Parcelle_Kemel_2": {
        "superficie_exploitee_ha": 0.6528, "superficie_zone_ha": 0.6528,
        "cultures_terrain": ["Aucune"],
        "irrigation_continue_declaree": True, "type_irrigation": "Manuel au pied / Citerne",
    },
    "sidi_mechreg_Parcelle_Kemel_3": {
        "superficie_exploitee_ha": 0.1651, "superficie_zone_ha": 0.1651,
        "cultures_terrain": ["Caroubier"],
        "irrigation_continue_declaree": True, "type_irrigation": "Manuel au pied / Citerne",
    },
    "sidi_mechreg_Parcelle_Yahia_4": {
        "superficie_exploitee_ha": 0.5886, "superficie_zone_ha": 0.5886,
        "cultures_terrain": ["Lavande", "Romarin", "Géranium", "Sauge"],
        "irrigation_continue_declaree": True, "type_irrigation": "Manuel au pied / Citerne",
    },
    "sidi_mechreg_Parcelle_Badreddine_5": {
        "superficie_exploitee_ha": 2.1137, "superficie_zone_ha": 2.1137,
        "cultures_terrain": ["Olivier", "Citronnelle", "Verveine"],
        "irrigation_continue_declaree": True, "type_irrigation": "Goutte-à-goutte (depuis 15/06/2026)",
    },
    "makthar_P1": {
        "superficie_exploitee_ha": 0.965, "superficie_zone_ha": 0.965,
        "cultures_terrain": ["Amandier"],
    },
    "makthar_P2": {
        "superficie_exploitee_ha": 1.420, "superficie_zone_ha": 1.420,
        "cultures_terrain": ["Olivier"],
    },
    "makthar_P3": {
        "superficie_exploitee_ha": 0.735, "superficie_zone_ha": 0.735,
        "cultures_terrain": ["Sol nu"],
    },
    "makthar_P4": {
        "superficie_exploitee_ha": 1.436, "superficie_zone_ha": 1.436,
        "cultures_terrain": ["Sol nu"],
    },
    "makthar_P5": {
        "superficie_exploitee_ha": 1.628, "superficie_zone_ha": 1.628,
        "cultures_terrain": ["Sol nu"],
    },
    "makthar_P6": {
        "superficie_exploitee_ha": 0.924, "superficie_zone_ha": 0.924,
        "cultures_terrain": ["Sol nu"],
    },
}

def charger_parcelles_terrain_dynamique() -> dict:
    """Charge dynamiquement les parcelles depuis le GeoJSON centralisé
    (config_global.py / parcelles_geojson), avec repli transparent sur
    le registre historique par défaut pour une résilience absolue."""
    res = dict(PARCELLES_TERRAIN_DEFAUT)
    try:
        from PIPELINE_MASTER.config_global import get_map_parcelles_terrain, PARCELLES_DIR
        geojson_all = PARCELLES_DIR / "AWAM_TERRAIN_ALL_ALL_Boundaries_20250501_20260828_v1.0.geojson"
        if geojson_all.exists():
            map_geo = get_map_parcelles_terrain(geojson_all)
            for pid, meta in map_geo.items():
                cult_str = meta.get("culture", "")
                cult_list = [c.strip() for c in cult_str.split("/") if c.strip()] if cult_str else ["Inconnue"]
                area = float(meta.get("area_h", 1.0))
                
                if pid not in res:
                    res[pid] = {
                        "superficie_exploitee_ha": area,
                        "superficie_zone_ha": area,
                        "cultures_terrain": cult_list,
                    }
                else:
                    if not res[pid].get("cultures_terrain"):
                        res[pid]["cultures_terrain"] = cult_list
                    if not res[pid].get("superficie_exploitee_ha"):
                        res[pid]["superficie_exploitee_ha"] = area
    except Exception:
        pass
    return res

PARCELLES_TERRAIN = charger_parcelles_terrain_dynamique()

# ===========================================================================
# Registre des 8 sources documentées (documentation_pipeline_extraction_spatial_v2.md §7.2)
# Chaque source déclare ses colonnes de valeur, si elle est native "pixel"
# (beaucoup de points par parcelle/date -> module de pics pixel applicable)
# ou "parcelle" (résolution grossière, une valeur ~unique par parcelle/date),
# et sa résolution nominale (utile pour pondérer la fiabilité du signal).
# ===========================================================================
SOURCE_SPECS = {
    "S2-Indices": {
        "cols": ["NDVI", "SAVI", "MSAVI", "EVI", "NDRE", "CI_RedEdge", "VARI",
                 "NDWI", "NDMI", "BSI", "Carbonate_SWIR", "NDSI_soil", "SI_soil", "fCover"],
        "niveau": "pixel", "resolution_m": 10,
    },
    "S1-SAR": {
        "cols": ["VV_dB", "VH_dB", "VH_VV_ratio", "DpRVIc"],
        "niveau": "pixel", "resolution_m": 10,
    },
    "MODIS-LST": {
        "cols": ["LST_K", "SMI", "CWSI_proxy"],
        "niveau": "parcelle", "resolution_m": 1000,
    },
    "Landsat-Thermal": {
        "cols": ["LST_Landsat_K", "LST_Landsat_C", "NDVI_Landsat"],
        "niveau": "parcelle", "resolution_m": 30,
    },
    "ERA5-Meteo": {
        "cols": ["Tmin_C", "Tmax_C", "precip_mm", "GDD_cumul", "frost_risk"],
        "niveau": "parcelle", "resolution_m": 11000,
    },
    "ECOSTRESS-LST": {
        "cols": ["LST_ECOSTRESS_K", "LST_ECOSTRESS_C", "LST_ECOSTRESS_QC",
                 "emissivity", "cloud_flag", "acquisition_time", "day_night"],
        "niveau": "parcelle", "resolution_m": 70,
    },
    "NISAR-SoilMoisture": {
        "cols": ["soil_moisture_vol", "soil_moisture_qc", "vegetation_water_content"],
        "niveau": "parcelle", "resolution_m": 200,
    },
    "NISAR-Backscatter": {
        "cols": ["HH_gamma0_dB", "HV_gamma0_dB", "HV_HH_ratio", "RVI_NISAR"],
        "niveau": "pixel", "resolution_m": 200,
    },
}

# Sources "pixel" pour lesquelles on applique le module de détection de pics
# (grille canonique + k-d tree + baseline glissante), une par colonne
# "principale" -- reprend la logique SAR du v2, généralisée.
SOURCES_PIXEL_PIC = {
    "S1-SAR": {"colonne": "VV_dB", "seuil_db": SEUIL_PIC_DB, "poids_defaut": 1.5},
    "NISAR-Backscatter": {"colonne": "HH_gamma0_dB", "seuil_db": SEUIL_PIC_DB, "poids_defaut": 1.0},
}

# Sources thermiques -- une entrée par capteur LST disponible, avec un poids
# et un seuil de chute de température (°C) calibré à l'échelle du capteur.
SOURCES_THERMIQUES = {
    "ECOSTRESS-LST": {"colonne": "LST_ECOSTRESS_C", "poids": 2.0, "seuil_chute": 1.5},
    "Landsat-Thermal": {"colonne": "LST_Landsat_C", "poids": 1.5, "seuil_chute": 1.5},
    "MODIS-LST": {"colonne": "LST_K", "colonne_est_kelvin": True, "poids": 1.0, "seuil_chute": 1.0},
}

# Colonne evidence (préfixe avant "_evidence") -> CAPTEUR PHYSIQUE dont elle
# dérive (nouveau v4). Sert à calculer n_capteurs_independants, plus strict
# que le simple compte de colonnes "*_evidence" : CWSI_proxy ET SMI (script
# besoin) dérivent tous les deux de MODIS-LST -- ce sont 2 indices, PAS 2
# preuves indépendantes. De même, ECOSTRESS, Landsat et MODIS sont tous les trois
# des capteurs thermiques (LST) -- regroupés sous "Thermique-LST" pour éviter
# que la canicule ne cumule 3 preuves thermiques parasites.
FAMILLE_CAPTEUR = {
    "ECOSTRESS-LST": "Thermique-LST", "Landsat-Thermal": "Thermique-LST", "MODIS-LST": "Thermique-LST",
    "NDMI": "S2-Indices", "NDWI": "S2-Indices", "NDRE": "S2-Indices", "SAVI": "S2-Indices", "MSAVI": "S2-Indices", "BSI": "S2-Indices",
    "soil_moisture": "NISAR-SoilMoisture", "vwc": "NISAR-SoilMoisture",
    "VV_dB": "S1-SAR", "HH_gamma0_dB": "NISAR-Backscatter",
    "stress_CWSI": "Thermique-LST", "stress_SMI": "Thermique-LST",
    "stress_NDMI": "S2-Indices", "stress_NDWI": "S2-Indices", "stress_NDRE": "S2-Indices", "stress_BSI": "S2-Indices",
    "stress_SM": "NISAR-SoilMoisture", "stress_VWC": "NISAR-SoilMoisture",
}

# CORRIGÉ (2026-08-14) : liste déplacée au niveau module (elle vivait avant
# uniquement à l'intérieur de main(), lignes ~1395-1402). Raison : detect_
# besoin_vs_irrigation.py reconstruit son propre panel via
# _construire_panel_avec_irrigation(), qui est censée "reproduire EXACTEMENT
# les étapes de main()" (cf. son docstring) mais codait en dur une copie
# incomplète de cette liste (NDMI/NDWI seulement, sur les 6 modules) --
# NDRE/SAVI/MSAVI/BSI étaient silencieusement absents du score_composite
# utilisé pour le calcul de comblement des besoins. En important cette
# constante unique depuis les deux scripts (au lieu de la recopier), les
# deux pipelines ne peuvent plus diverger, même si un futur indice est
# ajouté ici.
MODULES_OPTIQUES = [
    ("NDMI", SEUIL_HAUSSE_NDMI, 2.0, True, "Eau foliaire (SWIR/NIR)"),
    ("NDWI", SEUIL_HAUSSE_NDWI, 1.5, True, "Eau en surface (NIR/Green)"),
    ("NDRE", 0.03, 1.5, True, "Réponse chlorophyllienne précoce (RedEdge/NIR)"),
    ("SAVI", 0.04, 1.25, True, "Végétation ajustée au sol (vergers/faible couvert)"),
    ("MSAVI", 0.04, 1.25, True, "Végétation ajustée au sol modifiée"),
    ("BSI", -0.04, 1.5, False, "Bare Soil Index (baisse = humidification sol nu)"),
]

FILENAME_RE = re.compile(
    r"AWAM_(?:GEE|Earthdata)_(?P<site_raw>[A-Za-z0-9\-]+?)_ALL_(?P<source>[A-Za-z0-9\-]+)_"
    r"(?P<start>\d{8})_(?P<end>\d{8})(?:_v\d+)?(?:_calibrated)?(?:_clean)?\.parquet$",
    re.IGNORECASE,
)


def normaliser_site(site_raw):
    """Les noms de fichiers utilisent des tirets ('sidi-mechreg'), les
    données internes des underscores ('sidi_mechreg'). On harmonise ici."""
    return site_raw.replace("-", "_")


# ===========================================================================
# PONDÉRATION SELON LE DÉSACCORD D'ÉCHELLE PIXEL <-> PARCELLE (nouveau v4)
# ===========================================================================

FACTEUR_ECHELLE_PLANCHER = 0.15  # jamais annulé totalement -- signal partiel encore informatif


def facteur_echelle(parcel_id, resolution_m, plancher=FACTEUR_ECHELLE_PLANCHER):
    """Facteur [plancher, 1.0] reflétant le désaccord entre la taille d'un
    pixel de résolution `resolution_m` et la superficie RÉELLEMENT
    exploitée de la parcelle (PARCELLES_TERRAIN, seule donnée terrain
    disponible). Ex : Yahia_4 (0.5 ha) vu par MODIS-LST (100 ha/pixel) ->
    ratio 0.005 -> facteur = plancher (0.15) : le signal MODIS-LST sur
    cette parcelle reste utilisé, mais pèse 15% de son poids nominal, pas
    100%, car il mélange à ~99.5% du signal hors-parcelle.
    Pour une parcelle absente de PARCELLES_TERRAIN (aucune métadonnée
    terrain NI approximation geojson disponible) : retourne 1.0, comportement
    inchangé. Depuis le CORRECTIF 2026-08-12 ci-dessus, plus aucune parcelle
    connue à ce jour n'est dans ce cas (makthar_P1..P6 et Kemel_2/3 ont
    désormais une approximation geojson) -- ce cas ne couvre plus qu'une
    future nouvelle parcelle pas encore ajoutée à PARCELLES_TERRAIN."""
    meta = PARCELLES_TERRAIN.get(parcel_id)
    if not meta or not meta.get("superficie_exploitee_ha"):
        return 1.0
    aire_pixel_ha = (resolution_m ** 2) / 10000.0
    if aire_pixel_ha <= 0:
        return 1.0
    ratio = meta["superficie_exploitee_ha"] / aire_pixel_ha
    return max(plancher, min(1.0, ratio))


def verifier_coherence_terrain():
    """Compare la culture déclarée côté terrain (PARCELLES_TERRAIN) à ce
    que le pipeline satellite affichera -- imprimé au démarrage, jamais
    silencieux. N'écrase RIEN automatiquement : un écart doit être vérifié
    par un humain, pas résolu par le script."""
    print("\n[TERRAIN] Métadonnées terrain disponibles (Fiche_de_production_PAM.xlsx, "
          "maj 2026-06-03) :")
    for pid, meta in PARCELLES_TERRAIN.items():
        aire_modis_ha = SOURCE_SPECS["MODIS-LST"]["resolution_m"] ** 2 / 10000
        ratio = meta["superficie_exploitee_ha"] / aire_modis_ha
        print(f"  - {pid} : {meta['superficie_exploitee_ha']:g} ha exploité(s) "
              f"(zone totale {meta['superficie_zone_ha']:g} ha), cultures terrain : "
              f"{', '.join(meta['cultures_terrain'])} -- soit {ratio*100:.2f}% d'un pixel MODIS-LST "
              f"(1 km = 100 ha) : signal MODIS-LST fortement dilué sur cette parcelle.")
    print("  [i] makthar_P1..P6 et Kemel_2/Kemel_3 : hors fiche PAM (arbres/sol nu), "
          "mais correction d'échelle APPROXIMATIVE appliquée depuis 2026-08-12 "
          "(surface = polygone geojson complet, pas une vraie 'superficie exploitée' "
          "terrain -- à affiner si une mesure de terrain devient disponible).")


# ===========================================================================
# 1. DÉCOUVERTE AUTOMATIQUE DES FICHIERS DISPONIBLES
# ===========================================================================

def decouvrir_fichiers(data_dir):
    """Scanne récursivement data_dir et retourne {source: [Path, ...]}.
    Contrairement au v2 (chemins Windows codés en dur pointant sur des
    fichiers S1-SAR spécifiques), cette version s'adapte à N'IMPORTE QUEL
    sous-ensemble des 8 sources documentées, présent ou non.

    DÉDOUBLONNAGE RAW vs CLEAN (corrige un bug réel observé en usage) :
    quand `raw/` et `clean/` sont tous les deux sous data_dir, chaque
    (source, site) matche DEUX fichiers -- un `..._v2.parquet` (brut) et
    un `..._v2_clean.parquet` (nettoyé Phase 3). Les concaténer ferait
    DOUBLE COMPTER chaque observation (fausse les médianes, les baselines
    glissantes, les % de pixels en pic, les z-scores intersites...), et le
    fichier brut peut en plus avoir un schéma différent (colonnes pas
    encore harmonisées par `clean_extracted_data.py`, ce qui expliquait le
    `KeyError: 'date'`). Pour chaque (source, site) : on ne garde QUE la
    version `_clean` si elle existe ; sinon on retombe sur le brut le plus
    récent (par date de fin dans le nom de fichier)."""
    data_dir = Path(data_dir)
    candidats = {}  # (source, site_norm) -> [(Path, est_clean, date_fin), ...]
    ignores = []
    for p in data_dir.rglob("*.parquet"):
        m = FILENAME_RE.match(p.name)
        if not m:
            ignores.append(p.name)
            continue
        source = m.group("source")
        if source not in SOURCE_SPECS:
            ignores.append(p.name)
            continue
        site_norm = normaliser_site(m.group("site_raw"))
        est_clean = "_clean" in p.stem.lower()
        est_calibrated = "calibrated" in p.stem.lower()
        candidats.setdefault((source, site_norm), []).append((p, est_clean, est_calibrated, m.group("end")))

    trouve = {}
    doublons = []
    for (source, site_norm), items in candidats.items():
        if len(items) == 1:
            trouve.setdefault(source, []).append(items[0][0])
            continue
        propres = [it for it in items if it[1]]
        pool = propres if propres else items
        # Prioritize calibrated files if present
        calibres = [it for it in pool if it[2]]
        if calibres:
            pool = calibres
        pool = sorted(pool, key=lambda it: it[3], reverse=True)  # date de fin la plus récente d'abord
        garde = pool[0][0]
        ecartes = [it[0].name for it in items if it[0] != garde]
        trouve.setdefault(source, []).append(garde)
        doublons.append((source, site_norm, garde.name, ecartes))

    print("[DÉCOUVERTE] Fichiers reconnus par source :")
    for source in SOURCE_SPECS:
        n = len(trouve.get(source, []))
        marque = "✓" if n else " "
        print(f"  [{marque}] {source:<20s} : {n} fichier(s)"
              + (f" -> {[f.name for f in trouve[source]]}" if n else " (absent -- module désactivé)"))
    if doublons:
        print("\n[DÉDOUBLONNAGE] Plusieurs fichiers correspondaient au même (source, site) -- "
              "un seul retenu par (source, site) pour éviter un comptage en double raw+clean :")
        for source, site_norm, garde, ecartes in doublons:
            print(f"  [{source} / {site_norm}] gardé : {garde}  |  ignoré(s) : {ecartes}")
    if ignores:
        print(f"\n  [i] {len(ignores)} fichier(s) .parquet ignoré(s) (nom non reconnu) : {ignores[:5]}"
              + (" ..." if len(ignores) > 5 else ""))
    if not trouve:
        raise SystemExit(f"Aucun fichier reconnu dans {data_dir} (ni sous-dossiers). "
                          f"Vérifiez --data-dir, ou que les noms suivent le format "
                          f"AWAM_<GEE|Earthdata>_<site>_ALL_<Source>_<debut>_<fin>[_vN][_clean].parquet")
    return trouve


# Noms de colonne date déjà rencontrés selon la provenance (GEE vs Earthdata,
# brut vs nettoyé). Recherche insensible à la casse en dernier recours.
_DATE_COL_CANDIDATS = ["date", "Date", "DATE", "date_acquisition", "acquisition_date",
                        "time", "Time", "datetime", "acq_date"]


def _trouver_colonne_date(df):
    for c in _DATE_COL_CANDIDATS:
        if c in df.columns:
            return c
    for c in df.columns:
        if "date" in c.lower():
            return c
    return None


def _charger_un_fichier(path):
    """Charge UN fichier. Ne lève jamais d'exception vers l'appelant : un
    fichier illisible ou au schéma inattendu est signalé puis IGNORÉ, pour
    que le reste du pipeline (autres sources, autres sites) continue quand
    même -- contrairement au v2 où un seul fichier problématique arrêtait
    tout le script (`KeyError: 'date'` observé en usage réel)."""
    try:
        df = pd.read_parquet(path)
    except Exception as e:
        print(f"  [!] {path.name} illisible ({e}) -- fichier ignoré.")
        return None

    df = df.drop(columns=["geometry"], errors="ignore")

    col_date = _trouver_colonne_date(df)
    if col_date is None:
        print(f"  [!] Aucune colonne de date reconnue dans {path.name} "
              f"(colonnes présentes : {list(df.columns)}) -- fichier ignoré.")
        return None
    if col_date != "date":
        df = df.rename(columns={col_date: "date"})
    try:
        df["date"] = pd.to_datetime(df["date"])
    except Exception as e:
        print(f"  [!] Colonne date illisible dans {path.name} ({e}) -- fichier ignoré.")
        return None

    if "site" not in df.columns:
        m = FILENAME_RE.match(path.name)
        df["site"] = normaliser_site(m.group("site_raw")) if m else "inconnu"
    else:
        df["site"] = df["site"].apply(normaliser_site)
    return df


def charger_source(paths):
    """Concatène tous les fichiers d'une même source (plusieurs sites).
    Les fichiers en échec sont ignorés (voir _charger_un_fichier) plutôt
    que de faire planter tout le run."""
    frames = [f for f in (_charger_un_fichier(p) for p in paths) if f is not None]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ===========================================================================
# 2. GRILLE DE PIXELS STABLE DANS LE TEMPS (repris du v2, généralisé à toute
#    colonne pixel -- SAR VV_dB, NISAR-Backscatter HH_gamma0_dB, etc.)
# ===========================================================================

def construire_serie_pixels(sub, colonne, tol_m=TOL_SNAP_M):
    """Les coordonnées d'un même pixel physique dérivent légèrement d'un
    passage à l'autre selon le capteur. On construit une grille canonique à
    partir de la date la plus dense, puis on rattache chaque acquisition à
    cette grille par plus proche voisin (rejeté si > tol_m). Retourne
    (wide, ref, n_pixels)."""
    if cKDTree is None:
        return pd.DataFrame(), pd.DataFrame(), 0
    if sub.empty or colonne not in sub.columns:
        return pd.DataFrame(), pd.DataFrame(), 0
    sub = sub.dropna(subset=[colonne])
    if sub.empty:
        return pd.DataFrame(), pd.DataFrame(), 0

    date_ref = sub.groupby("date").size().idxmax()
    ref = sub.loc[sub.date == date_ref, ["longitude", "latitude"]].reset_index(drop=True)
    ref["pixel_uid"] = range(len(ref))

    lat0 = ref["latitude"].mean()
    m_lat = 111320.0
    m_lon = 111320.0 * np.cos(np.radians(lat0))

    def to_xy(d):
        return np.c_[d["longitude"].values * m_lon, d["latitude"].values * m_lat]

    tree = cKDTree(to_xy(ref))
    parts = []
    for date, g in sub.groupby("date"):
        dist, idx = tree.query(to_xy(g), k=1)
        ok = dist <= tol_m
        gm = g.loc[ok, [colonne]].copy()
        gm["date"] = date
        gm["pixel_uid"] = ref["pixel_uid"].values[idx[ok]]
        parts.append(gm)

    long = pd.concat(parts, ignore_index=True)
    long = long.groupby(["date", "pixel_uid"])[colonne].mean().reset_index()
    wide = long.pivot(index="date", columns="pixel_uid", values=colonne).sort_index()
    return wide, ref, len(ref)


def detecter_pics_pixel(wide, baseline_jours=BASELINE_JOURS, seuil_db=SEUIL_PIC_DB):
    """Pour chaque pixel : ligne de base glissante + écart. Retourne un
    résumé par date : % de pixels en pic, écart médian, écart max."""
    if wide.empty:
        return pd.DataFrame()
    baseline = wide.rolling(f"{baseline_jours}D", min_periods=5).median()
    ecart = wide - baseline
    pic = ecart >= seuil_db
    return pd.DataFrame({
        "pct_pixels_pic": pic.mean(axis=1) * 100,
        "n_pixels_pic": pic.sum(axis=1),
        "n_pixels_valides": wide.notna().sum(axis=1),
        "ecart_median": ecart.median(axis=1),
        "ecart_max": ecart.max(axis=1),
    })


def calculer_bruit_fond(res, precip=None, site=None, dates_a_exclure=None):
    """Bruit de fond de '% pixels en pic' sur les jours calmes -- sert de
    référence pour juger si un % observé pendant un événement est notable."""
    if res.empty:
        return None
    calme = res.copy()
    if dates_a_exclure is not None:
        masque = ~calme.index.isin(pd.to_datetime(dates_a_exclure))
        calme = calme.loc[masque]
    if calme.empty:
        return None
    bruit_global = {
        "median": calme["pct_pixels_pic"].median(),
        "p90": calme["pct_pixels_pic"].quantile(0.90),
        "p99": calme["pct_pixels_pic"].quantile(0.99),
        "n_jours": len(calme),
    }
    bruit_sec = None
    if precip is not None and site is not None and site in precip.site.unique():
        dates_sec = [d for d in calme.index
                     if (p5 := cumul_precip_avant(precip, site, d, fenetre_jours=5)) is not None and p5 < 1.0]
        if dates_sec:
            calme_sec = calme.loc[dates_sec]
            bruit_sec = {
                "median": calme_sec["pct_pixels_pic"].median(),
                "p90": calme_sec["pct_pixels_pic"].quantile(0.90),
                "p99": calme_sec["pct_pixels_pic"].quantile(0.99),
                "n_jours": len(calme_sec),
            }
    return {"global": bruit_global, "sec": bruit_sec}


# ===========================================================================
# 3. PRÉCIPITATION -- colonne embarquée > CSV manuel > API Open-Meteo
# ===========================================================================

def extraire_precip_embarquee(df_meteo):
    """NOUVEAU EN V3 : si ERA5-Meteo contient déjà precip_mm (le cas
    normal documenté), on l'utilise directement -- 0 appel réseau. Agrégée
    en médiane par site/date (les parcelles d'un même site partagent
    quasiment la même valeur, le buffer ERA5 étant à 11 km)."""
    if "precip_mm" not in df_meteo.columns:
        return None
    if df_meteo["precip_mm"].notna().sum() == 0:
        return None
    p = (df_meteo.groupby(["site", "date"])["precip_mm"]
         .median().reset_index())
    return p


def centroide_site(df, site):
    sub = df[df.site == site]
    return sub.latitude.mean(), sub.longitude.mean()


def telecharger_precipitation_openmeteo(site, lat, lon, cache_dir, date_debut=DATE_DEBUT,
                                         date_fin=DATE_FIN, timeout=30):
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_matches = sorted(cache_dir.glob(f"precip_{site}_*.csv"))
    if cache_matches:
        print(f"  ✓ Précipitation {site} chargée depuis le cache local : {cache_matches[0].name}")
        return pd.read_csv(cache_matches[0], parse_dates=["date"])

    if requests is None:
        print(f"  [!] 'requests' non installé (pip install requests) -> précipitation indisponible pour {site}.")
        return None

    cache_file = cache_dir / f"precip_{site}_{date_debut}_{date_fin}.csv"
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {"latitude": lat, "longitude": lon, "start_date": date_debut, "end_date": date_fin,
              "daily": "precipitation_sum", "timezone": "Africa/Tunis"}

    for tentative in range(1, 4):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            d = pd.DataFrame({"date": pd.to_datetime(data["daily"]["time"]), "site": site,
                               "precip_mm": data["daily"]["precipitation_sum"]})
            d.to_csv(cache_file, index=False)
            print(f"  ✓ Précipitation {site} téléchargée ({len(d)} jours) -> {cache_file}")
            return d
        except Exception as e:
            print(f"  [!] Tentative {tentative}/3 échouée pour {site} : {e}")
            if tentative < 3:
                time.sleep(3 * tentative)

    print(f"  [!!] ÉCHEC du téléchargement Open-Meteo pour {site} après 3 tentatives. "
          f"Toute date de ce site sera marquée INDETERMINE (jamais 0 mm par défaut).")
    return None


def charger_precipitation_manuelle(path):
    precip = pd.read_csv(path, parse_dates=["date"])
    for col in ("date", "site", "precip_mm"):
        if col not in precip.columns:
            raise ValueError(f"Colonne '{col}' manquante dans {path} — format attendu : date, site, precip_mm")
    return precip


def obtenir_precipitation(df_meteo, sites, cache_dir, csv_manuel=None, use_api=True):
    if csv_manuel is not None:
        print(f"[PLUIE] Chargée depuis {csv_manuel} (mode manuel).")
        return charger_precipitation_manuelle(csv_manuel)

    embarquee = extraire_precip_embarquee(df_meteo) if df_meteo is not None else None
    if embarquee is not None:
        print(f"[PLUIE] Colonne precip_mm trouvée dans ERA5-Meteo -- utilisée directement "
              f"({embarquee.site.nunique()} site(s), 0 appel réseau).")
        sites_ok = set(embarquee.site.unique())
        sites_manquants = [s for s in sites if s not in sites_ok]
        if not sites_manquants:
            return embarquee
        print(f"  [!] precip_mm absente/vide pour {sites_manquants} -- tentative Open-Meteo pour ces sites.")
    else:
        print("[PLUIE] Colonne 'precip_mm' absente ou vide dans ERA5-Meteo "
              "(vérifiez clean_extracted_data.py / l'export GEE -- la doc indique qu'elle devrait "
              "être présente). Tentative de secours via Open-Meteo (ERA5-Land, gratuit, sans clé).")
        sites_manquants = list(sites)
        embarquee = None

    if not use_api:
        print("[PLUIE] --no-api : pas de secours réseau -> ces sites resteront INDETERMINE.")
        return embarquee

    parts = [embarquee] if embarquee is not None else []
    for site in sites_manquants:
        if df_meteo is None or site not in df_meteo.site.unique():
            continue
        lat, lon = centroide_site(df_meteo, site)
        d = telecharger_precipitation_openmeteo(site, lat, lon, cache_dir)
        if d is not None:
            parts.append(d)
        time.sleep(0.5)
    if not parts:
        print("[PLUIE] Aucune précipitation obtenue pour aucun site -> classification pluie/irrigation impossible "
              "(tout sera INDETERMINE).")
        return None
    return pd.concat(parts, ignore_index=True)


def cumul_precip_avant(precip, site, date_pic, fenetre_jours=FENETRE_PRECIP_JOURS):
    if precip is None or site not in precip.site.unique():
        return None
    fen = precip[(precip.site == site) & (precip.date > date_pic - pd.Timedelta(days=fenetre_jours))
                 & (precip.date <= date_pic)]
    return fen["precip_mm"].sum() if not fen.empty else 0.0


def cumul_precip_ambiant(precip, site, date_pic, fenetre_jours=FENETRE_AMBIANTE_JOURS):
    return cumul_precip_avant(precip, site, date_pic, fenetre_jours=fenetre_jours)


# ===========================================================================
# 4. PANEL PARCELLE x DATE -- fusion de toutes les sources "parcelle"
#    (agrégation médiane des sources "pixel" pour la partie composite ;
#    les sources pixel gardent EN PLUS leur propre module de pics dédié,
#    cf. §2, pour ne pas perdre le signal minoritaire qui faisait l'objet
#    du v2).
# ===========================================================================

def construire_panel(sources):
    """sources : {nom_source: DataFrame brut}. Retourne un panel unique
    indexé (site, parcel_id, culture, date), une colonne par variable de
    toutes les sources disponibles (moyenne/médiane des pixels pour les
    sources 'pixel' -- SAR/S2/NISAR-Backscatter -- car ce panel sert au
    score composite, pas à la détection de pics minoritaires)."""
    meta_cols = ["site", "parcel_id", "culture", "culture_declaree_parcelle", "signal_partage", "area_h"]
    panel = None
    for source, df in sources.items():
        cols = [c for c in SOURCE_SPECS[source]["cols"] if c in df.columns]
        if not cols:
            continue
        keep_meta = [c for c in meta_cols if c in df.columns]
        agg = (df.groupby(["site", "parcel_id", "date"] + [c for c in keep_meta if c not in ("site", "parcel_id")])
                 [cols].median(numeric_only=True).reset_index())
        # certains groupby ci-dessus peuvent dupliquer 'culture' etc. si elle varie -- rare, on garde le 1er
        agg = agg.loc[:, ~agg.columns.duplicated()]
        if panel is None:
            panel = agg
        else:
            merge_keys = ["site", "parcel_id", "date"]
            common_meta = [c for c in keep_meta if c in panel.columns and c not in merge_keys]
            panel = panel.merge(agg.drop(columns=[c for c in common_meta], errors="ignore"),
                                 on=merge_keys, how="outer")
    if panel is None:
        raise SystemExit("Aucune source exploitable pour construire le panel (colonnes attendues absentes).")
    
    # Remplissage automatique de la colonne 'culture' depuis PARCELLES_TERRAIN
    # si elle est absente ou vide (NaN) pour qu'aucun CSV n'ait de champ culture vide.
    if "culture" not in panel.columns:
        panel["culture"] = np.nan

    for pid, meta in PARCELLES_TERRAIN.items():
        cult_str = "/".join(meta["cultures_terrain"])
        mask = (panel["parcel_id"] == pid) & (panel["culture"].isna() | (panel["culture"].astype(str).str.strip() == "") | (panel["culture"].astype(str) == "nan"))
        panel.loc[mask, "culture"] = cult_str

    return panel.sort_values(["site", "parcel_id", "date"]).reset_index(drop=True)


def est_faible_couvert(culture, ndvi_median):
    """Proxy fCover<15% (§4.2 du rapport) quand fCover réel n'est pas
    disponible : culture déclarée 'Sol nu'/'Aucune', ou NDVI médian < 0.20."""
    if isinstance(culture, str) and any(m in culture.lower() for m in MOTS_CLES_SOL_NU):
        return True
    if ndvi_median is not None and not pd.isna(ndvi_median) and ndvi_median < SEUIL_NDVI_SOL_NU:
        return True
    return False


# ===========================================================================
# 5. PREUVES THERMIQUES -- ΔTs = LST - Tair (proxy CWSI, recommandation #2)
# ===========================================================================

def evidence_thermique(panel, label, colonne_lst, poids, colonne_est_kelvin=False,
                        baseline_jours=BASELINE_JOURS_THERMIQUE, seuil_chute=None,
                        seuil_z=SEUIL_Z_SITE, resolution_m=None):
    """Calcule, pour un capteur LST donné : ΔTs = LST - Tmax_C, l'écart à la
    baseline glissante PROPRE à la parcelle (refroidissement temporel), et
    un z-score PROPRE AU SITE le même jour (corrobore en isolant le signal
    du bruit météo commun à toutes les parcelles d'un site ce jour-là,
    cf. le rôle joué par Badreddine comme témoin dans le rapport SAR)."""
    if colonne_lst not in panel.columns or "Tmax_C" not in panel.columns:
        return panel, False

    if seuil_chute is None:
        seuil_chute = SOURCES_THERMIQUES.get(label, {}).get("seuil_chute", SEUIL_CHUTE_DTS_C)

    lst_c = panel[colonne_lst] - 273.15 if colonne_est_kelvin else panel[colonne_lst]
    dts_col = f"dTs_{label}"
    panel[dts_col] = lst_c - panel["Tmax_C"]

    # Baseline glissante par parcelle (nécessite un tri par date, groupby+rolling)
    panel = panel.reset_index(drop=True)
    panel[f"{dts_col}_anomalie"] = np.nan
    for parcel_id, g in panel.groupby("parcel_id"):
        gg = g.set_index("date").sort_index()
        baseline = gg[dts_col].rolling(f"{baseline_jours}D", min_periods=3).median()
        anom = (gg[dts_col] - baseline).values
        panel.loc[g.sort_values("date").index, f"{dts_col}_anomalie"] = anom

    # z-score intra-site, même date (corrobore / isole le bruit météo commun)
    panel[f"{dts_col}_z_site"] = panel.groupby(["site", "date"])[dts_col].transform(
        lambda x: (x - x.mean()) / x.std(ddof=0) if x.std(ddof=0) not in (0, None) and len(x) >= 3 else np.nan
    )

    flag = (panel[f"{dts_col}_anomalie"] <= -seuil_chute)
    corrobore = panel[f"{dts_col}_z_site"] <= -seuil_z
    # evidence = poids si chute seule ; poids*1.25 si en plus corroborée par les
    # pairs du site le même jour ; 0 sinon.
    valeur = np.where(flag, poids, 0.0)
    valeur = np.where(flag & corrobore, poids * 1.25, valeur)
    if resolution_m and PARCELLES_TERRAIN:
        fe = panel["parcel_id"].map(lambda pid: facteur_echelle(pid, resolution_m)).values
        panel[f"{label}_facteur_echelle"] = fe
        valeur = valeur * fe
    panel[f"{label}_evidence"] = valeur
    panel[f"{label}_flag"] = flag
    panel[f"{label}_capteur"] = label  # trace le capteur physique d'origine (n_capteurs_independants)
    return panel, True


# ===========================================================================
# 6. PREUVES OPTIQUES -- NDMI / NDWI (recommandation #1, si S2-Indices fourni)
# ===========================================================================

# ===========================================================================
# 6. PREUVES OPTIQUES -- NDMI / NDWI / NDRE / SAVI / MSAVI / BSI
# ===========================================================================

def evidence_optique(panel, colonne, poids, seuil, sens_hausse=True, baseline_jours=BASELINE_JOURS_OPTIQUE):
    """Calcule l'anomalie par rapport à la baseline glissante 30j propre à la parcelle.
    - sens_hausse=True (ex: NDMI, NDWI, NDRE, SAVI, MSAVI) : hausse = hydratation/verdissement.
    - sens_hausse=False (ex: BSI) : baisse sous baseline = humidification du sol nu.
    """
    if colonne not in panel.columns:
        return panel, False
    panel[f"{colonne}_anomalie"] = np.nan
    for parcel_id, g in panel.groupby("parcel_id"):
        gg = g.set_index("date").sort_index()
        baseline = gg[colonne].rolling(f"{baseline_jours}D", min_periods=3).median()
        anom = (gg[colonne] - baseline).values
        panel.loc[g.sort_values("date").index, f"{colonne}_anomalie"] = anom
    flag = (panel[f"{colonne}_anomalie"] >= seuil) if sens_hausse else (panel[f"{colonne}_anomalie"] <= seuil)
    panel[f"{colonne}_evidence"] = np.where(flag, poids, 0.0)
    panel[f"{colonne}_flag"] = flag
    return panel, True


# ===========================================================================
# 7. PREUVES HUMIDITÉ ET CONTENU EN EAU -- NISAR (Soil Moisture & VWC)
# ===========================================================================

def evidence_humidite_sol(panel, poids=3.0, seuil_hausse=SEUIL_HAUSSE_SM,
                           baseline_jours=BASELINE_JOURS_OPTIQUE):
    if "soil_moisture_vol" not in panel.columns:
        return panel, False
    panel["soil_moisture_vol_anomalie"] = np.nan
    for parcel_id, g in panel.groupby("parcel_id"):
        gg = g.set_index("date").sort_index()
        baseline = gg["soil_moisture_vol"].rolling(f"{baseline_jours}D", min_periods=3).median()
        anom = (gg["soil_moisture_vol"] - baseline).values
        panel.loc[g.sort_values("date").index, "soil_moisture_vol_anomalie"] = anom
    flag = panel["soil_moisture_vol_anomalie"] >= seuil_hausse
    valeur = np.where(flag, poids, 0.0)
    resolution_m = SOURCE_SPECS["NISAR-SoilMoisture"]["resolution_m"]  # 200 m
    fe = panel["parcel_id"].map(lambda pid: facteur_echelle(pid, resolution_m)).values
    panel["soil_moisture_facteur_echelle"] = fe
    panel["soil_moisture_evidence"] = valeur * fe
    panel["soil_moisture_flag"] = flag
    return panel, True


def evidence_vwc_nisar(panel, poids=2.0, seuil_hausse=0.15, baseline_jours=BASELINE_JOURS_OPTIQUE):
    """Vegetation Water Content (VWC, kg/m2) dérivé du radar L-band NISAR."""
    if "vegetation_water_content" not in panel.columns:
        return panel, False
    panel["vwc_anomalie"] = np.nan
    for parcel_id, g in panel.groupby("parcel_id"):
        gg = g.set_index("date").sort_index()
        baseline = gg["vegetation_water_content"].rolling(f"{baseline_jours}D", min_periods=3).median()
        anom = (gg["vegetation_water_content"] - baseline).values
        panel.loc[g.sort_values("date").index, "vwc_anomalie"] = anom
    flag = panel["vwc_anomalie"] >= seuil_hausse
    valeur = np.where(flag, poids, 0.0)
    fe = panel["parcel_id"].map(lambda pid: facteur_echelle(pid, SOURCE_SPECS["NISAR-SoilMoisture"]["resolution_m"])).values
    panel["vwc_evidence"] = valeur * fe
    panel["vwc_flag"] = flag
    return panel, True


# ===========================================================================
# 8. CORROBORATION NDVI DIFFÉRÉE & PROFIL AGRONOMIQUE PAR CULTURE
# ===========================================================================

PROFILS_CULTURES = {
    "ARBORICULTURE": {
        "mots_cles": ["amandier", "olivier", "caroubier", "verger", "arboriculture", "pêcher", "pommier", "agrumes"],
        "horizon_ndvi_jours": 14,
        "fenetre_besoin_apres_jours": 7,
        "description": "Arbres fruitier/oliveraie : biomasse pérenne et réponse foliaire plus lente (14j horizon NDVI)."
    },
    "AROMATIQUE_ARBUSTIF": {
        "mots_cles": ["lavande", "romarin", "géranium", "sauge", "citronnelle", "verveine", "thym", "aromatique"],
        "horizon_ndvi_jours": 10,
        "fenetre_besoin_apres_jours": 5,
        "description": "Plantes aromatiques/arbustives méditerranéennes : croissance moyenne (10j horizon NDVI)."
    },
    "MARAICHAGE": {
        "mots_cles": ["tomate", "piment", "poivron", "légume", "maraîchage", "courgette", "melon", "pastèque", "fraise"],
        "horizon_ndvi_jours": 8,
        "fenetre_besoin_apres_jours": 4,
        "description": "Cultures maraîchères à cycle court : réponse foliaire rapide (8j horizon NDVI)."
    },
    "GRANDES_CULTURES": {
        "mots_cles": ["maïs", "blé", "orge", "céréale", "tournesol", "colza", "soja", "luzerne"],
        "horizon_ndvi_jours": 12,
        "fenetre_besoin_apres_jours": 5,
        "description": "Grandes cultures : réponse biomasse dynamique en phase végétative (12j horizon NDVI)."
    },
    "SOL_NU": {
        "mots_cles": ["sol nu", "aucune", "bare", "none", "sans culture"],
        "horizon_ndvi_jours": 0,  # Désactivé : pas de réponse biomasse sur sol nu !
        "fenetre_besoin_apres_jours": 3,
        "description": "Sol nu / pas de culture : corroboration NDVI désactivée."
    }
}

PROFIL_DEFAULT = {
    "horizon_ndvi_jours": 10,
    "fenetre_besoin_apres_jours": 5,
    "description": "Profil agronomique par défaut (10j horizon NDVI)."
}


def classifier_culture(culture_str):
    """Retourne la clé de profil et le dictionnaire de paramétrage agronomique pour une culture donnée."""
    if not isinstance(culture_str, str) or not culture_str.strip():
        return "DEFAULT", PROFIL_DEFAULT
    c_lower = culture_str.lower()
    for key, spec in PROFILS_CULTURES.items():
        if any(kw in c_lower for kw in spec["mots_cles"]):
            return key, spec
    return "DEFAULT", PROFIL_DEFAULT


def evidence_ndvi_differee(panel, colonne_ndvi, poids_max=0.5, horizon_jours_defaut=21, seuil_delta=0.03, early_stop=True):
    """Corroboration différée NDVI/fCover optimisée :
    1. Horizon adapté dynamiquement au profil de la culture (14j arbres, 10j aromatiques, 8j légumes, 0j sol nu).
    2. Atténuation temporelle (Time-Decay Weighting) : un verdissement précoce (J+2 à J+5) conserve ~100%
       du bonus, un verdissement tardif subit une dépréciation linéaire jusqu'à 50%.
    3. Validation précoce (Early-Stop) : dès la 1ère observation sans nuage validant ΔNDVI >= seuil,
       la recherche s'arrête pour éviter de capter le bruit phénologique ou des pluies ultérieures.
    4. Jamais déclencheur autonome : le bonus n'est appliqué que si score_composite > 0.
    
    ⚠️ AVERTISSEMENT ML / PHASE 2 : Cette fonction effectue une corroboration rétrospective
    (utilise les observations à J+N après l'événement). La colonne générée ne doit JAMAIS
    être injectée comme feature directe dans un modèle prédictif temps-réel sans décalage temporel (lag causal).
    """
    if colonne_ndvi not in panel.columns:
        return panel, False
    col_out = f"{colonne_ndvi}_corrobore"
    panel[col_out] = 0.0

    culture_col = "culture" if "culture" in panel.columns else None

    for parcel_id, g in panel.groupby("parcel_id"):
        gg = g.sort_values("date")
        dates = gg["date"].values
        ndvi = gg[colonne_ndvi].values
        idx_orig = gg.index.values
        cultures = gg[culture_col].values if culture_col else [None] * len(gg)

        for i in range(len(dates)):
            cult = cultures[i]
            _, spec_cult = classifier_culture(cult)
            horizon_j = spec_cult["horizon_ndvi_jours"] if horizon_jours_defaut == 21 else horizon_jours_defaut

            if horizon_j <= 0 or pd.isna(ndvi[i]):
                continue

            max_date = dates[i] + np.timedelta64(horizon_j, "D")
            futur_mask = (dates > dates[i]) & (dates <= max_date)

            if futur_mask.sum() == 0 or np.all(pd.isna(ndvi[futur_mask])):
                continue

            indices_futur = np.where(futur_mask)[0]

            poids_attribue = 0.0
            for idx_f in indices_futur:
                val_f = ndvi[idx_f]
                if pd.isna(val_f):
                    continue
                delta = val_f - ndvi[i]
                if delta >= seuil_delta:
                    delai_j = float((dates[idx_f] - dates[i]) / np.timedelta64(1, "D"))
                    facteur_decay = max(0.5, 1.0 - 0.5 * (delai_j / max(1, horizon_j)))
                    poids_attribue = poids_max * facteur_decay
                    if early_stop:
                        break

            if poids_attribue > 0:
                panel.loc[idx_orig[i], col_out] = round(poids_attribue, 3)

    return panel, True


# ===========================================================================
# 9. SCORE COMPOSITE PAR PARCELLE x DATE
# ===========================================================================

POIDS_MAX_PAR_FAMILLE = {
    "S2-Indices": 2.5,          # Tous les indices S2 combinés <= 2.5 pts au total (1 passage satellite)
    "Thermique-LST": 2.0,       # TOUS les capteurs thermiques combinés (ECOSTRESS/Landsat/MODIS) <= 2.0 pts
    "S1-SAR": 2.5,
    "NISAR-SoilMoisture": 3.0,
    "NISAR-Backscatter": 2.0,
}


def calculer_score_composite(panel, ndvi_ref_col="NDVI_Landsat"):
    """Combine toutes les colonnes '*_evidence' avec un plafonnement anti-redondance
    par famille de capteurs physiques (POIDS_MAX_PAR_FAMILLE) : les indices multiples
    dérivés d'un même passage satellite (ex: 6 indices S2) ne peuvent pas dépasser
    le plafond de leur famille (ex: 2.5 pts). Pour atteindre un score élevé (>=3.0),
    au moins 2 capteurs physiques indépendants doivent corroborer l'événement.
    """
    # BUG CORRIGÉ (2026-08-14) : depuis l'ajout du module stress hydrique dans
    # detect_besoin_vs_irrigation.py, le panel fusionné contient AUSSI des
    # colonnes "stress_*_evidence" (sécheresse, calculées par calculer_score_stress)
    # à côté des colonnes d'IRRIGATION (hydratation) que cette fonction est censée
    # agréger. Sans exclusion explicite, le filtre "se termine par _evidence" les
    # confond : au premier appel (panel encore sans les colonnes stress, cas du
    # tout premier run "calcul complet") le score est correct, mais dès que la
    # fonction est rappelée sur le panel COMPLET (cas --from-cache, où les
    # colonnes stress ont déjà été ajoutées), les preuves de sécheresse sont
    # additionnées aux preuves d'irrigation -- deux notions opposées mélangées.
    COLONNES_DERIVEES_NON_PREUVE = {"n_sources_evidence"}
    evidence_cols = [c for c in panel.columns if c.endswith("_evidence")
                      and c != "sources_evidence" and c not in COLONNES_DERIVEES_NON_PREUVE
                      and not c.startswith("stress_")]
    ndvi_median_par_parcelle = (panel.groupby("parcel_id")[ndvi_ref_col].median()
                                 if ndvi_ref_col in panel.columns else pd.Series(dtype=float))

    panel["score_composite"] = 0.0
    panel["sources_evidence"] = [[] for _ in range(len(panel))]

    # Regroupement des colonnes par famille de capteur physique
    familles_active_cols = {}
    for col in evidence_cols:
        label = col.replace("_evidence", "")
        famille = FAMILLE_CAPTEUR.get(label, "AUTRE")
        familles_active_cols.setdefault(famille, []).append(col)

    # Addition plafonnée par famille de capteur
    for famille, cols_fam in familles_active_cols.items():
        score_famille = pd.Series(0.0, index=panel.index)
        for col in cols_fam:
            label = col.replace("_evidence", "")
            val_col = panel[col].fillna(0).copy()
            if label in ("VV_dB", "HH_gamma0_dB"):
                poids_facteur = panel.apply(
                    lambda r: 0.4 if est_faible_couvert(
                        r.get("culture"), ndvi_median_par_parcelle.get(r["parcel_id"], np.nan)) else 1.0,
                    axis=1)
                val_col = val_col * poids_facteur
            score_famille += val_col

            actif = val_col > 0
            for i in panel.index[actif]:
                if label not in panel.at[i, "sources_evidence"]:
                    panel.at[i, "sources_evidence"].append(label)

        cap_famille = POIDS_MAX_PAR_FAMILLE.get(famille, 3.0)
        panel["score_composite"] += score_famille.clip(upper=cap_famille)

    # Corroboration différée (NDVI/fCover, cf. evidence_ndvi_differee)
    corrobore_cols = [c for c in panel.columns if c.endswith("_corrobore")]
    for col in corrobore_cols:
        label = col.replace("_corrobore", "") + "_corrobore"
        deja_actif = panel["score_composite"] > 0
        valeur = np.where(deja_actif, panel[col].fillna(0), 0.0)
        valeur_clip = np.minimum(valeur, 0.5)
        panel["score_composite"] += valeur_clip
        actif = valeur_clip > 0
        for i in panel.index[actif]:
            if label not in panel.at[i, "sources_evidence"]:
                panel.at[i, "sources_evidence"].append(label)

    panel["n_sources_evidence"] = panel["sources_evidence"].apply(len)

    panel["capteurs_independants"] = [set() for _ in range(len(panel))]
    for col in evidence_cols:
        label = col.replace("_evidence", "")
        famille = FAMILLE_CAPTEUR.get(label)
        if famille is None:
            continue
        actif = panel[col].fillna(0) > 0
        for i in panel.index[actif]:
            panel.at[i, "capteurs_independants"].add(famille)
    panel["n_capteurs_independants"] = panel["capteurs_independants"].apply(len)
    panel["capteurs_independants"] = panel["capteurs_independants"].apply(lambda s: sorted(s))
    return panel


# ===========================================================================
# 10. CLASSIFICATION PLUIE / IRRIGATION (Section D du rapport, INCHANGÉE)
# ===========================================================================

def saison(date):
    return "hiver" if date.month in (11, 12, 1, 2, 3) else "ete"


def classifier_jour(date_evt, site, precip):
    s = saison(date_evt)
    if precip is None or site not in precip.site.unique():
        return {"saison": s, "precip_avant_mm": None, "precip_ambiante_mm": None,
                "STATUT": f"INDETERMINE — pluie inconnue pour '{site}' (ne pas interpréter comme 0 mm)"}
    p_avant = cumul_precip_avant(precip, site, date_evt)
    p_ambiant = cumul_precip_ambiant(precip, site, date_evt)
    if p_avant is None or p_ambiant is None:
        return {"saison": s, "precip_avant_mm": None, "precip_ambiante_mm": None,
                "STATUT": f"INDETERMINE — pas de donnée pluie pour '{site}' à cette date"}
    regime_humide = p_ambiant >= SEUIL_AMBIANT_HUMIDE_MM
    if p_avant >= SEUIL_PLUIE_MM:
        statut = "PLUIE_PROBABLE"
    elif not regime_humide:
        statut = ("IRRIGATION_PROBABLE (confiance haute — saison sèche, aucune pluie proche)" if s == "ete"
                   else "IRRIGATION_PROBABLE (confiance moyenne)")
    else:
        statut = "IRRIGATION_POSSIBLE (confiance BASSE — régime ambiant humide, pluie locale non exclue)"
    return {"saison": s, "precip_avant_mm": round(p_avant, 1),
            "precip_ambiante_mm": round(p_ambiant, 1), "STATUT": statut}


# ===========================================================================
# 11. VALIDATION SUR ÉVÉNEMENT(S) CONNU(S)
# ===========================================================================

def resume_pixel_pour_parcelle(sources_brutes, parcel_id, fenetre):
    """Applique le module pixel (SAR/NISAR-Backscatter) sur UNE parcelle,
    si les fichiers correspondants sont disponibles. Retourne un dict de
    résumés (une entrée par source pixel dispo) pour affichage/validation."""
    resumes = {}
    for source, spec in SOURCES_PIXEL_PIC.items():
        if source not in sources_brutes:
            continue
        sub = sources_brutes[source]
        sub = sub[sub.parcel_id == parcel_id]
        if sub.empty:
            continue
        wide, ref, n_pixels = construire_serie_pixels(sub, spec["colonne"])
        if wide.empty:
            continue
        res = detecter_pics_pixel(wide, seuil_db=spec["seuil_db"])
        fen = res.loc[fenetre[0]:fenetre[1]]
        if fen.empty:
            continue
        resumes[source] = {
            "n_pixels": n_pixels, "pct_max": fen["pct_pixels_pic"].max(),
            "ecart_max": fen["ecart_max"].max(),
            "jours_flagues": int((fen["pct_pixels_pic"] >= SEUIL_PCT_PIXELS).sum()),
        }
    return resumes


def validation_connue(panel, sources_brutes, precip):
    print("\n" + "=" * 80)
    print(" VALIDATION MULTI-CAPTEUR SUR ÉVÉNEMENT(S) CONNU(S)")
    print("=" * 80)

    sources_dispo = sorted(sources_brutes.keys())
    sources_absentes = sorted(set(SOURCE_SPECS) - set(sources_brutes.keys()))
    print(f"  Capteurs disponibles ce run : {sources_dispo}")
    if sources_absentes:
        print(f"  Capteurs ABSENTS ce run (module correspondant désactivé) : {sources_absentes}")

    for evt in EVENEMENTS_CONNUS:
        print(f"\n  --- {evt['nom']} ({evt['date_debut']} -> {evt['date_fin']}) ---")
        debut_fenetre = pd.Timestamp(evt["date_debut"]) - pd.Timedelta(days=10)
        fin_fenetre = pd.Timestamp(evt["date_fin"]) + pd.Timedelta(days=21)

        for parcel_id, label in evt["parcelles"].items():
            print(f"\n  {label} [{parcel_id}] :")
            sous_panel = panel[(panel.parcel_id == parcel_id) &
                                (panel.date >= debut_fenetre) & (panel.date <= fin_fenetre)].sort_values("date")
            if sous_panel.empty:
                print("    Aucune donnée dans le panel pour cette fenêtre.")
                continue

            # Module pixel (SAR / NISAR-Backscatter), si dispo
            resumes_pixel = resume_pixel_pour_parcelle(sources_brutes, parcel_id, (debut_fenetre, fin_fenetre))
            if resumes_pixel:
                for source, r in resumes_pixel.items():
                    print(f"    [{source}] {r['n_pixels']} pixels -- max {r['pct_max']:.1f}% des pixels en pic, "
                          f"écart max {r['ecart_max']:+.2f} dB, {r['jours_flagues']} jour(s) flagué(s) "
                          f"(seuil parcelle {SEUIL_PCT_PIXELS}%)")
            else:
                print("    [S1-SAR / NISAR-Backscatter] non disponible ce run.")

            # Modules thermiques
            for label_th, spec in SOURCES_THERMIQUES.items():
                col_anom = f"dTs_{label_th}_anomalie"
                if col_anom not in sous_panel.columns or sous_panel[col_anom].notna().sum() == 0:
                    continue
                for _, row in sous_panel.dropna(subset=[col_anom]).iterrows():
                    z = row.get(f"dTs_{label_th}_z_site")
                    z_txt = f", z_site={z:+.2f}" if pd.notna(z) else ""
                    flagge = "★ ÉVIDENCE" if row[col_anom] <= -SEUIL_CHUTE_DTS_C else "  (sous seuil)"
                    print(f"    [{label_th}] {row['date'].date()} : ΔTs={row[f'dTs_{label_th}']:+.2f}°C, "
                          f"anomalie vs baseline propre={row[col_anom]:+.2f}°C{z_txt} {flagge}")

            # Score composite jour par jour dans la fenêtre
            print("    Score composite (toutes preuves dispo, pondération adaptée au couvert) :")
            for _, row in sous_panel.iterrows():
                if row["score_composite"] <= 0:
                    continue
                classif = classifier_jour(row["date"], row["site"], precip)
                print(f"      {row['date'].date()} : score={row['score_composite']:.2f} "
                      f"(sources: {row['sources_evidence']}) -> {classif['STATUT']}")
            if (sous_panel["score_composite"] <= 0).all():
                print("    -> Score composite nul sur toute la fenêtre, quel que soit le capteur disponible : "
                      "AUCUNE preuve (radar, thermie, optique, humidité du sol -- selon disponibilité) ne "
                      "distingue cette période de la baseline propre à la parcelle.")

    # Témoin déjà irrigué
    print(f"\n  --- Témoin : {CONTROLE_DEJA_IRRIGUE['nom']} ---")
    ctrl_id = CONTROLE_DEJA_IRRIGUE["parcel_id"]
    sous_panel = panel[panel.parcel_id == ctrl_id].sort_values("date")
    if not sous_panel.empty:
        top = sous_panel.sort_values("score_composite", ascending=False).head(5)
        for _, row in top.iterrows():
            if row["score_composite"] <= 0:
                continue
            classif = classifier_jour(row["date"], row["site"], precip)
            print(f"    {row['date'].date()} : score={row['score_composite']:.2f} "
                  f"(sources: {row['sources_evidence']}) -> {classif['STATUT']}")
    else:
        print("    Aucune donnée pour ce témoin dans le panel.")


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    global SEUIL_SCORE_COMPOSITE, SEUIL_PCT_PIXELS, SEUIL_CHUTE_DTS_C
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR),
                     help=f"Dossier contenant les .parquet (recherche récursive). Défaut : {DEFAULT_DATA_DIR}")
    ap.add_argument("--precip", default=None, help="CSV date,site,precip_mm déjà préparé (désactive precip_mm/API)")
    ap.add_argument("--no-api", action="store_true", help="Ne pas appeler Open-Meteo en secours")
    ap.add_argument("--dry-run", action="store_true", help="Validation sur événement(s) connu(s) uniquement")
    ap.add_argument("--evidence-threshold", type=float, default=SEUIL_SCORE_COMPOSITE,
                     help=f"Score composite minimal pour flaguer un jour (défaut {SEUIL_SCORE_COMPOSITE})")
    ap.add_argument("--seuil-pct-sar", type=float, default=SEUIL_PCT_PIXELS,
                     help=f"%% minimum de pixels SAR/NISAR en pic pour flaguer un jour (défaut {SEUIL_PCT_PIXELS})")
    ap.add_argument("--dts-threshold", type=float, default=SEUIL_CHUTE_DTS_C,
                     help=f"Chute de ΔTs (°C) sous la baseline pour évoquer un refroidissement évaporatif "
                          f"(défaut {SEUIL_CHUTE_DTS_C})")
    ap.add_argument("--output", default="rapport_irrigation_vs_pluie.csv", help="Fichier CSV de sortie")
    ap.add_argument("--cache-panel", default=None,
                     help="Sauvegarde le panel (toutes preuves + score_composite déjà calculés) dans ce "
                          "fichier .pkl après ce run -- réutilisable avec --from-cache pour tester "
                          "plusieurs seuils SANS relire les .parquet ni refaire les calculs (rolling "
                          "baselines, k-d tree pixel, appel météo). Le score_composite ne dépend PAS du "
                          "seuil : seul le filtrage final en dépend, donc ce cache est valide pour "
                          "n'importe quel --evidence-threshold ultérieur.")
    ap.add_argument("--from-cache", default=None,
                     help="Charge le panel depuis un .pkl généré par --cache-panel (ignore --data-dir, "
                          "--precip, --no-api -- rien n'est relu). Usage typique : un premier run avec "
                          "--cache-panel pour construire le cache, puis N runs rapides avec "
                          "--from-cache + --evidence-threshold différent pour comparer des seuils.")
    args = ap.parse_args()
    SEUIL_SCORE_COMPOSITE = args.evidence_threshold
    SEUIL_PCT_PIXELS = args.seuil_pct_sar
    SEUIL_CHUTE_DTS_C = args.dts_threshold

    data_dir = Path(args.data_dir)
    cache_dir = data_dir / CACHE_DIR_NAME

    print("=" * 80)
    print(" DÉTECTEUR MULTI-CAPTEUR IRRIGATION vs PLUIE — v4")
    print("=" * 80)
    verifier_coherence_terrain()

    if args.from_cache:
        print(f"\n[CACHE] Chargement du panel pré-calculé depuis {args.from_cache} "
              f"-- aucune relecture des .parquet, aucun recalcul de preuve (--data-dir/--precip/"
              f"--no-api ignorés).")
        panel, precip = pd.read_pickle(args.from_cache)
        sources_brutes = {}
        print(f"  {len(panel)} lignes chargées, {panel.parcel_id.nunique()} parcelles.")
        panel = calculer_score_composite(panel)  # recalcule juste l'agrégation, pas les evidences (rapide)
    else:
        fichiers = decouvrir_fichiers(data_dir)
        sources_brutes = {source: charger_source(paths) for source, paths in fichiers.items()}

        df_meteo = sources_brutes.get("ERA5-Meteo")
        tous_sites = sorted(set().union(*[set(df.site.unique()) for df in sources_brutes.values()]))
        precip = obtenir_precipitation(df_meteo, tous_sites, cache_dir, csv_manuel=args.precip, use_api=not args.no_api)

        print("\n[PANEL] Construction du panel parcelle x date (fusion multi-capteur)...")
        panel = construire_panel(sources_brutes)
        print(f"  {len(panel)} lignes (parcelle x date), {panel.parcel_id.nunique()} parcelles, "
              f"colonnes disponibles : {[c for c in panel.columns if c not in ('site','parcel_id','date')]}")

    if not args.from_cache and "culture" in panel.columns:
        print("\n[TERRAIN] Croisement culture satellite <-> culture terrain (GeoJSON) :")
        for pid, meta in PARCELLES_TERRAIN.items():
            sous = panel.loc[panel.parcel_id == pid, "culture"].dropna()
            culture_sat = sous.iloc[0] if not sous.empty else None
            sat_mots = set(normaliser_mot_culture(w) for w in re.split(r"[/,;\s]+", culture_sat or ""))
            manquants = [c for c in meta["cultures_terrain"] if normaliser_mot_culture(c) not in sat_mots]
            if culture_sat is None or (isinstance(culture_sat, str) and not culture_sat.strip()):
                print(f"  [?] {pid} : pas de colonne 'culture' renseignée côté satellite "
                      f"(terrain : {', '.join(meta['cultures_terrain'])}) -- auto-rempli depuis GeoJSON.")
            elif manquants:
                print(f"  [!] {pid} : culture satellite = '{culture_sat}' vs terrain = "
                      f"{', '.join(meta['cultures_terrain'])} -- écart sur {', '.join(manquants)}.")
            else:
                print(f"  [✓] {pid} : culture satellite cohérente avec le terrain.")

    if args.from_cache:
        print("\n[PREUVES] Ignoré -- déjà calculées dans le panel mis en cache (c'est tout l'intérêt de "
              "--from-cache : ce run ne relit rien, ne refait aucune baseline glissante ni k-d tree).")
    else:
        print("\n[PREUVES] Calcul des modules d'évidence disponibles...")
        for label, spec in SOURCES_THERMIQUES.items():
            panel, actif = evidence_thermique(panel, label, spec["colonne"], spec["poids"],
                                               colonne_est_kelvin=spec.get("colonne_est_kelvin", False),
                                               resolution_m=SOURCE_SPECS[label]["resolution_m"])
            print(f"  [{'✓' if actif else ' '}] Thermique {label} (ΔTs = LST - Tmax_C)"
                  + ("" if actif else " -- colonne(s) absente(s), désactivé"))

        # MODULES_OPTIQUES est désormais une constante module (cf. tête de fichier,
        # à côté de FAMILLE_CAPTEUR) -- plus de copie locale possible à désynchroniser.
        for colonne, seuil, poids, sens_hausse, desc in MODULES_OPTIQUES:
            panel, actif = evidence_optique(panel, colonne, poids, seuil, sens_hausse=sens_hausse)
            sens_str = "hausse" if sens_hausse else "baisse"
            print(f"  [{'✓' if actif else ' '}] Optique {colonne} ({sens_str} ≥ {abs(seuil):g} -- {desc})"
                  + ("" if actif else " -- absent, désactivé"))

        panel, actif = evidence_humidite_sol(panel)
        print(f"  [{'✓' if actif else ' '}] Humidité du sol NISAR SME2 (soil_moisture_vol)" + ("" if actif else " -- absent, désactivé"))

        panel, actif = evidence_vwc_nisar(panel)
        print(f"  [{'✓' if actif else ' '}] Contenu en eau végétation NISAR L-band (vegetation_water_content)" + ("" if actif else " -- absent, désactivé"))

        for colonne_ndvi in ("NDVI_Landsat", "NDVI"):
            if colonne_ndvi in panel.columns:
                panel, _ = evidence_ndvi_differee(panel, colonne_ndvi)
                print(f"  [✓] Corroboration NDVI différée ({colonne_ndvi}, +0.5 max avec decay & early-stop par culture)")

        # Preuves pixel (SAR / NISAR-Backscatter) -> injectées dans le panel comme colonnes évidence
        for source, spec in SOURCES_PIXEL_PIC.items():
            if source not in sources_brutes:
                print(f"  [ ] Pixel {source} -- absent, désactivé")
                continue
            lignes = []
            for parcel_id, sub in sources_brutes[source].groupby("parcel_id"):
                wide, ref, n_pixels = construire_serie_pixels(sub, spec["colonne"])
                if wide.empty:
                    continue
                res = detecter_pics_pixel(wide, seuil_db=spec["seuil_db"])
                for date_evt, row in res.iterrows():
                    lignes.append({"parcel_id": parcel_id, "date": date_evt,
                                    f"{spec['colonne']}_pct_pixels_pic": row["pct_pixels_pic"]})
            if lignes:
                df_pix = pd.DataFrame(lignes)
                panel = panel.merge(df_pix, on=["parcel_id", "date"], how="left")
                flag = panel[f"{spec['colonne']}_pct_pixels_pic"] >= SEUIL_PCT_PIXELS
                panel[f"{spec['colonne']}_evidence"] = np.where(flag, spec["poids_defaut"], 0.0)
                print(f"  [✓] Pixel {source} ({spec['colonne']}) -- {flag.sum()} jour(s)*parcelle(s) au-dessus du "
                      f"seuil {SEUIL_PCT_PIXELS}% (poids nominal {spec['poids_defaut']}, réduit si sol nu/faible NDVI)")
            else:
                print(f"  [ ] Pixel {source} -- aucune série exploitable")

        panel = calculer_score_composite(panel)

        if args.cache_panel:
            pd.to_pickle((panel, precip), args.cache_panel)
            print(f"\n[CACHE] Panel complet (evidences + score_composite, indépendant du seuil) "
                  f"sauvegardé -> {args.cache_panel} -- réutilisable avec --from-cache pour tester "
                  f"d'autres seuils instantanément.")

    validation_connue(panel, sources_brutes, precip)

    if args.dry_run:
        return

    print("\n" + "=" * 80)
    print(" DÉTECTION SUR TOUTE LA PÉRIODE, TOUTES PARCELLES (multi-capteur)")
    print("=" * 80)
    flagues = panel[panel["score_composite"] >= SEUIL_SCORE_COMPOSITE].copy()
    lignes = []
    n_degrades = 0
    for _, row in flagues.iterrows():
        classif = classifier_jour(row["date"], row["site"], precip)
        capteurs_indep = row.get("capteurs_independants", [])
        # DÉGRADATION DE CONFIANCE (v4) : un jour porté par UN SEUL capteur
        # physique, et que ce capteur est MODIS-LST (1 km, très majoritairement
        # hors-parcelle sur Kemel/Yahia/Badreddine -- cf. facteur_echelle()),
        # ne doit jamais afficher "confiance haute/moyenne" même si le score
        # composite dépasse le seuil (le bonus corrobération z_site suffit à
        # franchir 1.2 à lui seul, ce qui n'est PAS une deuxième preuve
        # indépendante). On ne supprime pas la ligne, on rend la faiblesse de
        # la preuve visible dans le STATUT.
        if list(capteurs_indep) == ["MODIS-LST"] and classif["STATUT"].startswith("IRRIGATION_PROBABLE"):
            classif = dict(classif)
            classif["STATUT"] = ("IRRIGATION_POSSIBLE (confiance BASSE — MODIS-LST seul, 1 km/pixel, "
                                  "résolution trop grossière pour cette parcelle pour constituer une "
                                  "preuve à elle seule)")
            n_degrades += 1
        lignes.append({
            "site": row["site"], "parcel_id": row["parcel_id"],
            "culture": row.get("culture"), "date": row["date"].date(),
            "score_composite": round(row["score_composite"], 2),
            "n_sources_evidence": row["n_sources_evidence"],
            "sources_evidence": ";".join(row["sources_evidence"]),
            "n_capteurs_independants": row.get("n_capteurs_independants", row["n_sources_evidence"]),
            "capteurs_independants": ";".join(capteurs_indep) if isinstance(capteurs_indep, (list, set)) else capteurs_indep,
            **classif,
        })
    if n_degrades:
        print(f"\n  [i] {n_degrades} jour(s) dégradé(s) IRRIGATION_PROBABLE -> IRRIGATION_POSSIBLE "
              f"(confiance BASSE) car porté(s) uniquement par MODIS-LST (1 km).")
    rapport = pd.DataFrame(lignes)
    out_path = Path(args.output)
    rapport.to_csv(out_path, index=False)
    print(f"{len(rapport)} jour(s)*parcelle(s) flagué(s) (score >= {SEUIL_SCORE_COMPOSITE}) -> {out_path}")
    if not rapport.empty:
        print("\nRépartition des statuts :")
        print(rapport["STATUT"].value_counts().to_string())
        n_indetermine = rapport["STATUT"].str.startswith("INDETERMINE").sum()
        if n_indetermine:
            sites_touches = sorted(rapport.loc[rapport["STATUT"].str.startswith("INDETERMINE"), "site"].unique())
            print(f"\n  [!!] {n_indetermine} jour(s) INDETERMINE (pluie inconnue) sur {sites_touches} -- "
                  f"ne pas compter comme IRRIGATION_PROBABLE tant que la pluie de ces sites n'est pas résolue.")
    else:
        print("Aucun jour flagué -- vérifiez --evidence-threshold, ou l'étendue des capteurs disponibles "
              "(actuellement : " + ", ".join(sorted(sources_brutes.keys())) + ").")


if __name__ == "__main__":
    main()