# Synthèse par parcelle -- Irrigation détectée & Besoin en eau

*Généré le 2026-08-31 13:19*

Ce document croise deux analyses indépendantes : **quand une irrigation a probablement eu lieu** (`detect_irrigation_vs_pluie_v3.py`) et **quand la plante en avait besoin** (`detect_besoin_vs_irrigation.py`).


## makthar_P1 -- *Amandier* (makthar)

**Irrigation détectée** (46 jour(s) flagué(s) au total) :
- 40 jour(s) classés irrigation (18 haute, 4 moyenne, 18 basse)
- 6 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 141 jour(s) de stress hydrique détecté(s)
- 92 avec irrigation détectée à proximité (65%), **49 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 92 stress persistant(s) malgré irrigation, 49 stress non traité(s)
- ⚠️ 71 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 46 irrigation(s) analysée(s) : 38 réactive(s), 8 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 141 épisodes de stress hydrique ne s'est résorbé — stress persistant (92) ou non traité (49).

> ⚠️ *Alerte coupure d'eau (Été 2026)* : après une irrigation corroborée le 23/07/2026 (insuffisante à ramener le CWSI sous le seuil de récupération), aucun signal d'apport d'eau n'a été détecté du **29/07/2026 au 08/08/2026** (dernière donnée disponible, soit 11 jours consécutifs sans eau), sur fond de stress thermique quasi continu. Cohérent avec le témoignage terrain d'une coupure d'eau découverte le 15/08/2026.

## makthar_P2 -- *Olivier* (makthar)

**Irrigation détectée** (74 jour(s) flagué(s) au total) :
- 62 jour(s) classés irrigation (37 haute, 6 moyenne, 19 basse)
- 12 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 139 jour(s) de stress hydrique détecté(s)
- 99 avec irrigation détectée à proximité (71%), **40 sans irrigation détectée**
- **Effet biologique réel** : 4 stress résorbé(s), 94 stress persistant(s) malgré irrigation, 40 stress non traité(s)
- ⚠️ 48 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 74 irrigation(s) analysée(s) : 59 réactive(s), 15 préventive(s)/non corroborée(s)

**Verdict** : Déficit sévère : seuls 4/139 épisodes de stress hydrique (3%) se sont résorbés — 134 épisodes restent en stress persistant ou non traité.

