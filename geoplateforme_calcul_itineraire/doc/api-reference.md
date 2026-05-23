# Référence API — Géoplateforme / Calcul d'itinéraire

> Synthèse structurée de la documentation IGN couverte par le module.
> Sources officielles :
> - [Guide cartes.gouv.fr](https://cartes.gouv.fr/aide/fr/guides-utilisateur/utiliser-les-services-de-la-geoplateforme/calcul-itineraire/)
> - [Swagger Navigation](https://data.geopf.fr/navigation/openapi/)
> - [Page Géoservices](https://geoservices.ign.fr/services-geoplateforme)

---

## 1. Vue d'ensemble

| Item | Valeur |
|---|---|
| **Base URL** | `https://data.geopf.fr/navigation` |
| **Authentification** | Aucune (service public) |
| **Quota** | 5 requêtes / seconde / IP |
| **Format de réponse** | JSON |
| **CRS d'entrée par défaut** | EPSG:4326 (`lon,lat`) |
| **Données sous-jacentes** | BD TOPO® de l'IGN |

L'API est servie par trois moteurs interchangeables :

| Ressource | Moteur | Caractéristiques |
|---|---|---|
| `bdtopo-osrm` | OSRM | Performance maximale, par défaut |
| `bdtopo-valhalla` | Valhalla | Plus d'options de profils et contraintes |
| `bdtopo-pgr` | pgRouting | Contraintes/attributs avancés, plus lent |

---

## 2. Endpoint `/getCapabilities`

### Description

Renvoie la description des capacités de l'API : ressources, profils,
opérations, options supportées.

À appeler **en premier** lors d'une intégration pour découvrir ce qui
est disponible — la structure exacte peut évoluer sans rupture
documentée.

### Méthode et URL

```
GET https://data.geopf.fr/navigation/getCapabilities
```

Aucun paramètre. Aucun header obligatoire (le module ajoute
`Accept: application/json`).

### Réponse

Un objet JSON dont les clés typiques incluent :

- `info` / `title` / `version` — métadonnées du service.
- `operations` — liste des opérations exposées (au minimum `itineraire`
  et `isochrone`).
- `resources` — liste de ressources avec, pour chacune : `id`,
  `profiles`, `optimization`, `geometry`, `constraints` supportées, etc.

La structure n'étant pas figée dans la doc publique, le module retourne
le `dict` JSON brut. Les helpers `list_available_resources()` et
`list_available_profiles(resource=None)` sont écrits pour être robustes
à plusieurs formes possibles (liste de dicts, liste de strings, dict).

---

## 3. Endpoint `/itineraire`

### Description

Calcule un itinéraire entre deux points (avec étapes intermédiaires
optionnelles).

### Méthode et URL

```
GET  https://data.geopf.fr/navigation/itineraire?<paramètres>
POST https://data.geopf.fr/navigation/itineraire
     Content-Type: application/json
     <body JSON>
```

Le GET est suffisant tant que la requête tient dans une URL. Le POST
est recommandé dès qu'on passe des `constraints` complexes ou beaucoup
d'étapes intermédiaires.

### Paramètres

#### Obligatoires

| Nom (API) | Type | Description |
|---|---|---|
| `resource` | string | `bdtopo-osrm` \| `bdtopo-valhalla` \| `bdtopo-pgr` |
| `start` | string | `"lon,lat"` (EPSG:4326) |
| `end` | string | `"lon,lat"` (EPSG:4326) |

#### Optionnels

| Nom (API) | Type | Description |
|---|---|---|
| `intermediates` | list[string] | Étapes intermédiaires `"lon,lat"` |
| `profile` | string | Profil : `car`, `pedestrian`, ... |
| `optimization` | string | `fastest` (défaut) ou `shortest` |
| `geometryFormat` | string | `geojson` ou `polyline` |
| `getSteps` | bool | Inclure les étapes de navigation |
| `getBbox` | bool | Inclure la bounding box de l'itinéraire |
| `distanceUnit` | string | `meter` ou `kilometer` |
| `timeUnit` | string | `second`, `minute`, `hour` |
| `crs` | string | Système de coordonnées en sortie |
| `constraints` | list[dict] | Règles d'exclusion (voir ci-dessous) |
| `waysAttributes` | list[string] | Attributs de segments à retourner |

#### Format des contraintes

Une contrainte est un objet :

```json
{
  "constraintType": "banned",
  "key": "wayType",
  "operator": "=",
  "value": "tunnel"
}
```

- `constraintType` : `banned` (exclusion) le plus courant.
- `key` : attribut de la route (`wayType`, `wayName`, …).
- `operator` : `=`, `!=`, `<`, `>`.
- `value` : valeur attendue.

Plusieurs contraintes peuvent être combinées dans la liste.

#### En GET vs POST

En GET, les valeurs listes/objets (`constraints`, `intermediates`,
`waysAttributes`) sont JSON-stringifiées dans la query string. Les
booléens sont sérialisés en `true`/`false` (chaînes). Le module fait
cette sérialisation automatiquement via `_serialize_get_params`.

En POST, le body est un JSON natif — pas de sérialisation supplémentaire.

### Réponse

Objet JSON dont les champs typiques sont :

| Champ | Description |
|---|---|
| `distance` | Distance totale (unité = `distanceUnit`) |
| `duration` | Durée totale (unité = `timeUnit`) |
| `geometry` | GeoJSON LineString ou polyline encodée |
| `bbox` | Bounding box `[minLon, minLat, maxLon, maxLat]` (si `getBbox=true`) |
| `portions` / `steps` | Étapes détaillées (si `getSteps=true`) |
| `resource` / `profile` / ... | Échos des paramètres de la requête |

> Le format exact est susceptible d'évoluer. Le module retourne le
> `dict` brut tel que reçu de l'API — c'est aux consommateurs de lire
> les clés dont ils ont besoin.

### Codes d'erreur observés

| HTTP | Sens | Exception levée |
|---|---|---|
| 200 | Succès | — |
| 400 | Paramètres invalides | `GeoplateformeAPIError(status_code=400)` |
| 404 | Ressource inconnue | `GeoplateformeAPIError(status_code=404)` |
| 429 | Quota dépassé (5 req/s) | `GeoplateformeAPIError(status_code=429)` |
| 500-503 | Erreur côté IGN | `GeoplateformeAPIError(status_code=5xx)` |

Pour les erreurs réseau pures (timeout, DNS, connexion refusée) le
module lève `GeoplateformeNetworkError`.

---

## 4. Exemples de requêtes brutes

### GET (Notre-Dame → Bastille à pied)

```
https://data.geopf.fr/navigation/itineraire?
  resource=bdtopo-osrm&
  start=2.349902,48.852968&
  end=2.369248,48.853110&
  profile=pedestrian&
  optimization=shortest&
  getSteps=true
```

### POST avec contraintes

```http
POST /navigation/itineraire HTTP/1.1
Host: data.geopf.fr
Content-Type: application/json

{
  "resource": "bdtopo-valhalla",
  "start": "2.349902,48.852968",
  "end":   "2.369248,48.853110",
  "profile": "car",
  "optimization": "fastest",
  "constraints": [
    {"constraintType":"banned","key":"wayType","operator":"=","value":"tunnel"}
  ],
  "getSteps": true,
  "getBbox": true
}
```

---

## 5. Hors scope du module

| Endpoint | Module qui devrait le porter |
|---|---|
| `/navigation/isochrone` | Module séparé (à créer si besoin) |
| `/geocodage/*` | Module séparé pour le géocodage |

Le présent module se limite volontairement au **calcul d'itinéraire**.
