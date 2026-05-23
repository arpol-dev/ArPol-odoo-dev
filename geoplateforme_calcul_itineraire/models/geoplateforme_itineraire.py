# -*- coding: utf-8 -*-
"""Connecteur Odoo vers l'API de calcul d'itinéraire de la Géoplateforme IGN.

Ce module expose un :class:`odoo.models.AbstractModel` accessible via::

    self.env['geoplateforme.itineraire']

Il encapsule les deux endpoints utiles côté itinéraire :

* ``GET  /getCapabilities`` — découverte (ressources, profils, options)
* ``GET|POST /itineraire``  — calcul d'un itinéraire entre deux points

Conception générale
-------------------

1. **Une seule couche HTTP** (:meth:`_request`) factorise les appels et la
   gestion d'erreurs. Toutes les méthodes publiques passent par elle.
2. **Configuration via ir.config_parameter** avec valeurs par défaut codées
   en dur (cf. :meth:`_get_base_url` et compagnie). Aucune UI dédiée : un
   admin peut surcharger via *Paramètres techniques → Paramètres système*.
3. **Cache mémoire process** pour ``/getCapabilities`` (les capacités IGN
   changent rarement). Cache invalidable via ``force_refresh=True``.
4. **Sortie : dict JSON brut** tel que retourné par l'API. Les consommateurs
   accèdent aux champs directement (``result['distance']``, etc.) — cela
   garantit la transparence et la fidélité au format documenté par l'IGN.
5. **Extensible** : tout module tiers peut faire ``_inherit =
   'geoplateforme.itineraire'`` pour surcharger n'importe quelle méthode
   (ex. ajouter un cache persistant, un rate-limiter, du logging custom).

Référence API officielle :
    https://cartes.gouv.fr/aide/fr/guides-utilisateur/utiliser-les-services-de-la-geoplateforme/calcul-itineraire/
    Swagger : https://data.geopf.fr/navigation/openapi/
"""

import json
import logging
import time

import requests

from odoo import _, api, models

