# Géoplateforme — Calcul d'itinéraire

Connecteur Odoo v18 vers l'API de **calcul d'itinéraire** de la
Géoplateforme IGN (`https://data.geopf.fr/navigation/`).

> Module **de base** : il n'ajoute aucun écran, aucun menu, aucun modèle
> métier. Il expose un service Python (`geoplateforme.itineraire`) que
> d'autres modules viennent consommer pour intégrer du calcul
> d'itinéraire dans leurs propres processus (livraison, planning, fiches
> partenaires, etc.).

---

## Sommaire

- [Vue d'ensemble](#vue-densemble)
- [Installation](#installation)
- [Démarrage rapide](#démarrage-rapide)
- [Endpoints couverts](#endpoints-couverts)
- [Configuration](#configuration)
- [Gestion des erreurs](#gestion-des-erreurs)
- [Tests](#tests)
- [Documentation détaillée](#documentation-détaillée)
- [Licence et auteur](#licence-et-auteur)

---

## Vue d'ensemble

L'API Géoplateforme de l'IGN propose un service public (pas de clé API
requise) pour calculer des itinéraires sur le territoire français à
partir de la BD TOPO®. Ce module fournit un connecteur Odoo idiomatique
pour interroger cette API :

- une seule classe (`geoplateforme.itineraire`, AbstractModel) ;
- une couche HTTP unique avec gestion d'erreurs typées ;
- cache mémoire pour `/getCapabilities` ;
- configuration via `ir.config_parameter` ;
- sortie en `dict` Python brut (fidèle à la réponse JSON de l'API).

Le module est conçu pour être **étendu par `_inherit`** depuis n'importe
quel autre module Odoo (ajout de cache persistant, rate-limiter,
logging, etc.).

---

## Installation

### Dépendances

- Odoo 18.0
- Python : `requests` (déjà inclus dans l'image Odoo standard).

### Mise en place

1. Copier le dossier `geoplateforme_calcul_itineraire/` dans votre
   `addons_path`.
2. Mettre à jour la liste des modules (Apps → *Update Apps List*).
3. Installer le module **Géoplateforme - Calcul d'itinéraire**.

Aucune configuration initiale n'est requise — les valeurs par défaut
ciblent directement l'API publique IGN.

---

## Démarrage rapide

Depuis n'importe quel modèle Odoo ou depuis le shell :

```python
service = self.env['geoplateforme.itineraire']

# 1) Découvrir l'API (cache process actif)
caps = service.get_capabilities()
print(service.list_available_resources())  # ex: ['bdtopo-osrm', 'bdtopo-valhalla', ...]

# 2) Calculer un itinéraire (Paris : Notre-Dame -> Bastille)
route = service.compute_route(
    start=(2.349902, 48.852968),
    end=(2.369248, 48.853110),
    profile="car",
    optimization="fastest",
    get_steps=True,
)
print(route['distance'], route['duration'])
```

Plus d'exemples dans [`doc/examples.md`](doc/examples.md).

---

## Endpoints couverts

| Endpoint | Méthodes | Méthode service |
|---|---|---|
| `GET /navigation/getCapabilities` | GET | `get_capabilities(force_refresh=False)` |
| `GET\|POST /navigation/itineraire` | GET, POST | `compute_route(start, end, **opts)` |

Quota IGN : **5 requêtes/seconde par IP**. Authentification : aucune.

Référence API complète : [`doc/api-reference.md`](doc/api-reference.md).

---

## Configuration

Tous les paramètres sont stockés dans `ir.config_parameter` et ont des
valeurs par défaut codées dans le module — aucune écriture n'est
effectuée à l'installation. Pour surcharger : *Paramètres techniques →
Paramètres système*.

| Clé | Défaut | Rôle |
|---|---|---|
| `geoplateforme.base_url` | `https://data.geopf.fr/navigation` | URL de base de l'API |
| `geoplateforme.timeout` | `10` | Timeout HTTP (secondes) |
| `geoplateforme.default_resource` | `bdtopo-osrm` | Ressource par défaut |
| `geoplateforme.default_profile` | `car` | Profil par défaut |
| `geoplateforme.default_optimization` | `fastest` | Optimisation par défaut |
| `geoplateforme.capabilities_cache_ttl` | `3600` | TTL cache `/getCapabilities` |

Détails : [`doc/configuration.md`](doc/configuration.md).

---

## Gestion des erreurs

Le connecteur lève trois sous-classes d'`odoo.exceptions.UserError` :

```python
from odoo.addons.geoplateforme_calcul_itineraire.models.geoplateforme_exceptions import (
    GeoplateformeError,           # parent — attrape tout
    GeoplateformeNetworkError,    # timeout, DNS, refus
    GeoplateformeAPIError,        # HTTP non-2xx (status_code, body)
    GeoplateformeInvalidResponseError,  # réponse non-JSON
)
```

Exemple : [`doc/usage.md`](doc/usage.md#gestion-des-erreurs).

---

## Tests

```bash
odoo --test-tags=geoplateforme_calcul_itineraire \
     -d <db> --stop-after-init
```

Tous les tests mockent `requests.request` — aucun appel réseau n'est
effectué.

---

## Documentation détaillée

- [`doc/api-reference.md`](doc/api-reference.md) — référence complète de
  l'API IGN couverte.
- [`doc/usage.md`](doc/usage.md) — guide pour consommer le service
  depuis un autre module.
- [`doc/examples.md`](doc/examples.md) — exemples concrets prêts à
  copier-coller.
- [`doc/configuration.md`](doc/configuration.md) — paramètres système
  exposés.

---

## Licence et auteur

- Licence : **AGPL-3.0-or-later**.
- Auteur : Armand Polmard — `contact@arpol.fr`.
