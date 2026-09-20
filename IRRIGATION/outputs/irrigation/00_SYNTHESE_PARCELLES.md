# Synthèse par parcelle -- Irrigation détectée & Besoin en eau

*Généré le 2026-09-20 10:02*

Ce document croise deux analyses indépendantes : **quand une irrigation a probablement eu lieu** (`detect_irrigation_vs_pluie_v3.py`) et **quand la plante en avait besoin** (`detect_besoin_vs_irrigation.py`).


## makthar_P1 -- *Amandier* (makthar)

**Irrigation détectée** (49 jour(s) flagué(s) au total) :
- 42 jour(s) classés irrigation (20 haute, 4 moyenne, 18 basse)
- 7 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 146 jour(s) de stress hydrique détecté(s)
- 97 avec irrigation détectée à proximité (66%), **49 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 97 stress persistant(s) malgré irrigation, 49 stress non traité(s)
- ⚠️ 76 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 49 irrigation(s) analysée(s) : 41 réactive(s), 8 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 146 épisodes de stress hydrique ne s'est résorbé — stress persistant (97) ou non traité (49).

> ⚠️ *Alerte canicule & coupure d'eau (Été 2026)* : Malgré un bon taux de comblement printanier, les capteurs thermiques (MODIS CWSI=1.00, $T_{\text{sol}} > 44\text{ °C}$) et optiques (baisse NDVI/NDRE) confirment un choc thermique sévère et l'absence totale d'irrigation durant l'été 2026 (coupure d'eau réseau/barrage), entraînant le flétrissement des fruits et des dégâts sur la récolte observés le 15/08/2026.

## makthar_P2 -- *Olivier* (makthar)

**Irrigation détectée** (60 jour(s) flagué(s) au total) :
- 52 jour(s) classés irrigation (33 haute, 3 moyenne, 16 basse)
- 8 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 152 jour(s) de stress hydrique détecté(s)
- 99 avec irrigation détectée à proximité (65%), **53 sans irrigation détectée**
- **Effet biologique réel** : 2 stress résorbé(s), 97 stress persistant(s) malgré irrigation, 53 stress non traité(s)
- ⚠️ 67 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 60 irrigation(s) analysée(s) : 47 réactive(s), 13 préventive(s)/non corroborée(s)

**Verdict** : Déficit sévère : seuls 2/152 épisodes de stress hydrique (1%) se sont résorbés — 150 épisodes restent en stress persistant ou non traité.

> ⚠️ *Alerte coupure d'eau (Été 2026)* : après une irrigation corroborée le 25/07/2026 (insuffisante à ramener le CWSI sous le seuil de récupération), aucun signal d'apport d'eau n'a été détecté du **27/08/2026 au 30/08/2026** (dernière donnée disponible, soit 4 jours consécutifs sans eau), sur fond de stress thermique quasi continu. Cohérent avec le témoignage terrain d'une coupure d'eau découverte le 15/08/2026.

## makthar_P3 -- *Sol nu* (makthar)

**Irrigation détectée** (47 jour(s) flagué(s) au total) :
- 39 jour(s) classés irrigation (21 haute, 5 moyenne, 13 basse)
- 8 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 108 jour(s) d'assèchement de surface détecté(s)
- 44 avec irrigation détectée à proximité (41%), **64 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 44 stress persistant(s) malgré irrigation, 64 stress non traité(s)
- ⚠️ 37 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 47 irrigation(s) analysée(s) : 25 réactive(s), 22 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 108 épisodes d'assèchement ne s'est résorbé — stress persistant (44) ou non traité (64).

## makthar_P4 -- *Sol nu* (makthar)

**Irrigation détectée** (60 jour(s) flagué(s) au total) :
- 53 jour(s) classés irrigation (31 haute, 3 moyenne, 19 basse)
- 7 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 143 jour(s) d'assèchement de surface détecté(s)
- 83 avec irrigation détectée à proximité (58%), **60 sans irrigation détectée**
- **Effet biologique réel** : 1 stress résorbé(s), 82 stress persistant(s) malgré irrigation, 60 stress non traité(s)
- ⚠️ 51 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 60 irrigation(s) analysée(s) : 49 réactive(s), 11 préventive(s)/non corroborée(s)

**Verdict** : Déficit sévère : seuls 1/143 épisodes d'assèchement (1%) se sont résorbés — 142 épisodes restent en stress persistant ou non traité.

## makthar_P5 -- *Sol nu* (makthar)

**Irrigation détectée** (46 jour(s) flagué(s) au total) :
- 43 jour(s) classés irrigation (25 haute, 4 moyenne, 14 basse)
- 3 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 122 jour(s) d'assèchement de surface détecté(s)
- 57 avec irrigation détectée à proximité (47%), **65 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 57 stress persistant(s) malgré irrigation, 65 stress non traité(s)
- ⚠️ 42 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 46 irrigation(s) analysée(s) : 29 réactive(s), 17 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 122 épisodes d'assèchement ne s'est résorbé — stress persistant (57) ou non traité (65).

## makthar_P6 -- *Sol nu* (makthar)

**Irrigation détectée** (46 jour(s) flagué(s) au total) :
- 39 jour(s) classés irrigation (21 haute, 4 moyenne, 14 basse)
- 7 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 122 jour(s) d'assèchement de surface détecté(s)
- 53 avec irrigation détectée à proximité (43%), **69 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 53 stress persistant(s) malgré irrigation, 69 stress non traité(s)
- ⚠️ 48 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 46 irrigation(s) analysée(s) : 30 réactive(s), 16 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 122 épisodes d'assèchement ne s'est résorbé — stress persistant (53) ou non traité (69).

## sidi_mechreg_Parcelle_Badreddine_5 -- *Olivier/Citronnelle/Verveine* (sidi_mechreg)

**Irrigation détectée** (64 jour(s) flagué(s) au total) :
- 38 jour(s) classés irrigation (19 haute, 0 moyenne, 19 basse)
- 26 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 128 jour(s) de stress hydrique détecté(s)
- 90 avec irrigation détectée à proximité (70%), **38 sans irrigation détectée**
- **Effet biologique réel** : 3 stress résorbé(s), 87 stress persistant(s) malgré irrigation, 38 stress non traité(s)
- ⚠️ 26 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 64 irrigation(s) analysée(s) : 46 réactive(s), 18 préventive(s)/non corroborée(s)

**Verdict** : Déficit suspect sur irrigation déclarée (Goutte-à-goutte (depuis 15/06/2026)) : seuls 3/128 épisodes de stress hydrique (2%) se sont résorbés. Sur un réseau automatisé, une faible réponse spectrale constitue un signal d'anomalie d'apport ou de débit à vérifier sur le terrain.

> ℹ️ *Note d'exploitation terrain* : Parcelle mise en culture officielle au **15 juin 2026** (confirmé par l'exploitant). Le système goutte-à-goutte est actif en continu depuis cette date.