from .geoplateforme_exceptions import (
    GeoplateformeAPIError,
    GeoplateformeInvalidResponseError,
    GeoplateformeNetworkError,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes (valeurs par défaut, surchargeables via ir.config_parameter)
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://data.geopf.fr/navigation"
DEFAULT_TIMEOUT = 10.0
DEFAULT_RESOURCE = "bdtopo-osrm"
DEFAULT_PROFILE = "car"
DEFAULT_OPTIMIZATION = "fastest"
DEFAULT_CAPABILITIES_TTL = 3600  # secondes

# Cache process-level pour /getCapabilities.
# Forme : {"data": <dict|None>, "expires_at": <float|None>}.
# Partagé par tous les workers Python d'un même process (utile en mode dev
# mono-worker ; chaque worker en multi-process fera son propre fetch).
_capabilities_cache = {"data": None, "expires_at": None}


class GeoplateformeItineraire(models.AbstractModel):
    """Connecteur API Géoplateforme — calcul d'itinéraire.

    AbstractModel (pas de table SQL, pas d'enregistrement). On y accède via::

        service = self.env['geoplateforme.itineraire']
        caps = service.get_capabilities()
        route = service.compute_route(start="2.33,48.84", end="2.36,48.85")
    """

    _name = "geoplateforme.itineraire"
    _description = "Connecteur API Géoplateforme — calcul d'itinéraire"

    # ------------------------------------------------------------------
    # Configuration (ir.config_parameter avec fallback en dur)
    # ------------------------------------------------------------------

    @api.model
    def _get_config_param(self, key, default):
        """Récupère un ``ir.config_parameter`` avec valeur par défaut."""
        return self.env["ir.config_parameter"].sudo().get_param(key, default)

    @api.model
    def _get_base_url(self):
        """URL de base de l'API Géoplateforme (sans slash final)."""
        return self._get_config_param("geoplateforme.base_url", DEFAULT_BASE_URL).rstrip("/")

    @api.model
    def _get_timeout(self):
        """Timeout HTTP (secondes, float)."""
        return float(self._get_config_param("geoplateforme.timeout", DEFAULT_TIMEOUT))

    @api.model
    def _get_default_resource(self):
        """Nom de ressource par défaut (``bdtopo-osrm``, ``bdtopo-valhalla``, …)."""
        return self._get_config_param("geoplateforme.default_resource", DEFAULT_RESOURCE)

    @api.model
    def _get_default_profile(self):
        """Profil par défaut (``car``, ``pedestrian``, …)."""
        return self._get_config_param("geoplateforme.default_profile", DEFAULT_PROFILE)

    @api.model
    def _get_default_optimization(self):
        """Optimisation par défaut (``fastest`` ou ``shortest``)."""
        return self._get_config_param("geoplateforme.default_optimization", DEFAULT_OPTIMIZATION)

    @api.model
    def _get_capabilities_ttl(self):
        """TTL (en secondes) du cache de ``/getCapabilities``."""
        return int(self._get_config_param("geoplateforme.capabilities_cache_ttl", DEFAULT_CAPABILITIES_TTL))

    # ------------------------------------------------------------------
    # Couche HTTP unique
    # ------------------------------------------------------------------

    @api.model
    def _request(self, path, method="GET", params=None, json_body=None):
        """Envoie une requête HTTP à l'API Géoplateforme.

        Toutes les méthodes publiques du connecteur passent par cette
        fonction. C'est l'unique point de sortie réseau du module — utile
        pour mocker en test et pour centraliser logs/erreurs.

        :param str path: chemin relatif à la base URL (commence par ``/``).
        :param str method: ``GET`` ou ``POST``.
        :param dict|None params: query parameters (pour GET).
        :param dict|None json_body: corps JSON (pour POST).
        :returns: la réponse désérialisée (typiquement un ``dict``).
        :rtype: dict
        :raises GeoplateformeNetworkError: échec réseau (timeout, DNS…).
        :raises GeoplateformeAPIError: code HTTP non-2xx.
        :raises GeoplateformeInvalidResponseError: réponse non-JSON.
        """
        url = f"{self._get_base_url()}{path}"
        timeout = self._get_timeout()
        _logger.debug(
            "Géoplateforme %s %s params=%s json_body=%s timeout=%s",
            method, url, params, json_body, timeout,
        )

        start_ts = time.monotonic()
        try:
            response = requests.request(
                method,
                url,
                params=params,
                json=json_body,
                timeout=timeout,
                headers={"Accept": "application/json"},
            )
        except requests.Timeout as e:
            _logger.error("Géoplateforme timeout sur %s: %s", url, e)
            raise GeoplateformeNetworkError(
                _("Timeout lors de l'appel à la Géoplateforme (%s s).") % timeout
            )
        except requests.RequestException as e:
            _logger.error("Géoplateforme erreur réseau sur %s: %s", url, e)
            raise GeoplateformeNetworkError(
                _("Erreur réseau lors de l'appel à la Géoplateforme : %s") % e
            )

        elapsed = time.monotonic() - start_ts
        _logger.info(
            "Géoplateforme %s %s -> HTTP %s (%.0f ms)",
            method, path, response.status_code, elapsed * 1000,
        )

        if not response.ok:
            body_preview = (response.text or "")[:500]
            _logger.warning(
                "Géoplateforme HTTP %s sur %s : %s",
                response.status_code, url, body_preview,
            )
            raise GeoplateformeAPIError(
                _("Erreur API Géoplateforme (HTTP %(code)s) : %(body)s") % {
                    "code": response.status_code,
                    "body": body_preview,
                },
                status_code=response.status_code,
                body=response.text,
            )

        try:
            return response.json()
        except ValueError:
            _logger.error(
                "Géoplateforme réponse non-JSON sur %s : %r",
                url, (response.text or "")[:200],
            )
            raise GeoplateformeInvalidResponseError(
                _("Réponse non-JSON reçue de la Géoplateforme.")
            )

    # ------------------------------------------------------------------
    # Helpers de normalisation / sérialisation des paramètres
    # ------------------------------------------------------------------

    @api.model
    def _normalize_point(self, point):
        """Normalise un point en chaîne ``"lon,lat"`` (EPSG:4326).

        Accepte :
        * ``"lon,lat"`` (str, retourné tel quel après strip)
        * ``(lon, lat)`` (tuple/list de 2 numériques)

        :param point: la valeur à normaliser.
        :returns: la chaîne ``"lon,lat"``.
        :rtype: str
        :raises ValueError: si le format n'est pas reconnu.
        """
        if isinstance(point, str):
            cleaned = point.strip()
            if cleaned.count(",") != 1:
                raise ValueError(
                    "Point '%s' invalide : format attendu 'lon,lat'." % point
                )
            return cleaned
        if isinstance(point, (tuple, list)) and len(point) == 2:
            return "%s,%s" % (point[0], point[1])
        raise ValueError(
            "Point %r invalide : attendu 'lon,lat' ou (lon, lat)." % (point,)
        )

    @api.model
    def _build_route_params(self, start, end, resource=None, profile=None,
                            optimization=None, intermediates=None,
                            geometry_format=None, get_steps=None, get_bbox=None,
                            distance_unit=None, time_unit=None, crs=None,
                            constraints=None, ways_attributes=None,
                            extra_params=None):
        """Construit le dict de paramètres pour ``/itineraire``.

        Mappe les arguments Python (snake_case, valeurs natives) vers les
        clés et formats attendus par l'API IGN (camelCase, chaînes).
        Les paramètres ``None`` sont omis afin de laisser l'API appliquer
        ses propres valeurs par défaut.

        :returns: dict prêt à être passé en query string (GET) ou body (POST).
        :rtype: dict
        """
        params = {
            "resource": resource or self._get_default_resource(),
            "start": self._normalize_point(start),
            "end": self._normalize_point(end),
        }

        if profile is not None:
            params["profile"] = profile
        else:
            params["profile"] = self._get_default_profile()

        if optimization is not None:
            params["optimization"] = optimization
        else:
            params["optimization"] = self._get_default_optimization()

        if intermediates:
            params["intermediates"] = [self._normalize_point(p) for p in intermediates]
        if geometry_format is not None:
            params["geometryFormat"] = geometry_format
        if get_steps is not None:
            params["getSteps"] = bool(get_steps)
        if get_bbox is not None:
            params["getBbox"] = bool(get_bbox)
        if distance_unit is not None:
            params["distanceUnit"] = distance_unit
        if time_unit is not None:
            params["timeUnit"] = time_unit
        if crs is not None:
            params["crs"] = crs
        if constraints:
            params["constraints"] = constraints  # list[dict] — sérialisé plus tard si GET
        if ways_attributes:
            params["waysAttributes"] = ways_attributes
        if extra_params:
            params.update(extra_params)

        return params

    @api.model
    def _serialize_get_params(self, params):
        """Aplatie les valeurs complexes pour usage en query string.

        L'API IGN accepte les listes / objets sous forme JSON-stringifiée
        en paramètre GET. Cette méthode convertit chaque valeur non-scalaire
        en chaîne JSON, et passe les booléens en ``"true"``/``"false"``.

        :param dict params: paramètres « riches » construits par
            :meth:`_build_route_params`.
        :returns: dict ``{str: str}`` directement utilisable par ``requests``.
        :rtype: dict
        """
        flat = {}
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, bool):
                flat[key] = "true" if value else "false"
            elif isinstance(value, (list, dict)):
                flat[key] = json.dumps(value, separators=(",", ":"))
            else:
                flat[key] = str(value)
        return flat

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    @api.model
    def get_capabilities(self, force_refresh=False):
        """Récupère les capacités de l'API Géoplateforme (``/getCapabilities``).

        La réponse décrit les opérations disponibles, les ressources
        (``bdtopo-osrm``, ``bdtopo-valhalla``, ``bdtopo-pgr``), les profils
        (``car``, ``pedestrian``) et les options supportées. Elle change
        très rarement → on la cache en mémoire process pour ``ttl`` secondes
        (cf. :meth:`_get_capabilities_ttl`).

        :param bool force_refresh: ignore le cache et refait l'appel.
        :returns: la réponse JSON brute de l'API.
        :rtype: dict
        :raises GeoplateformeError: en cas d'erreur réseau / HTTP / parsing.
        """
        now = time.monotonic()
        if not force_refresh:
            cached = _capabilities_cache.get("data")
            expires_at = _capabilities_cache.get("expires_at")
            if cached is not None and expires_at and now < expires_at:
                _logger.debug("Géoplateforme capabilities servi depuis le cache.")
                return cached

        data = self._request("/getCapabilities", method="GET")
        ttl = self._get_capabilities_ttl()
        _capabilities_cache["data"] = data
        _capabilities_cache["expires_at"] = now + ttl
        return data

    @api.model
    def compute_route(self, start, end, resource=None, profile=None,
                      optimization=None, intermediates=None,
                      geometry_format=None, get_steps=None, get_bbox=None,
                      distance_unit=None, time_unit=None, crs=None,
                      constraints=None, ways_attributes=None,
                      use_post=False, extra_params=None):
        """Calcule un itinéraire (``/itineraire``).

        Wrapper Pythonique autour de l'endpoint ``/itineraire``. Construit
        les paramètres, choisit GET ou POST, et renvoie le JSON brut.

        :param start: point de départ — ``"lon,lat"`` ou ``(lon, lat)``.
        :param end: point d'arrivée — ``"lon,lat"`` ou ``(lon, lat)``.
        :param str|None resource: ressource (défaut config —
            ``bdtopo-osrm`` en standard).
        :param str|None profile: ``car`` ou ``pedestrian`` (défaut config).
        :param str|None optimization: ``fastest`` ou ``shortest``
            (défaut config).
        :param list|None intermediates: liste de points intermédiaires.
        :param str|None geometry_format: ``geojson`` ou ``polyline``.
        :param bool|None get_steps: inclure les étapes de navigation.
        :param bool|None get_bbox: inclure la bounding box de l'itinéraire.
        :param str|None distance_unit: ``meter`` ou ``kilometer``.
        :param str|None time_unit: ``second``, ``minute``, ``hour``.
        :param str|None crs: système de coordonnées (par défaut EPSG:4326).
        :param list|None constraints: contraintes d'exclusion
            (ex. ``[{"constraintType": "banned", "key": "wayType",
            "operator": "=", "value": "tunnel"}]``).
        :param list|None ways_attributes: attributs de segments à retourner.
        :param bool use_post: utilise POST au lieu de GET (recommandé si
            beaucoup de paramètres / contraintes complexes).
        :param dict|None extra_params: paramètres additionnels passés tels
            quels — utile pour rester compatible si l'IGN ajoute des options.

        :returns: la réponse JSON brute de l'API (typiquement un dict
            contenant ``geometry``, ``distance``, ``duration``, etc.).
        :rtype: dict
        :raises GeoplateformeError: en cas d'erreur réseau / HTTP / parsing.

        Exemple::

            route = self.env['geoplateforme.itineraire'].compute_route(
                start=(2.337306, 48.849319),
                end=(2.367776, 48.852891),
                profile="car",
                optimization="fastest",
                get_steps=True,
            )
            print(route['distance'], route['duration'])
        """
        params = self._build_route_params(
            start=start, end=end,
            resource=resource, profile=profile, optimization=optimization,
            intermediates=intermediates, geometry_format=geometry_format,
            get_steps=get_steps, get_bbox=get_bbox,
            distance_unit=distance_unit, time_unit=time_unit, crs=crs,
            constraints=constraints, ways_attributes=ways_attributes,
            extra_params=extra_params,
        )

        if use_post:
            return self._request("/itineraire", method="POST", json_body=params)
        return self._request(
            "/itineraire", method="GET",
            params=self._serialize_get_params(params),
        )

    # ------------------------------------------------------------------
    # Helpers de découverte (construits sur get_capabilities)
    # ------------------------------------------------------------------

    @api.model
    def list_available_resources(self):
        """Liste les identifiants des ressources disponibles.

        Lit ``/getCapabilities`` (via cache) et extrait les noms des
        ressources. Robuste à plusieurs formes possibles de payload IGN
        (la structure exacte n'est pas figée dans la doc publique).

        :returns: liste de chaînes (vide si non extractible).
        :rtype: list[str]
        """
        caps = self.get_capabilities()
        resources = caps.get("resources") or caps.get("operations") or []
        names = []
        if isinstance(resources, list):
            for item in resources:
                if isinstance(item, dict):
                    name = item.get("id") or item.get("name") or item.get("resource")
                    if name:
                        names.append(name)
                elif isinstance(item, str):
                    names.append(item)
        elif isinstance(resources, dict):
            names = list(resources.keys())
        return names

    @api.model
    def list_available_profiles(self, resource=None):
        """Liste les profils disponibles, éventuellement filtrés par ressource.

        :param str|None resource: si fourni, ne retourne que les profils
            supportés par cette ressource.
        :returns: liste de chaînes (vide si non extractible).
        :rtype: list[str]
        """
        caps = self.get_capabilities()
        resources = caps.get("resources") or []
        profiles = set()
        if isinstance(resources, list):
            for item in resources:
                if not isinstance(item, dict):
                    continue
                rname = item.get("id") or item.get("name")
                if resource and rname != resource:
                    continue
                item_profiles = item.get("profiles") or []
                if isinstance(item_profiles, list):
                    profiles.update(p for p in item_profiles if isinstance(p, str))
                elif isinstance(item_profiles, dict):
                    profiles.update(item_profiles.keys())
        return sorted(profiles)

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    @api.model
    def clear_capabilities_cache(self):
        """Vide le cache process de ``/getCapabilities``.

        Utile en tests ou pour forcer un refresh sans paramètre côté
        consommateur.
        """
        _capabilities_cache["data"] = None
        _capabilities_cache["expires_at"] = None
