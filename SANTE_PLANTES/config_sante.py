#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config_sante.py
===================================================================
Configuration centrale pour le module Santé des Plantes AWAM.
Rassemble les seuils, profils agronomiques, stades phénologiques (issus de
stade_phenologique_des_cultures_sites_WWC.xlsx et INDICES_SATELLITE_PAR_CULTURE_AWAM.xlsx),
pondérations de l'Indice AWAM, et métadonnées sol/climat.
"""

import math

# ===========================================================================
# 1. MODES DE CONFIANCE & SEUILS DE COUVERTURE (fCover)
# ===========================================================================
# Contrairement à un blocage strict (gate), TOUS LES INDICES SONT TOUJOURS CALCULÉS,
# mais chaque score et l'Indice AWAM final sont estampillés avec leur niveau de confiance.
SEUIL_FCOVER_FAIBLE = 0.05    # < 5% fCover : Confiance BASSE (signal fortement faussé par sol nu)
SEUIL_FCOVER_MOYEN  = 0.15    # 5% - 15% fCover : Confiance MOYENNE (ANOMALIE_AUTO_REFERENCEE)
                              # >= 15% fCover : Confiance HAUTE (DIAGNOSTIC_COMPLET)

MODES_CONFIANCE_INFO = {
    "SUIVI_BRUT": {
        "fcover_range": (0.0, 0.05),
        "confiance_label": "BASSE",
        "description": "Occupation très faible (<5%). fCover/LAI directement mesurables, indices optiques (NDVI/EVI) fortement dominés par le sol."
    },
    "ANOMALIE_AUTO_REFERENCEE": {
        "fcover_range": (0.05, 0.15),
        "confiance_label": "MOYENNE",
        "description": "Occupation modérée (5-15%). NDRE et NDMI restent informatifs. NDVI à lire avec prudence."
    },
    "DIAGNOSTIC_COMPLET": {
        "fcover_range": (0.15, 1.0),
        "confiance_label": "HAUTE",
        "description": "Couvert végétal suffisant (>=15%). Signal optique propre, tous les indices pleinement représentatifs."
    }
}

# ===========================================================================
# 2. PONDÉRATIONS PAR DÉFAUT DE L'INDICE DE SANTÉ AWAM
# ===========================================================================
POIDS_SANTE_AWAM_DEFAUT = {
    "score_vigueur_vegetative": 0.20,
    "score_chlorophylle":        0.15,
    "score_stress_hydrique":     0.20,
    "score_couverture_canopee":  0.15,
    "score_suivi_phenologique":  0.10,
    "score_detection_anomalie":  0.10,
    "score_risque_maladie":      0.10,
}

# ===========================================================================
# 3. SEUILS POUR PASTILLES DE SANTÉ
# ===========================================================================
SEUIL_PASTILLE_SAIN      = 70.0  # Score >= 70 : 🟢 SAIN
SEUIL_PASTILLE_ATTENTION = 50.0  # 50 <= Score < 70 : 🟡 ATTENTION
                                 # Score < 50 : 🔴 CRITIQUE

# ===========================================================================
# 4. EXTINCTION K_LAI PAR CULTURE (Loi de Beer-Lambert : LAI = -ln(1-fCover)/k)
# ===========================================================================
K_EXTINCTION_CULTURE = {
    "Amandier": 0.50,
    "Olivier": 0.55,
    "Caroubier": 0.50,
    "Lavande": 0.45,
    "Romarin": 0.45,
    "Géranium": 0.50,
    "Sauge": 0.45,
    "Verveine": 0.50,
    "Thym": 0.40,
    "Citronnelle": 0.60,
    "Basilic": 0.55,
    "Menthe": 0.60,
    "Piment": 0.60,
    "Oignon": 0.50,
    "DEFAULT": 0.50
}

# ===========================================================================
# 5. TABLE DES STADES PHÉNOLOGIQUES DE RÉFÉRENCE ET SEUILS PAR CULTURE
#    Source : Alignement entre stade_phenologique_des_cultures_sites_WWC.xlsx
#    et INDICES_SATELLITE_PAR_CULTURE_AWAM.xlsx (Onglet 7)
# ===========================================================================
STADES_PHENOLOGIQUES_PAR_CULTURE = {
    "Geranium": [
        {"stade": "Croissance ralentie", "mois": [11, 12, 1, 2], "ndvi_min": 0.15, "ndvi_max": 0.25, "ndre_min": 0.06, "ndre_max": 0.12},
        {"stade": "Débourrement / reprise", "mois": [3], "ndvi_min": 0.20, "ndvi_max": 0.30, "ndre_min": 0.08, "ndre_max": 0.15},
        {"stade": "Croissance végétative", "mois": [3, 4, 5], "ndvi_min": 0.25, "ndvi_max": 0.35, "ndre_min": 0.10, "ndre_max": 0.20},
        {"stade": "Floraison & Récoltes", "mois": [5, 6, 7, 8, 9], "ndvi_min": 0.30, "ndvi_max": 0.45, "ndre_min": 0.15, "ndre_max": 0.28},
        {"stade": "Repos automnal", "mois": [10], "ndvi_min": 0.18, "ndvi_max": 0.28, "ndre_min": 0.08, "ndre_max": 0.15},
    ],
    "Lavande": [
        {"stade": "Dormance hivernale", "mois": [12, 1, 2], "ndvi_min": 0.08, "ndvi_max": 0.15, "ndre_min": 0.04, "ndre_max": 0.09},
        {"stade": "Débourrement & croissance", "mois": [3, 4, 5], "ndvi_min": 0.15, "ndvi_max": 0.25, "ndre_min": 0.08, "ndre_max": 0.16},
        {"stade": "Floraison & Maturation", "mois": [6, 7], "ndvi_min": 0.25, "ndvi_max": 0.35, "ndre_min": 0.14, "ndre_max": 0.22},
        {"stade": "Récolte", "mois": [6, 7, 8], "ndvi_min": 0.15, "ndvi_max": 0.30, "ndre_min": 0.08, "ndre_max": 0.18},
        {"stade": "Après-récolte (taille)", "mois": [8, 9, 10, 11], "ndvi_min": 0.10, "ndvi_max": 0.18, "ndre_min": 0.05, "ndre_max": 0.12},
    ],
    "Romarin": [
        {"stade": "Croissance ralentie", "mois": [11, 12, 1], "ndvi_min": 0.20, "ndvi_max": 0.30, "ndre_min": 0.08, "ndre_max": 0.14},
        {"stade": "Débourrement", "mois": [2, 3], "ndvi_min": 0.25, "ndvi_max": 0.35, "ndre_min": 0.10, "ndre_max": 0.18},
        {"stade": "Floraison & Croissance", "mois": [3, 4, 5], "ndvi_min": 0.30, "ndvi_max": 0.45, "ndre_min": 0.15, "ndre_max": 0.25},
        {"stade": "Coupes successives", "mois": [4, 5, 6, 7, 8, 9, 10], "ndvi_min": 0.25, "ndvi_max": 0.40, "ndre_min": 0.12, "ndre_max": 0.22},
        {"stade": "Creux estival", "mois": [7, 8], "ndvi_min": 0.20, "ndvi_max": 0.32, "ndre_min": 0.09, "ndre_max": 0.16},
    ],
    "Sauge": [
        {"stade": "Dormance hivernale", "mois": [12, 1, 2], "ndvi_min": 0.08, "ndvi_max": 0.15, "ndre_min": 0.04, "ndre_max": 0.08},
        {"stade": "Débourrement & croissance", "mois": [3, 4, 5], "ndvi_min": 0.15, "ndvi_max": 0.25, "ndre_min": 0.07, "ndre_max": 0.15},
        {"stade": "Floraison & Production foliaire", "mois": [5, 6], "ndvi_min": 0.25, "ndvi_max": 0.38, "ndre_min": 0.12, "ndre_max": 0.22},
        {"stade": "Récoltes foliaires", "mois": [4, 5, 6, 7, 8, 9, 10], "ndvi_min": 0.20, "ndvi_max": 0.35, "ndre_min": 0.10, "ndre_max": 0.20},
        {"stade": "Taille automnale", "mois": [10, 11], "ndvi_min": 0.10, "ndvi_max": 0.20, "ndre_min": 0.05, "ndre_max": 0.10},
    ],
    "Verveine": [
        {"stade": "Repos hivernal", "mois": [12, 1, 2], "ndvi_min": 0.10, "ndvi_max": 0.18, "ndre_min": 0.05, "ndre_max": 0.10},
        {"stade": "Débourrement", "mois": [3], "ndvi_min": 0.18, "ndvi_max": 0.28, "ndre_min": 0.08, "ndre_max": 0.14},
        {"stade": "Croissance & Feuillaison", "mois": [3, 4, 5], "ndvi_min": 0.25, "ndvi_max": 0.40, "ndre_min": 0.12, "ndre_max": 0.22},
        {"stade": "Floraison & Coupes", "mois": [6, 7, 8, 9], "ndvi_min": 0.28, "ndvi_max": 0.45, "ndre_min": 0.14, "ndre_max": 0.25},
        {"stade": "Taille hivernale", "mois": [10, 11], "ndvi_min": 0.12, "ndvi_max": 0.22, "ndre_min": 0.06, "ndre_max": 0.12},
    ],
    "Thym": [
        {"stade": "Végétation ralentie", "mois": [12, 1, 2], "ndvi_min": 0.10, "ndvi_max": 0.20, "ndre_min": 0.05, "ndre_max": 0.10},
        {"stade": "Croissance", "mois": [2, 3], "ndvi_min": 0.15, "ndvi_max": 0.28, "ndre_min": 0.07, "ndre_max": 0.14},
        {"stade": "Floraison / Coupe 1", "mois": [4, 5], "ndvi_min": 0.25, "ndvi_max": 0.35, "ndre_min": 0.12, "ndre_max": 0.20},
        {"stade": "Repos estival", "mois": [6, 7, 8], "ndvi_min": 0.10, "ndvi_max": 0.20, "ndre_min": 0.05, "ndre_max": 0.10},
        {"stade": "Regain / Coupe 2", "mois": [9, 10], "ndvi_min": 0.15, "ndvi_max": 0.25, "ndre_min": 0.07, "ndre_max": 0.13},
    ],
    "Citronnelle": [
        {"stade": "Repos hivernal", "mois": [11, 12, 1, 2], "ndvi_min": 0.12, "ndvi_max": 0.22, "ndre_min": 0.06, "ndre_max": 0.11},
        {"stade": "Reprise", "mois": [3, 4], "ndvi_min": 0.20, "ndvi_max": 0.35, "ndre_min": 0.09, "ndre_max": 0.16},
        {"stade": "Plein développement biomasse", "mois": [4, 5, 6, 7, 8, 9], "ndvi_min": 0.35, "ndvi_max": 0.55, "ndre_min": 0.16, "ndre_max": 0.28},
        {"stade": "Coupes biomasse", "mois": [6, 7, 9, 10], "ndvi_min": 0.25, "ndvi_max": 0.45, "ndre_min": 0.11, "ndre_max": 0.22},
    ],
    "Olivier": [
        {"stade": "Repos hivernal", "mois": [12, 1], "ndvi_min": 0.25, "ndvi_max": 0.40, "ndre_min": 0.10, "ndre_max": 0.18},
        {"stade": "Débourrement", "mois": [2, 3], "ndvi_min": 0.30, "ndvi_max": 0.45, "ndre_min": 0.12, "ndre_max": 0.20},
        {"stade": "Floraison", "mois": [4, 5], "ndvi_min": 0.35, "ndvi_max": 0.50, "ndre_min": 0.15, "ndre_max": 0.25},
        {"stade": "Nouaison & Grossissement", "mois": [6, 7, 8, 9], "ndvi_min": 0.35, "ndvi_max": 0.55, "ndre_min": 0.16, "ndre_max": 0.26},
        {"stade": "Maturation & Récolte", "mois": [10, 11, 12], "ndvi_min": 0.30, "ndvi_max": 0.45, "ndre_min": 0.12, "ndre_max": 0.20},
    ],
    "Amandier": [
        {"stade": "Dormance hivernale", "mois": [11, 12, 1], "ndvi_min": 0.10, "ndvi_max": 0.20, "ndre_min": 0.04, "ndre_max": 0.09},
        {"stade": "Floraison précoce", "mois": [2], "ndvi_min": 0.15, "ndvi_max": 0.25, "ndre_min": 0.06, "ndre_max": 0.12},
        {"stade": "Feuillaison & Nouaison", "mois": [3, 4], "ndvi_min": 0.25, "ndvi_max": 0.45, "ndre_min": 0.11, "ndre_max": 0.22},
        {"stade": "Grossissement fruit & Maturation", "mois": [5, 6, 7, 8], "ndvi_min": 0.35, "ndvi_max": 0.55, "ndre_min": 0.15, "ndre_max": 0.28},
        {"stade": "Récolte & Chute feuilles", "mois": [8, 9, 10], "ndvi_min": 0.18, "ndvi_max": 0.32, "ndre_min": 0.07, "ndre_max": 0.15},
    ],
    "Caroubier": [
        {"stade": "Croissance hivernale ralentie", "mois": [12, 1, 2], "ndvi_min": 0.20, "ndvi_max": 0.32, "ndre_min": 0.08, "ndre_max": 0.14},
        {"stade": "Reprise & Floraison", "mois": [3, 4, 5], "ndvi_min": 0.28, "ndvi_max": 0.42, "ndre_min": 0.12, "ndre_max": 0.20},
        {"stade": "Nouaison & Développement gousses", "mois": [6, 7, 8], "ndvi_min": 0.30, "ndvi_max": 0.48, "ndre_min": 0.14, "ndre_max": 0.24},
        {"stade": "Maturation gousses & Récolte", "mois": [9, 10, 11], "ndvi_min": 0.25, "ndvi_max": 0.38, "ndre_min": 0.10, "ndre_max": 0.18},
    ],
    "Piment": [
        {"stade": "Pépinière / Plantule", "mois": [1, 2, 3], "ndvi_min": 0.10, "ndvi_max": 0.20, "ndre_min": 0.04, "ndre_max": 0.08},
        {"stade": "Plantation & Végétatif", "mois": [3, 4, 5], "ndvi_min": 0.18, "ndvi_max": 0.35, "ndre_min": 0.08, "ndre_max": 0.16},
        {"stade": "Floraison & Fructification", "mois": [6, 7, 8, 9], "ndvi_min": 0.35, "ndvi_max": 0.60, "ndre_min": 0.18, "ndre_max": 0.32},
        {"stade": "Récoltes", "mois": [7, 8, 9, 10], "ndvi_min": 0.30, "ndvi_max": 0.55, "ndre_min": 0.14, "ndre_max": 0.28},
    ],
    "Oignon": [
        {"stade": "Plantation / Reprise", "mois": [10, 11, 12], "ndvi_min": 0.08, "ndvi_max": 0.18, "ndre_min": 0.03, "ndre_max": 0.07},
        {"stade": "Développement feuillage", "mois": [1, 2, 3], "ndvi_min": 0.18, "ndvi_max": 0.35, "ndre_min": 0.08, "ndre_max": 0.15},
        {"stade": "Bulbification", "mois": [4, 5], "ndvi_min": 0.30, "ndvi_max": 0.50, "ndre_min": 0.14, "ndre_max": 0.24},
        {"stade": "Maturation & Dessèchement", "mois": [6, 7], "ndvi_min": 0.15, "ndvi_max": 0.30, "ndre_min": 0.06, "ndre_max": 0.12},
    ],
    "DEFAULT": [
        {"stade": "Repos / Inter-saison", "mois": [11, 12, 1, 2], "ndvi_min": 0.10, "ndvi_max": 0.25, "ndre_min": 0.05, "ndre_max": 0.12},
        {"stade": "Croissance printanière", "mois": [3, 4, 5], "ndvi_min": 0.20, "ndvi_max": 0.40, "ndre_min": 0.09, "ndre_max": 0.20},
        {"stade": "Plein développement", "mois": [6, 7, 8, 9], "ndvi_min": 0.25, "ndvi_max": 0.50, "ndre_min": 0.12, "ndre_max": 0.25},
        {"stade": "Maturation / Senescence", "mois": [10], "ndvi_min": 0.15, "ndvi_max": 0.30, "ndre_min": 0.07, "ndre_max": 0.15},
    ]
}

# ===========================================================================
# 6. THRESHOLDS POUR RISQUE DE MALADIES ET STRESS CLIMATIQUE
# ===========================================================================
# Découplage NDVI vs NDRE (chute relative de NDRE sans chute proportionnelle de NDVI)
SEUIL_DECOUPLAGE_NDRE_NDVI = -0.15   # Z-score du ratio NDRE/NDVI < -1.5
SEUIL_HUMIDITE_ERA5_MALADIE = 80.0   # % RH relative ou régime pluvieux persistant
SEUIL_TEMP_OPTIMALE_MALADIE = (18.0, 26.0) # Plage °C favorable au développement fongique

# Stress Gel (ERA5)
SEUIL_GEL_RISQUE_LEGER = 0.0   # Tmin <= 0°C
SEUIL_GEL_RISQUE_SEVERE = -3.0 # Tmin <= -3°C

# Stress Chaleur / Canicule
SEUIL_CHALEUR_STRESS_C = 38.0  # Tmax >= 38°C