## sidi_mechreg_Parcelle_Kemel_1 -- *Lavande/Romarin/Géranium* (sidi_mechreg)

**Irrigation détectée** (53 jour(s) flagué(s) au total) :
- 32 jour(s) classés irrigation (22 haute, 0 moyenne, 10 basse)
- 21 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 107 jour(s) de stress hydrique détecté(s)
- 59 avec irrigation détectée à proximité (55%), **48 sans irrigation détectée**
- **Effet biologique réel** : 1 stress résorbé(s), 57 stress persistant(s) malgré irrigation, 48 stress non traité(s)
- ⚠️ 33 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 53 irrigation(s) analysée(s) : 35 réactive(s), 18 préventive(s)/non corroborée(s)

**Verdict** : Compatible avec sous-détection instrumentale documentée : seuls 1/107 épisodes de stress hydrique (1%) montrent une résorption mesurable à l'échelle satellite. L'arrosage manuel localisé (micro-empreinte < résolution pixel sous forte évaporation) explique la faible détectabilité, mais un déficit ponctuel d'irrigation ne peut être formellement exclu sans contrôle terrain.

> ℹ️ *Note d'exploitation terrain & Limite instrumentale* : L'exploitant déclare un arrosage manuel localisé au pied. La faible empreinte spatiale (< 2 m² sous 30 °C+ sur parcelle de 0.6 à 0.8 ha) explique la sous-détection physique satellite sans exclure des variations d'apport.

## sidi_mechreg_Parcelle_Kemel_2 -- *Aucune* (sidi_mechreg)

