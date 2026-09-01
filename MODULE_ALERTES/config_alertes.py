#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config_alertes.py
===================================================================
Registre central des 15 alertes agronomiques multi-sources, seuils,
familles de capteurs et calcul du score de confiance explicite.

Réutilisation stricte :
- Importe FAMILLE_CAPTEUR depuis detect_irrigation_vs_pluie_v3.py (IRRIGATION)
- Importe STADES_PHENOLOGIQUES_PAR_CULTURE, SEUIL_FCOVER_FAIBLE depuis config_sante.py (SANTE_PLANTES)
"""

import sys
import numpy as np
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = MODULE_DIR.parent
IRRIGATION_DIR = SCRIPTS_DIR / "IRRIGATION"
SANTE_DIR = SCRIPTS_DIR / "SANTE_PLANTES"

for p in [str(SCRIPTS_DIR), str(IRRIGATION_DIR), str(SANTE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Imports réutilisés
try:
    import detect_irrigation_vs_pluie_v3 as irr
    FAMILLE_CAPTEUR_BASE = irr.FAMILLE_CAPTEUR
except ImportError:
    FAMILLE_CAPTEUR_BASE = {
        "NDVI": "S2-Indices", "SAVI": "S2-Indices", "MSAVI": "S2-Indices",
        "NDRE": "S2-Indices", "NDWI": "S2-Indices", "NDMI": "S2-Indices", "BSI": "S2-Indices", "fCover": "S2-Indices",
        "CWSI_proxy": "Thermique-LST", "SMI": "Thermique-LST", "LST_K": "Thermique-LST",
        "soil_moisture_vol": "NISAR-SoilMoisture", "soil_moisture_qc": "NISAR-SoilMoisture",
        "VV_dB": "S1-SAR"
    }

try:
    import config_sante as cfg_sante
    STADES_PHENOLOGIQUES_PAR_CULTURE = cfg_sante.STADES_PHENOLOGIQUES_PAR_CULTURE
    SEUIL_FCOVER_FAIBLE = cfg_sante.SEUIL_FCOVER_FAIBLE
    SEUIL_FCOVER_MOYEN = cfg_sante.SEUIL_FCOVER_MOYEN
except ImportError:
    STADES_PHENOLOGIQUES_PAR_CULTURE = {}
    SEUIL_FCOVER_FAIBLE = 0.05
    SEUIL_FCOVER_MOYEN = 0.15


# Extension des familles de capteurs (implementation_plan_v2.md §4.3)
FAMILLE_CAPTEUR_ALERTES = {
    **FAMILLE_CAPTEUR_BASE,
    "CI_RedEdge": "S2-Indices",
    "EVI": "S2-Indices",
    "VARI": "S2-Indices",
    "GDD_cumul": "ERA5-Meteo",
    "precip_mm": "ERA5-Meteo",
    "Tmax_C": "ERA5-Meteo",
    "Tmin_C": "ERA5-Meteo",
    "LST_ECOSTRESS_C": "Thermique-LST",
    "VH_dB": "S1-SAR",
    "VH_VV_ratio": "S1-SAR",
    "DpRVIc": "S1-SAR",
    "vegetation_water_content": "NISAR-SoilMoisture",
}


def compter_familles_independantes(cols_utilisees: list) -> int:
    """Compte le nombre de familles de capteurs distinctes réelles dans la liste de colonnes."""
    familles = set()
    for col in cols_utilisees:
        fam = FAMILLE_CAPTEUR_ALERTES.get(col)
        if fam:
            familles.add(fam)
    return len(familles)


def calculer_score_confiance_alerte(
    n_familles: int,
    facteur_echelle: float = 1.0,
    fraicheur_jours: int = 0,
    multi_passage_valide: bool = False
) -> dict:
    """
    Calcule le score de confiance explicite (0 à 100%) selon §7 :
    - Nombre de familles (40%) : 1 fam = 0%, 2 fam = 70% de 40 (28%), 3+ fam = 100% de 40 (40%)
    - Facteur d'échelle (25%) : 25 * min(1.0, max(0.15, facteur_echelle))
    - Fraîcheur des données (20%) : <=3j = 20%, <=7j = 15%, <=14j = 10%, >14j = 0%
    - Confirmation multi-passage (15%) : 15% si True, 0% si False

    Règle absolue : Si n_familles == 1, le score total est plafonné à 69% (jamais Confiance Haute).
    """
    # 1. Familles (40%)
    if n_familles <= 1:
        part_familles = 0.0
    elif n_familles == 2:
        part_familles = 28.0
    else:
        part_familles = 40.0

    # 2. Facteur d'échelle (25%)
    fe_effective = max(0.15, min(1.0, float(facteur_echelle)))
    part_echelle = 25.0 * fe_effective

    # 3. Fraîcheur (20%)
    if fraicheur_jours <= 3:
        part_fraicheur = 20.0
    elif fraicheur_jours <= 7:
        part_fraicheur = 15.0
    elif fraicheur_jours <= 14:
        part_fraicheur = 10.0
    else:
        part_fraicheur = 0.0

    # 4. Multi-passage (15%)
    part_multipassage = 15.0 if multi_passage_valide else 0.0

    score_raw = part_familles + part_echelle + part_fraicheur + part_multipassage

    # Plafond strict si 1 seule famille
    if n_familles <= 1:
        score_final = min(69.0, score_raw)
    else:
        score_final = min(100.0, score_raw)

    score_final = float(np.round(score_final, 1))
    qualite = "HAUTE" if score_final >= 70.0 else ("MOYENNE" if score_final >= 50.0 else "BASSE")

    explanation = []
    if n_familles <= 1:
        explanation.append("1 seule famille de capteur (plafonné < 70%)")
    if fe_effective < 0.5:
        explanation.append(f"Signal fortement dilué (facteur d'échelle {fe_effective:.2f})")
    if fraicheur_jours > 7:
        explanation.append(f"Données anciennes ({fraicheur_jours} jours)")

    message_explanation = " - ".join(explanation) if explanation else "Signal pleinement corroboré multi-familles"

    return {
        "score_confiance": score_final,
        "niveau_confiance": qualite,
        "n_familles": n_familles,
        "facteur_echelle": fe_effective,
        "explication_confiance": message_explanation
    }


# Registre des 15 alertes
REGISTRE_ALERTES = {
    # Catégorie A : Risques Naturels (7 alertes)
    "ALERTE_1_STRESS_HYDRIQUE": {
        "id": 1,
        "nom": "Stress hydrique",
        "categorie": "A_RISQUES_NATURELS",
        "gravite_defaut": "AVERTISSEMENT",
        "gravite_critique_condition": "jeune_plantation_ou_nouaison",
        "cols": ["NDWI", "NDMI", "CWSI_proxy", "soil_moisture_vol", "fCover"],
        "min_familles_haute_confiance": 2
    },
    "ALERTE_2_STRESS_AZOTE_FORT": {
        "id": 2,
        "nom": "Stress azoté fort",
        "categorie": "A_RISQUES_NATURELS",
        "gravite_defaut": "AVERTISSEMENT",
        "gravite_critique_condition": "persistant_2_passages_sans_fertilisation",
        "cols": ["CI_RedEdge", "NDRE", "NDWI", "NDMI", "fCover"],
        "min_familles_haute_confiance": 1
    },
    "ALERTE_3_STRESS_COMBINE_EAU_AZOTE": {
        "id": 3,
        "nom": "Stress combiné eau + azote",
        "categorie": "A_RISQUES_NATURELS",
        "gravite_defaut": "CRITIQUE",
        "gravite_critique_condition": "toujours_critique_hors_dormance",
        "cols": ["CI_RedEdge", "NDRE", "NDWI", "CWSI_proxy", "fCover"],
        "min_familles_haute_confiance": 2
    },
    "ALERTE_4_STRESS_THERMIQUE_CANICULE": {
        "id": 4,
        "nom": "Stress thermique / canicule",
        "categorie": "A_RISQUES_NATURELS",
        "gravite_defaut": "AVERTISSEMENT",
        "gravite_critique_condition": "floraison_nouaison",
        "cols": ["Tmax_C", "LST_ECOSTRESS_C", "LST_K", "fCover"],
        "min_familles_haute_confiance": 1
    },
    "ALERTE_5_EXCES_HUMIDITE_ENGORGEMENT": {
        "id": 5,
        "nom": "Excès d'humidité / engorgement",
        "categorie": "A_RISQUES_NATURELS",
        "gravite_defaut": "AVERTISSEMENT",
        "gravite_critique_condition": "sol_argileux_jeune_plant",
        "cols": ["NDWI", "precip_mm", "soil_moisture_vol", "VV_dB"],
        "min_familles_haute_confiance": 2
    },
    "ALERTE_6_SECHERESSE_PROLONGEE": {
        "id": 6,
        "nom": "Sécheresse prolongée",
        "categorie": "A_RISQUES_NATURELS",
        "gravite_defaut": "AVERTISSEMENT",
        "gravite_critique_condition": "non_irriguee_en_ete",
        "cols": ["precip_mm", "NDVI", "SAVI", "soil_moisture_vol"],
        "min_familles_haute_confiance": 2
    },
    "ALERTE_7_ANOMALIE_NON_ATTRIBUEE": {
        "id": 7,
        "nom": "Anomalie non attribuée (maladie/ravageur potentiel)",
        "categorie": "A_RISQUES_NATURELS",
        "gravite_defaut": "CRITIQUE",
        "gravite_critique_condition": "toujours_critique",
        "cols": ["NDVI", "NDRE", "VARI"],
        "min_familles_haute_confiance": 1
    },

    # Catégorie B : Comparaison (3 alertes)
    "ALERTE_8_ECART_EAU_REEL_VS_BESOIN": {
        "id": 8,
        "nom": "Écart apport eau réel vs. besoin théorique",
        "categorie": "B_COMPARAISON",
        "gravite_defaut": "AVERTISSEMENT",
        "gravite_critique_condition": "pointe_de_besoin",
        "cols": ["Tmax_C", "Tmin_C", "precip_mm", "fCover"],
        "min_familles_haute_confiance": 1
    },
    "ALERTE_9_ECART_STADE_PHENOLOGIQUE": {
        "id": 9,
        "nom": "Écart stade phénologique observé vs. attendu",
        "categorie": "B_COMPARAISON",
        "gravite_defaut": "INFORMATION",
        "gravite_critique_condition": "impact_operationnel",
        "cols": ["NDVI", "NDRE", "fCover"],
        "min_familles_haute_confiance": 1
    },
    "ALERTE_10_ECART_OCCUPATION_REELLE_VS_DECLAREES": {
        "id": 10,
        "nom": "Écart occupation réelle vs. déclarée",
        "categorie": "B_COMPARAISON",
        "gravite_defaut": "CRITIQUE",
        "gravite_critique_condition": "toujours_critique",
        "cols": ["NDVI", "BSI", "fCover"],
        "min_familles_haute_confiance": 1
    },

    # Catégorie C : Cohérence Registre / Satellite (5 alertes)
    "ALERTE_11_RECOLTE_DESHERBAGE_SANS_CHANGEMENT": {
        "id": 11,
        "nom": "Récolte/désherbage déclaré terminé, signal inchangé",
        "categorie": "C_COHERENCE_REGISTRE",
        "gravite_defaut": "AVERTISSEMENT",
        "gravite_critique_condition": "repete",
        "cols": ["NDVI"],
        "min_familles_haute_confiance": 1
    },
    "ALERTE_12_PLANTATION_SANS_LEVEE": {
        "id": 12,
        "nom": "Plantation déclarée sans levée détectée",
        "categorie": "C_COHERENCE_REGISTRE",
        "gravite_defaut": "AVERTISSEMENT",
        "gravite_critique_condition": "delai_superieur_2x_attendu",
        "cols": ["SAVI", "NDVI"],
        "min_familles_haute_confiance": 1
    },
    "ALERTE_13_IRRIGATION_SANS_REPONSE_HYDRIQUE": {
        "id": 13,
        "nom": "Irrigation déclarée sans réponse hydrique",
        "categorie": "C_COHERENCE_REGISTRE",
        "gravite_defaut": "CRITIQUE",
        "gravite_critique_condition": "toujours_critique",
        "cols": ["NDWI", "NDMI", "soil_moisture_vol"],
        "min_familles_haute_confiance": 1
    },
    "ALERTE_14_COUPE_PAM_SANS_SAUT_NDVI": {
        "id": 14,
        "nom": "Coupe PAM déclarée sans ΔNDVI caractéristique",
        "categorie": "C_COHERENCE_REGISTRE",
        "gravite_defaut": "AVERTISSEMENT",
        "gravite_critique_condition": "non_critique",
        "cols": ["NDVI", "NDRE"],
        "min_familles_haute_confiance": 1
    },
    "ALERTE_15_CHANGEMENT_DETECTE_SANS_TACHE": {
        "id": 15,
        "nom": "Changement détecté sans tâche (Déclassifiée)",
        "categorie": "C_COHERENCE_REGISTRE",
        "gravite_defaut": "INFORMATION",
        "gravite_critique_condition": "non_applicable",
        "cols": ["NDVI", "BSI", "VV_dB"],
        "min_familles_haute_confiance": 1,
        "statut_declassification": "DECLASSIFIEE_COUVERT_PAR_7_ET_10",
        "note_declassification": "Couvert par Alerte #7 (anomalie spectrale non attribuée) + Alerte #10 (écart d'occupation réelle vs déclarée)."
    }
}
