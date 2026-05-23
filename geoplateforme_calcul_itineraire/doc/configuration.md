# Configuration

Toute la configuration du connecteur passe par **`ir.config_parameter`**.
Aucune écriture n'est effectuée à l'installation : les valeurs par défaut
sont codées dans `models/geoplateforme_itineraire.py`. Surcharger un
paramètre revient simplement à **créer la clé correspondante** dans
*Paramètres techniques → Paramètres système*.

---

## Paramètres exposés

| Clé | Type | Défaut | Rôle |
|---|---|---|---|
| `geoplateforme.base_url` | str | `https://data.geopf.fr/navigation` | URL de base de l'API (sans `/` final) |
| `geoplateforme.timeout` | float (s) | `10` | Timeout HTTP côté `requests` |
| `geoplateforme.default_resource` | str | `bdtopo-osrm` | Ressource utilisée si `resource=None` dans `compute_route` |
| `geoplateforme.default_profile` | str | `car` | Profil par défaut |
| `geoplateforme.default_optimization` | str | `fastest` | `fastest` ou `shortest` |
| `geoplateforme.capabilities_cache_ttl` | int (s) | `3600` | TTL du cache mémoire de `/getCapabilities` |

---

## Procédure de modification

### Via l'UI Odoo

1. *Mode développeur activé* → menu *Paramètres techniques* →
   *Paramètres système*.
2. **Créer** une ligne avec la clé voulue (ex. `geoplateforme.timeout`)
   et la valeur souhaitée (ex. `20`).
3. La nouvelle valeur est prise en compte au prochain appel —
   aucun redémarrage requis.

### En code (init, migration, hook…)

```python
self.env['ir.config_parameter'].sudo().set_param(
    'geoplateforme.timeout', '30'
)
```

### Lecture côté code

```python
self.env['ir.config_parameter'].sudo().get_param(
    'geoplateforme.timeout', '10'
)
```

Ou, plus idiomatique : utiliser les helpers du service (qui appliquent
le bon fallback) :

```python
service = self.env['geoplateforme.itineraire']
service._get_timeout()
service._get_base_url()
service._get_default_resource()
```

---

## Cas particuliers

### Pointer vers un proxy interne / un mock

Si vous routez les appels via un reverse proxy ou un mock pendant des
tests d'intégration :

```
geoplateforme.base_url = https://geo-proxy.interne.lan/navigation
```

Toutes les méthodes du service utiliseront immédiatement cette URL.

### Désactiver le cache `/getCapabilities`

Mettre le TTL à `0` :

```
geoplateforme.capabilities_cache_ttl = 0
```

Ou, depuis le code :

```python
self.env['geoplateforme.itineraire'].clear_capabilities_cache()
```

### Changer le timeout pour les longs calculs (Valhalla + contraintes)

```
geoplateforme.timeout = 30
```
