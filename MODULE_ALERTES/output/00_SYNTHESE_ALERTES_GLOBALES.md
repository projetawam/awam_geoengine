# Synthèse Globale des Alertes Agronomiques Multi-Sources

*Généré automatiquement par `run_alertes_pipeline.py`*

---

## 1. Métriques Clés

- **Nombre Total d'Alertes Déclenchées / Évaluées** : 818
- **Alertes Confiance Haute (score ≥ 70%)** : 1
- **Cas INDETERMINE (données manquantes, ex: precip_mm)** : 462
- **Chaînes causales complexes identifiées** : 75

---

## 2. Répartition par Catégorie

| Catégorie | Fichier CSV | Nombre d'Alertes |
|---|---|---:|
| **Catégorie A : Risques Naturels** | `1_alertes_risques_naturels.csv` | 528 |
| **Catégorie B : Comparaison** | `2_alertes_comparaison.csv` | 290 |
| **Catégorie C : Cohérence Registre** | `3_alertes_coherence.csv` | 0 |
| **Diagnostics Cascades** | `4_diagnostics_cascades.csv` | 818 |

---

## 3. Remarques Qualité & Gardes-Fous

- **Masquage Sol Nu** (`fCover < 0.05`) : les alertes de stress foliaire (#1, #2, #3) sont neutralisées en présence de sol nu dominant.
- **Garde-fou `INDETERMINE`** : Les alertes dépendantes de la pluie (#5, #6, #8) basculent en `INDETERMINE_DONNEE_MANQUANTE` si `precip_mm` est absent du fichier ERA5.
- **Facteur d'Échelle Spatial** : appliqué aux capteurs à résolution métrique supérieure (MODIS 1km, NISAR 200m).
