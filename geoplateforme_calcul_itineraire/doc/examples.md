# Exemples concrets

Tous les exemples ci-dessous tournent dans n'importe quel contexte
Odoo où `self.env` est défini (modèle, contrôleur, shell, server
action). On suppose :

```python
service = self.env['geoplateforme.itineraire']
```

---

## Exemple 1 — Itinéraire voiture simple avec étapes

Notre-Dame → Bastille, en voiture, le plus rapide, avec étapes
détaillées.

```python
route = service.compute_route(
    start=(2.349902, 48.852968),
    end=(2.369248, 48.853110),
    profile="car",
    optimization="fastest",
    get_steps=True,
)

print("Distance:", route.get("distance"))
print("Durée   :", route.get("duration"))
print("Étapes  :", len(route.get("portions") or route.get("steps") or []))
```

---

## Exemple 2 — Piéton + contrainte (pas de tunnel)

Le calcul est posté en POST car les contraintes complexes passent mal
dans une query string.

```python
route = service.compute_route(
    start=(2.337306, 48.849319),
    end=(2.367776, 48.852891),
    resource="bdtopo-valhalla",
    profile="pedestrian",
    optimization="shortest",
    constraints=[{
        "constraintType": "banned",
        "key": "wayType",
        "operator": "=",
        "value": "tunnel",
    }],
    distance_unit="meter",
    time_unit="second",
    get_bbox=True,
    use_post=True,
)
```

---

## Exemple 3 — Découverte avant calcul

Avant d'envoyer un calcul, on inspecte les ressources et profils
disponibles. Utile pour proposer un menu déroulant à l'utilisateur,
ou pour valider un paramètre avant l'appel.

```python
caps = service.get_capabilities()  # cache process activé par défaut

resources = service.list_available_resources()
# ['bdtopo-osrm', 'bdtopo-valhalla', 'bdtopo-pgr']

profiles_osrm = service.list_available_profiles(resource="bdtopo-osrm")
# ['car', ...]

if "pedestrian" not in service.list_available_profiles(resource="bdtopo-osrm"):
    raise UserError(_("Le profil piéton n'est plus supporté par bdtopo-osrm."))
```

---

## Exemple 4 — Extension via `_inherit` (cache base de données)

Cas d'usage : on veut mettre en cache **persistant** (en base) les
itinéraires les plus demandés afin de réduire les appels à l'IGN.

```python
import hashlib
import json

from odoo import api, models


class GeoplateformeItineraireDbCache(models.AbstractModel):
    _inherit = 'geoplateforme.itineraire'

    @api.model
    def compute_route(self, start, end, **kwargs):
        # Construit une clé déterministe depuis les paramètres normalisés
        params = self._build_route_params(start=start, end=end, **kwargs)
        cache_key = hashlib.sha1(
            json.dumps(params, sort_keys=True).encode("utf-8")
        ).hexdigest()

        Cache = self.env['my.route.cache'].sudo()
        existing = Cache.search([('cache_key', '=', cache_key)], limit=1)
        if existing:
            return json.loads(existing.payload)

        result = super().compute_route(start=start, end=end, **kwargs)
        Cache.create({
            'cache_key': cache_key,
            'payload': json.dumps(result),
        })
        return result
```

> `my.route.cache` est un modèle imaginaire dans le module consommateur,
> avec les champs `cache_key` (Char) et `payload` (Text).

---

## Exemple 5 — Utilisation depuis un Server Action

Action serveur attachée à `res.partner`, qui calcule la distance entre
deux partenaires sélectionnés à partir de leurs coordonnées (champs
`partner_latitude` / `partner_longitude` de `base_geolocalize`).

```python
# Code à coller dans une Action Serveur Python
if len(records) != 2:
    raise UserError(_("Sélectionnez exactement 2 contacts."))

a, b = records
if not (a.partner_longitude and a.partner_latitude
        and b.partner_longitude and b.partner_latitude):
    raise UserError(_("Coordonnées manquantes — géolocalisez d'abord."))

route = env['geoplateforme.itineraire'].compute_route(
    start=(a.partner_longitude, a.partner_latitude),
    end=(b.partner_longitude, b.partner_latitude),
    profile="car",
)

raise UserError(_("Distance : %(d)s — Durée : %(t)s") % {
    "d": route.get("distance"),
    "t": route.get("duration"),
})
```
