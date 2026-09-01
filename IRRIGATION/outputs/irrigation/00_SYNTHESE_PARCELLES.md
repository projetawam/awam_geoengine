# Synthèse par parcelle -- Irrigation détectée & Besoin en eau

*Généré le 2026-09-01 14:23*

Ce document croise deux analyses indépendantes : **quand une irrigation a probablement eu lieu** (`detect_irrigation_vs_pluie_v3.py`) et **quand la plante en avait besoin** (`detect_besoin_vs_irrigation.py`).


## makthar_P1 -- *Amandier* (makthar)

**Irrigation détectée** (3 jour(s) flagué(s) au total) :
- 2 jour(s) classés irrigation (2 haute, 0 moyenne, 0 basse)
- 1 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 7 jour(s) de stress hydrique détecté(s)
- 5 avec irrigation détectée à proximité (71%), **2 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 5 stress persistant(s) malgré irrigation, 2 stress non traité(s)
- ⚠️ 5 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 3 irrigation(s) analysée(s) : 3 réactive(s), 0 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 7 épisodes de stress hydrique ne s'est résorbé — stress persistant (5) ou non traité (2).

> ⚠️ *Alerte canicule & coupure d'eau (Été 2026)* : Malgré un bon taux de comblement printanier, les capteurs thermiques (MODIS CWSI=1.00, $T_{\text{sol}} > 44\text{ °C}$) et optiques (baisse NDVI/NDRE) confirment un choc thermique sévère et l'absence totale d'irrigation durant l'été 2026 (coupure d'eau réseau/barrage), entraînant le flétrissement des fruits et des dégâts sur la récolte observés le 15/08/2026.

## makthar_P2 -- *Olivier* (makthar)

**Irrigation détectée** (3 jour(s) flagué(s) au total) :
- 2 jour(s) classés irrigation (2 haute, 0 moyenne, 0 basse)
- 1 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 21 jour(s) de stress hydrique détecté(s)
- 12 avec irrigation détectée à proximité (57%), **9 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 12 stress persistant(s) malgré irrigation, 9 stress non traité(s)
- ⚠️ 12 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 3 irrigation(s) analysée(s) : 3 réactive(s), 0 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 21 épisodes de stress hydrique ne s'est résorbé — stress persistant (12) ou non traité (9).

> ⚠️ *Alerte coupure d'eau (Été 2026)* : aucun signal d'apport d'eau n'a été détecté du **27/08/2026 au 30/08/2026** (dernière donnée disponible, soit 4 jours consécutifs sans eau), sur fond de stress thermique quasi continu. Cohérent avec le témoignage terrain d'une coupure d'eau découverte le 15/08/2026.

## makthar_P3 -- *Sol nu* (makthar)

**Irrigation détectée** (3 jour(s) flagué(s) au total) :
- 2 jour(s) classés irrigation (2 haute, 0 moyenne, 0 basse)
- 1 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 10 jour(s) d'assèchement de surface détecté(s)
- 3 avec irrigation détectée à proximité (30%), **7 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 3 stress persistant(s) malgré irrigation, 7 stress non traité(s)
- ⚠️ 3 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 3 irrigation(s) analysée(s) : 3 réactive(s), 0 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 10 épisodes d'assèchement ne s'est résorbé — stress persistant (3) ou non traité (7).

## makthar_P4 -- *Sol nu* (makthar)

**Irrigation détectée** (4 jour(s) flagué(s) au total) :
- 3 jour(s) classés irrigation (3 haute, 0 moyenne, 0 basse)
- 1 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 18 jour(s) d'assèchement de surface détecté(s)
- 7 avec irrigation détectée à proximité (39%), **11 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 7 stress persistant(s) malgré irrigation, 11 stress non traité(s)
- ⚠️ 6 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 4 irrigation(s) analysée(s) : 4 réactive(s), 0 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 18 épisodes d'assèchement ne s'est résorbé — stress persistant (7) ou non traité (11).

## makthar_P5 -- *Sol nu* (makthar)

**Irrigation détectée** (3 jour(s) flagué(s) au total) :
- 2 jour(s) classés irrigation (2 haute, 0 moyenne, 0 basse)
- 1 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 19 jour(s) d'assèchement de surface détecté(s)
- 5 avec irrigation détectée à proximité (26%), **14 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 5 stress persistant(s) malgré irrigation, 14 stress non traité(s)
- ⚠️ 4 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 3 irrigation(s) analysée(s) : 3 réactive(s), 0 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 19 épisodes d'assèchement ne s'est résorbé — stress persistant (5) ou non traité (14).

## makthar_P6 -- *Sol nu* (makthar)

**Irrigation détectée** (3 jour(s) flagué(s) au total) :
- 2 jour(s) classés irrigation (2 haute, 0 moyenne, 0 basse)
- 1 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 17 jour(s) d'assèchement de surface détecté(s)
- 4 avec irrigation détectée à proximité (24%), **13 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 4 stress persistant(s) malgré irrigation, 13 stress non traité(s)
- ⚠️ 4 irrigation(s) reposant uniquement sur un signal thermique LST (canicule possible — preuve faible)
- Sur 3 irrigation(s) analysée(s) : 3 réactive(s), 0 préventive(s)/non corroborée(s)

**Verdict** : Déficit critique : aucun des 17 épisodes d'assèchement ne s'est résorbé — stress persistant (4) ou non traité (13).

## sidi_mechreg_Parcelle_Badreddine_5 -- *Olivier/Citronnelle/Verveine* (sidi_mechreg)

**Irrigation détectée** (3 jour(s) flagué(s) au total) :
- 3 jour(s) classés irrigation (3 haute, 0 moyenne, 0 basse)
- 0 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 12 jour(s) de stress hydrique détecté(s)
- 8 avec irrigation détectée à proximité (67%), **4 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 8 stress persistant(s) malgré irrigation, 4 stress non traité(s)
- Sur 3 irrigation(s) analysée(s) : 3 réactive(s), 0 préventive(s)/non corroborée(s)

**Verdict** : Déficit suspect sur irrigation déclarée (Goutte-à-goutte (depuis 15/06/2026)) : seuls 0/12 épisodes de stress hydrique (0%) se sont résorbés. Sur un réseau automatisé, une faible réponse spectrale constitue un signal d'anomalie d'apport ou de débit à vérifier sur le terrain.

> ℹ️ *Note d'exploitation terrain* : Parcelle mise en culture officielle au **15 juin 2026** (confirmé par l'exploitant). Le système goutte-à-goutte est actif en continu depuis cette date.