**Irrigation détectée** (38 jour(s) flagué(s) au total) :
- 26 jour(s) classés irrigation (16 haute, 0 moyenne, 10 basse)
- 12 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 109 jour(s) d'assèchement de surface détecté(s)
- 39 avec irrigation détectée à proximité (36%), **70 sans irrigation détectée**
- **Effet biologique réel** : 2 stress résorbé(s), 37 stress persistant(s) malgré irrigation, 70 stress non traité(s)
- ⚠️ 26 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 38 irrigation(s) analysée(s) : 31 réactive(s), 7 préventive(s)/non corroborée(s)

**Verdict** : Compatible avec sous-détection instrumentale documentée : seuls 2/109 épisodes d'assèchement (2%) montrent une résorption mesurable à l'échelle satellite. L'arrosage manuel localisé (micro-empreinte < résolution pixel sous forte évaporation) explique la faible détectabilité, mais un déficit ponctuel d'irrigation ne peut être formellement exclu sans contrôle terrain.

> ℹ️ *Note d'exploitation terrain & Limite instrumentale* : L'exploitant déclare un arrosage manuel localisé au pied. La faible empreinte spatiale (< 2 m² sous 30 °C+ sur parcelle de 0.6 à 0.8 ha) explique la sous-détection physique satellite sans exclure des variations d'apport.

## sidi_mechreg_Parcelle_Kemel_3 -- *Caroubier* (sidi_mechreg)

**Irrigation détectée** (33 jour(s) flagué(s) au total) :
- 18 jour(s) classés irrigation (10 haute, 0 moyenne, 8 basse)
- 15 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI -- absents : soil_moisture_vol) :
- 105 jour(s) de stress hydrique détecté(s)
- 41 avec irrigation détectée à proximité (39%), **64 sans irrigation détectée**
- **Effet biologique réel** : 2 stress résorbé(s), 39 stress persistant(s) malgré irrigation, 64 stress non traité(s)
- ⚠️ 20 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 33 irrigation(s) analysée(s) : 24 réactive(s), 9 préventive(s)/non corroborée(s)

**Verdict** : Compatible avec sous-détection instrumentale documentée : seuls 2/105 épisodes de stress hydrique (2%) montrent une résorption mesurable à l'échelle satellite. L'arrosage manuel localisé (micro-empreinte < résolution pixel sous forte évaporation) explique la faible détectabilité, mais un déficit ponctuel d'irrigation ne peut être formellement exclu sans contrôle terrain.

> ℹ️ *Note d'exploitation terrain & Limite instrumentale* : L'exploitant déclare un arrosage manuel localisé au pied. La faible empreinte spatiale (< 2 m² sous 30 °C+ sur parcelle de 0.6 à 0.8 ha) explique la sous-détection physique satellite sans exclure des variations d'apport.

## sidi_mechreg_Parcelle_Yahia_4 -- *Lavande/Romarin/Géranium/Sauge* (sidi_mechreg)

**Irrigation détectée** (40 jour(s) flagué(s) au total) :
- 23 jour(s) classés irrigation (16 haute, 0 moyenne, 7 basse)
- 17 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 112 jour(s) de stress hydrique détecté(s)
- 44 avec irrigation détectée à proximité (39%), **68 sans irrigation détectée**
- **Effet biologique réel** : 3 stress résorbé(s), 41 stress persistant(s) malgré irrigation, 68 stress non traité(s)
- ⚠️ 25 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 40 irrigation(s) analysée(s) : 25 réactive(s), 15 préventive(s)/non corroborée(s)

**Verdict** : Compatible avec sous-détection instrumentale documentée : seuls 3/112 épisodes de stress hydrique (3%) montrent une résorption mesurable à l'échelle satellite. L'arrosage manuel localisé (micro-empreinte < résolution pixel sous forte évaporation) explique la faible détectabilité, mais un déficit ponctuel d'irrigation ne peut être formellement exclu sans contrôle terrain.

> ℹ️ *Note d'exploitation terrain & Limite instrumentale* : L'exploitant déclare un arrosage manuel localisé au pied. La faible empreinte spatiale (< 2 m² sous 30 °C+ sur parcelle de 0.6 à 0.8 ha) explique la sous-détection physique satellite sans exclure des variations d'apport.