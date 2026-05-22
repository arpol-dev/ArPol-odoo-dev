# Guide d'utilisation — consommer le connecteur

Ce document s'adresse aux développeurs qui écrivent un **module
consommateur** souhaitant calculer des itinéraires via la Géoplateforme.

---

## 1. Dépendre du module

Dans le `__manifest__.py` de votre module consommateur :

```python
{
    'name': "Mon module qui calcule des itinéraires",
    'depends': ['geoplateforme_calcul_itineraire'],
    ...
}
```

C'est tout. Une fois installé, le service `geoplateforme.itineraire` est
disponible via `self.env`.

---

## 2. Récupérer le service

`geoplateforme.itineraire` est un `AbstractModel` Odoo. On y accède
exactement comme un modèle normal, mais sans `create()` / `browse()` :
les méthodes sont décorées `@api.model` et s'appellent sur le recordset
vide.

```python
service = self.env['geoplateforme.itineraire']
```

---

## 3. Calculer un itinéraire

### Cas simple

```python
route = service.compute_route(
    start=(2.349902, 48.852968),  # tuple (lon, lat)
    end="2.369248,48.853110",     # ou directement "lon,lat"
)
```

La valeur de retour est le `dict` JSON brut renvoyé par l'API IGN
(typiquement avec les clés `distance`, `duration`, `geometry`, etc.).

### Avec options

```python
route = service.compute_route(
    start=(2.337306, 48.849319),
    end=(2.367776, 48.852891),
    resource="bdtopo-valhalla",
    profile="pedestrian",
    optimization="shortest",
    intermediates=[(2.354, 48.850)],
    get_steps=True,
    get_bbox=True,
    distance_unit="meter",
    time_unit="second",
)
```

### Avec contraintes (POST recommandé)

```python
route = service.compute_route(
    start=(2.337306, 48.849319),
    end=(2.367776, 48.852891),
    constraints=[{
        "constraintType": "banned",
        "key": "wayType",
        "operator": "=",
        "value": "tunnel",
    }],
    use_post=True,
)
```

### Paramètre `extra_params`

Si l'IGN ajoute un nouveau paramètre que le wrapper Python n'expose pas
encore, il peut être passé tel quel via `extra_params` :

```python
route = service.compute_route(
    start=(2.337, 48.849),
    end=(2.368, 48.853),
    extra_params={"futureOption": "value"},
)
```

---

## 4. Découvrir les capacités

```python
caps = service.get_capabilities()
print(caps)

resources = service.list_available_resources()
# ex: ['bdtopo-osrm', 'bdtopo-valhalla', 'bdtopo-pgr']

profiles = service.list_available_profiles(resource="bdtopo-osrm")
# ex: ['car', 'pedestrian']
```

`get_capabilities()` est mis en cache au niveau du process (TTL d'1
heure par défaut). Pour forcer un refresh :

```python
caps = service.get_capabilities(force_refresh=True)
# ou
service.clear_capabilities_cache()
```

---

## 5. Gestion des erreurs

Toutes les exceptions du connecteur héritent de
`odoo.exceptions.UserError` — elles s'affichent donc correctement si
elles remontent jusqu'à l'utilisateur.

```python
from odoo.addons.geoplateforme_calcul_itineraire.models.geoplateforme_exceptions import (
    GeoplateformeError,
    GeoplateformeNetworkError,
    GeoplateformeAPIError,
    GeoplateformeInvalidResponseError,
)

try:
    route = service.compute_route(start=..., end=...)
except GeoplateformeNetworkError:
    # Timeout / DNS / refus de connexion → retry possible
    ...
except GeoplateformeAPIError as e:
    if e.status_code == 429:
        # Quota dépassé → backoff
        ...
    else:
        raise
except GeoplateformeError:
    # Tout le reste (parsing JSON, etc.)
    raise
```

L'attribut `e.status_code` (et `e.body`) n'est défini que sur
`GeoplateformeAPIError`.

---

## 6. Étendre le connecteur par `_inherit`

Le pattern Odoo standard fonctionne :

```python
from odoo import api, models


class GeoplateformeItineraireCustom(models.AbstractModel):
    _inherit = 'geoplateforme.itineraire'

    @api.model
    def _request(self, path, method="GET", params=None, json_body=None):
        # Ex: ajouter du logging custom, du tracing, un rate-limiter…
        self._my_rate_limiter.acquire()
        return super()._request(path, method=method, params=params, json_body=json_body)
```

Vous pouvez surcharger :

| Méthode | Cas d'usage typique |
|---|---|
| `_request` | Rate-limiter, retry, tracing, log custom |
| `_get_base_url` | Pointer vers un proxy interne ou un mock en dev |
| `_normalize_point` | Accepter un format de point propre à votre code |
| `compute_route` | Pré- / post-traitement (cache base de données, etc.) |
| `_build_route_params` | Forcer des paramètres par défaut différents |

---

## 7. Configuration

Voir [`configuration.md`](configuration.md). Tous les paramètres sont
des `ir.config_parameter`, modifiables sans redémarrage.

---

## 8. Tests côté consommateur

Pour éviter d'appeler le vrai service IGN dans vos tests, mockez
`requests.request` (la couche utilisée par le module) ou surchargez
`_request` via `_inherit` dans un addon de test.

Exemple avec `unittest.mock` :

```python
from unittest.mock import patch
from odoo.tests.common import TransactionCase


class TestMyConsumer(TransactionCase):

    @patch(
        'odoo.addons.geoplateforme_calcul_itineraire.models'
        '.geoplateforme_itineraire.requests.request'
    )
    def test_route_call(self, mock_request):
        mock_request.return_value.ok = True
        mock_request.return_value.status_code = 200
        mock_request.return_value.json.return_value = {"distance": 1234}

        result = self.env['my.consumer'].do_something_with_route()
        self.assertEqual(result['distance'], 1234)
```