## sidi_mechreg_Parcelle_Kemel_1 -- *Lavande/Romarin/Géranium* (sidi_mechreg)

**Irrigation détectée** (1 jour(s) flagué(s) au total) :
- 1 jour(s) classés irrigation (1 haute, 0 moyenne, 0 basse)
- 0 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 9 jour(s) de stress hydrique détecté(s)
- 3 avec irrigation détectée à proximité (33%), **6 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 2 stress persistant(s) malgré irrigation, 6 stress non traité(s)
- Sur 1 irrigation(s) analysée(s) : 1 réactive(s), 0 préventive(s)/non corroborée(s)

**Verdict** : Compatible avec sous-détection instrumentale documentée : seuls 0/9 épisodes de stress hydrique (0%) montrent une résorption mesurable à l'échelle satellite. L'arrosage manuel localisé (micro-empreinte < résolution pixel sous forte évaporation) explique la faible détectabilité, mais un déficit ponctuel d'irrigation ne peut être formellement exclu sans contrôle terrain.

> ℹ️ *Note d'exploitation terrain & Limite instrumentale* : L'exploitant déclare un arrosage manuel localisé au pied. La faible empreinte spatiale (< 2 m² sous 30 °C+ sur parcelle de 0.6 à 0.8 ha) explique la sous-détection physique satellite sans exclure des variations d'apport.

## sidi_mechreg_Parcelle_Kemel_2 -- *Aucune* (sidi_mechreg)

**Irrigation détectée** (0 jour(s) flagué(s) au total) :
- 0 jour(s) classés irrigation (0 haute, 0 moyenne, 0 basse)
- 0 jour(s) classés pluie

> ⚠️ Parcelle *Sol nu* / sans culture déclarée : CWSI, NDMI et NDWI sont conçus pour détecter le stress hydrique d'un couvert végétal. Sans plante, ils reflètent l'humidité/réflectance du sol nu -- signal utile, mais PAS un besoin agronomique d'une culture.