> ⚠️ *Alerte canicule & coupure d'eau (Été 2026)* : Malgré un bon taux de comblement printanier, les capteurs thermiques (MODIS CWSI=1.00, $T_{\text{sol}} > 44\text{ °C}$) et optiques (baisse NDVI/NDRE) confirment un choc thermique sévère et l'absence totale d'irrigation durant l'été 2026 (coupure d'eau réseau/barrage), entraînant le flétrissement des fruits et des dégâts sur la récolte observés le 15/08/2026.

## makthar_P3 -- *Sol nu* (makthar)

**Irrigation détectée** (44 jour(s) flagué(s) au total) :
- 37 jour(s) classés irrigation (19 haute, 5 moyenne, 13 basse)
- 7 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 100 jour(s) d'assèchement de surface détecté(s)
- 41 avec irrigation détectée à proximité (41%), **59 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 41 stress persistant(s) malgré irrigation, 59 stress non traité(s)
- ⚠️ 34 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 44 irrigation(s) analysée(s) : 22 réactive(s), 22 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 100 épisodes d'assèchement ne s'est résorbé — stress persistant (41) ou non traité (59).

## makthar_P4 -- *Sol nu* (makthar)

**Irrigation détectée** (56 jour(s) flagué(s) au total) :
- 50 jour(s) classés irrigation (28 haute, 3 moyenne, 19 basse)
- 6 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 131 jour(s) d'assèchement de surface détecté(s)
- 76 avec irrigation détectée à proximité (58%), **55 sans irrigation détectée**
- **Effet biologique réel** : 1 stress résorbé(s), 75 stress persistant(s) malgré irrigation, 55 stress non traité(s)
- ⚠️ 45 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 56 irrigation(s) analysée(s) : 45 réactive(s), 11 préventive(s)/non corroborée(s)

**Verdict** : Déficit sévère : seuls 1/131 épisodes d'assèchement (1%) se sont résorbés — 130 épisodes restent en stress persistant ou non traité.

## makthar_P5 -- *Sol nu* (makthar)

**Irrigation détectée** (44 jour(s) flagué(s) au total) :
- 41 jour(s) classés irrigation (23 haute, 4 moyenne, 14 basse)
- 3 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 111 jour(s) d'assèchement de surface détecté(s)
- 54 avec irrigation détectée à proximité (49%), **57 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 54 stress persistant(s) malgré irrigation, 57 stress non traité(s)
- ⚠️ 40 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 44 irrigation(s) analysée(s) : 27 réactive(s), 17 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 111 épisodes d'assèchement ne s'est résorbé — stress persistant (54) ou non traité (57).

## makthar_P6 -- *Sol nu* (makthar)

**Irrigation détectée** (43 jour(s) flagué(s) au total) :
- 37 jour(s) classés irrigation (19 haute, 4 moyenne, 14 basse)
- 6 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 112 jour(s) d'assèchement de surface détecté(s)
- 49 avec irrigation détectée à proximité (44%), **63 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 49 stress persistant(s) malgré irrigation, 63 stress non traité(s)
- ⚠️ 44 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 43 irrigation(s) analysée(s) : 27 réactive(s), 16 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 112 épisodes d'assèchement ne s'est résorbé — stress persistant (49) ou non traité (63).

## sidi_mechreg_Parcelle_Badreddine_5 -- *Olivier/Citronnelle/Verveine* (sidi_mechreg)

**Irrigation détectée** (62 jour(s) flagué(s) au total) :
- 36 jour(s) classés irrigation (17 haute, 0 moyenne, 19 basse)
- 26 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 120 jour(s) de stress hydrique détecté(s)
- 83 avec irrigation détectée à proximité (69%), **37 sans irrigation détectée**
- **Effet biologique réel** : 3 stress résorbé(s), 80 stress persistant(s) malgré irrigation, 37 stress non traité(s)
- ⚠️ 26 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 62 irrigation(s) analysée(s) : 44 réactive(s), 18 préventive(s)/non corroborée(s)

**Verdict** : Déficit suspect sur irrigation déclarée (Goutte-à-goutte (depuis 15/06/2026)) : seuls 3/120 épisodes de stress hydrique (2%) se sont résorbés. Sur un réseau automatisé, une faible réponse spectrale constitue un signal d'anomalie d'apport ou de débit à vérifier sur le terrain.

> ℹ️ *Note d'exploitation terrain* : Parcelle mise en culture officielle au **15 juin 2026** (confirmé par l'exploitant). Le système goutte-à-goutte est actif en continu depuis cette date.

## sidi_mechreg_Parcelle_Kemel_1 -- *Lavande/Romarin/Géranium* (sidi_mechreg)

**Irrigation détectée** (52 jour(s) flagué(s) au total) :
- 31 jour(s) classés irrigation (21 haute, 0 moyenne, 10 basse)
- 21 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 100 jour(s) de stress hydrique détecté(s)
- 56 avec irrigation détectée à proximité (56%), **44 sans irrigation détectée**
- **Effet biologique réel** : 1 stress résorbé(s), 55 stress persistant(s) malgré irrigation, 44 stress non traité(s)
- ⚠️ 33 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 52 irrigation(s) analysée(s) : 34 réactive(s), 18 préventive(s)/non corroborée(s)

**Verdict** : Compatible avec sous-détection instrumentale documentée : seuls 1/100 épisodes de stress hydrique (1%) montrent une résorption mesurable à l'échelle satellite. L'arrosage manuel localisé (micro-empreinte < résolution pixel sous forte évaporation) explique la faible détectabilité, mais un déficit ponctuel d'irrigation ne peut être formellement exclu sans contrôle terrain.

> ℹ️ *Note d'exploitation terrain & Limite instrumentale* : L'exploitant déclare un arrosage manuel localisé au pied. La faible empreinte spatiale (< 2 m² sous 30 °C+ sur parcelle de 0.6 à 0.8 ha) explique la sous-détection physique satellite sans exclure des variations d'apport.

## sidi_mechreg_Parcelle_Kemel_2 -- *Aucune* (sidi_mechreg)

**Irrigation détectée** (38 jour(s) flagué(s) au total) :
- 26 jour(s) classés irrigation (16 haute, 0 moyenne, 10 basse)
- 12 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 102 jour(s) d'assèchement de surface détecté(s)
- 39 avec irrigation détectée à proximité (38%), **63 sans irrigation détectée**
- **Effet biologique réel** : 2 stress résorbé(s), 37 stress persistant(s) malgré irrigation, 63 stress non traité(s)
- ⚠️ 26 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 38 irrigation(s) analysée(s) : 31 réactive(s), 7 préventive(s)/non corroborée(s)

**Verdict** : Compatible avec sous-détection instrumentale documentée : seuls 2/102 épisodes d'assèchement (2%) montrent une résorption mesurable à l'échelle satellite. L'arrosage manuel localisé (micro-empreinte < résolution pixel sous forte évaporation) explique la faible détectabilité, mais un déficit ponctuel d'irrigation ne peut être formellement exclu sans contrôle terrain.

> ℹ️ *Note d'exploitation terrain & Limite instrumentale* : L'exploitant déclare un arrosage manuel localisé au pied. La faible empreinte spatiale (< 2 m² sous 30 °C+ sur parcelle de 0.6 à 0.8 ha) explique la sous-détection physique satellite sans exclure des variations d'apport.

## sidi_mechreg_Parcelle_Kemel_3 -- *Caroubier* (sidi_mechreg)

**Irrigation détectée** (35 jour(s) flagué(s) au total) :
- 18 jour(s) classés irrigation (9 haute, 0 moyenne, 9 basse)
- 17 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI -- absents : soil_moisture_vol) :
- 99 jour(s) de stress hydrique détecté(s)
- 42 avec irrigation détectée à proximité (42%), **57 sans irrigation détectée**
- **Effet biologique réel** : 2 stress résorbé(s), 40 stress persistant(s) malgré irrigation, 57 stress non traité(s)
- ⚠️ 20 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 35 irrigation(s) analysée(s) : 22 réactive(s), 13 préventive(s)/non corroborée(s)

**Verdict** : Compatible avec sous-détection instrumentale documentée : seuls 2/99 épisodes de stress hydrique (2%) montrent une résorption mesurable à l'échelle satellite. L'arrosage manuel localisé (micro-empreinte < résolution pixel sous forte évaporation) explique la faible détectabilité, mais un déficit ponctuel d'irrigation ne peut être formellement exclu sans contrôle terrain.

> ℹ️ *Note d'exploitation terrain & Limite instrumentale* : L'exploitant déclare un arrosage manuel localisé au pied. La faible empreinte spatiale (< 2 m² sous 30 °C+ sur parcelle de 0.6 à 0.8 ha) explique la sous-détection physique satellite sans exclure des variations d'apport.

## sidi_mechreg_Parcelle_Yahia_4 -- *Lavande/Romarin/Geranium/Sauge* (sidi_mechreg)

**Irrigation détectée** (40 jour(s) flagué(s) au total) :
- 22 jour(s) classés irrigation (16 haute, 0 moyenne, 6 basse)
- 18 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 106 jour(s) de stress hydrique détecté(s)
- 38 avec irrigation détectée à proximité (36%), **68 sans irrigation détectée**
- **Effet biologique réel** : 2 stress résorbé(s), 36 stress persistant(s) malgré irrigation, 68 stress non traité(s)
- ⚠️ 23 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 40 irrigation(s) analysée(s) : 24 réactive(s), 16 préventive(s)/non corroborée(s)

**Verdict** : Compatible avec sous-détection instrumentale documentée : seuls 2/106 épisodes de stress hydrique (2%) montrent une résorption mesurable à l'échelle satellite. L'arrosage manuel localisé (micro-empreinte < résolution pixel sous forte évaporation) explique la faible détectabilité, mais un déficit ponctuel d'irrigation ne peut être formellement exclu sans contrôle terrain.

> ℹ️ *Note d'exploitation terrain & Limite instrumentale* : L'exploitant déclare un arrosage manuel localisé au pied. La faible empreinte spatiale (< 2 m² sous 30 °C+ sur parcelle de 0.6 à 0.8 ha) explique la sous-détection physique satellite sans exclure des variations d'apport.