**Assèchement de surface** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 9 jour(s) d'assèchement de surface détecté(s)
- 0 avec irrigation détectée à proximité (0%), **9 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 0 stress persistant(s) malgré irrigation, 9 stress non traité(s)
- Sur 0 irrigation(s) analysée(s) : 0 réactive(s), 0 préventive(s)/non corroborée(s)

**Verdict** : Compatible avec sous-détection instrumentale documentée : seuls 0/9 épisodes d'assèchement (0%) montrent une résorption mesurable à l'échelle satellite. L'arrosage manuel localisé (micro-empreinte < résolution pixel sous forte évaporation) explique la faible détectabilité, mais un déficit ponctuel d'irrigation ne peut être formellement exclu sans contrôle terrain.

> ℹ️ *Note d'exploitation terrain & Limite instrumentale* : L'exploitant déclare un arrosage manuel localisé au pied. La faible empreinte spatiale (< 2 m² sous 30 °C+ sur parcelle de 0.6 à 0.8 ha) explique la sous-détection physique satellite sans exclure des variations d'apport.

## sidi_mechreg_Parcelle_Kemel_3 -- *Caroubier* (sidi_mechreg)

**Irrigation détectée** (0 jour(s) flagué(s) au total) :
- 0 jour(s) classés irrigation (0 haute, 0 moyenne, 0 basse)
- 0 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI -- absents : soil_moisture_vol) :
- 8 jour(s) de stress hydrique détecté(s)
- 0 avec irrigation détectée à proximité (0%), **8 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 0 stress persistant(s) malgré irrigation, 8 stress non traité(s)
- Sur 0 irrigation(s) analysée(s) : 0 réactive(s), 0 préventive(s)/non corroborée(s)

**Verdict** : Compatible avec sous-détection instrumentale documentée : seuls 0/8 épisodes de stress hydrique (0%) montrent une résorption mesurable à l'échelle satellite. L'arrosage manuel localisé (micro-empreinte < résolution pixel sous forte évaporation) explique la faible détectabilité, mais un déficit ponctuel d'irrigation ne peut être formellement exclu sans contrôle terrain.

> ℹ️ *Note d'exploitation terrain & Limite instrumentale* : L'exploitant déclare un arrosage manuel localisé au pied. La faible empreinte spatiale (< 2 m² sous 30 °C+ sur parcelle de 0.6 à 0.8 ha) explique la sous-détection physique satellite sans exclure des variations d'apport.

## sidi_mechreg_Parcelle_Yahia_4 -- *Lavande/Romarin/Géranium/Sauge* (sidi_mechreg)

**Irrigation détectée** (0 jour(s) flagué(s) au total) :
- 0 jour(s) classés irrigation (0 haute, 0 moyenne, 0 basse)
- 0 jour(s) classés pluie

**Besoin en eau** (capteurs actifs : CWSI_proxy, NDMI, NDWI, SMI, soil_moisture_vol) :
- 9 jour(s) de stress hydrique détecté(s)
- 0 avec irrigation détectée à proximité (0%), **9 sans irrigation détectée**
- **Effet biologique réel** : 0 stress résorbé(s), 0 stress persistant(s) malgré irrigation, 9 stress non traité(s)
- Sur 0 irrigation(s) analysée(s) : 0 réactive(s), 0 préventive(s)/non corroborée(s)

**Verdict** : Compatible avec sous-détection instrumentale documentée : seuls 0/9 épisodes de stress hydrique (0%) montrent une résorption mesurable à l'échelle satellite. L'arrosage manuel localisé (micro-empreinte < résolution pixel sous forte évaporation) explique la faible détectabilité, mais un déficit ponctuel d'irrigation ne peut être formellement exclu sans contrôle terrain.

> ℹ️ *Note d'exploitation terrain & Limite instrumentale* : L'exploitant déclare un arrosage manuel localisé au pied. La faible empreinte spatiale (< 2 m² sous 30 °C+ sur parcelle de 0.6 à 0.8 ha) explique la sous-détection physique satellite sans exclure des variations d'apport.