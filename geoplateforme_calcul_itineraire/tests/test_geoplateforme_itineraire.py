# -*- coding: utf-8 -*-
"""Tests unitaires du connecteur `geoplateforme.itineraire`.

Tous les appels HTTP sont mockés via `unittest.mock.patch` sur la
fonction `requests.request` du module — aucun appel réseau réel n'est
effectué. Les fixtures JSON sont lues depuis `tests/fixtures/`.
"""

import json
import os
from unittest.mock import MagicMock, patch

import requests

from odoo.tests import TransactionCase, tagged

from odoo.addons.geoplateforme_calcul_itineraire.models import (
    geoplateforme_itineraire as service_module,
)
from odoo.addons.geoplateforme_calcul_itineraire.models.geoplateforme_exceptions import (
    GeoplateformeAPIError,
    GeoplateformeInvalidResponseError,
    GeoplateformeNetworkError,
)


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
REQUESTS_PATH = (
    "odoo.addons.geoplateforme_calcul_itineraire.models"
    ".geoplateforme_itineraire.requests.request"
)


def _load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _make_response(status_code=200, json_data=None, text=None, raise_json=False):
    """Construit un mock minimal d'objet `requests.Response`."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.text = text if text is not None else (
        json.dumps(json_data) if json_data is not None else ""
    )
    if raise_json:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = json_data if json_data is not None else {}
    return resp


@tagged("post_install", "-at_install")
class TestGeoplateformeItineraire(TransactionCase):

    def setUp(self):
        super().setUp()
        self.service = self.env["geoplateforme.itineraire"]
        # Reset systématique du cache process pour isolation des tests.
        self.service.clear_capabilities_cache()
        self.caps_payload = _load_fixture("capabilities_response.json")
        self.route_payload = _load_fixture("itineraire_response.json")

    # ------------------------------------------------------------------
    # /getCapabilities
    # ------------------------------------------------------------------

    @patch(REQUESTS_PATH)
    def test_get_capabilities_calls_correct_url(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.caps_payload)

        result = self.service.get_capabilities()

        self.assertEqual(result, self.caps_payload)
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        self.assertEqual(args[0], "GET")
        self.assertTrue(args[1].endswith("/getCapabilities"))

    @patch(REQUESTS_PATH)
    def test_get_capabilities_caches_result(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.caps_payload)

        self.service.get_capabilities()
        self.service.get_capabilities()
        self.service.get_capabilities()

        # Cache process actif : un seul appel HTTP effectué.
        self.assertEqual(mock_request.call_count, 1)

    @patch(REQUESTS_PATH)
    def test_get_capabilities_force_refresh(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.caps_payload)

        self.service.get_capabilities()
        self.service.get_capabilities(force_refresh=True)

        self.assertEqual(mock_request.call_count, 2)

    @patch(REQUESTS_PATH)
    def test_capabilities_ttl_zero_disables_cache(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.caps_payload)
        self.env["ir.config_parameter"].sudo().set_param(
            "geoplateforme.capabilities_cache_ttl", "0"
        )
        self.service.clear_capabilities_cache()

        self.service.get_capabilities()
        self.service.get_capabilities()

        self.assertEqual(mock_request.call_count, 2)

    # ------------------------------------------------------------------
    # Helpers de découverte
    # ------------------------------------------------------------------

    @patch(REQUESTS_PATH)
    def test_list_available_resources(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.caps_payload)
        resources = self.service.list_available_resources()
        self.assertIn("bdtopo-osrm", resources)
        self.assertIn("bdtopo-valhalla", resources)

    @patch(REQUESTS_PATH)
    def test_list_available_profiles_filtered(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.caps_payload)
        profiles = self.service.list_available_profiles(resource="bdtopo-osrm")
        self.assertIn("car", profiles)
        self.assertIn("pedestrian", profiles)

    # ------------------------------------------------------------------
    # _normalize_point
    # ------------------------------------------------------------------

    def test_normalize_point_accepts_string(self):
        self.assertEqual(
            self.service._normalize_point("2.337,48.849"),
            "2.337,48.849",
        )

    def test_normalize_point_strips_string(self):
        self.assertEqual(
            self.service._normalize_point("  2.337,48.849 "),
            "2.337,48.849",
        )

    def test_normalize_point_accepts_tuple(self):
        self.assertEqual(
            self.service._normalize_point((2.337306, 48.849319)),
            "2.337306,48.849319",
        )

    def test_normalize_point_accepts_list(self):
        self.assertEqual(
            self.service._normalize_point([2.337, 48.849]),
            "2.337,48.849",
        )

    def test_normalize_point_rejects_bad_format(self):
        with self.assertRaises(ValueError):
            self.service._normalize_point("not-a-point")
        with self.assertRaises(ValueError):
            self.service._normalize_point((1, 2, 3))

    # ------------------------------------------------------------------
    # compute_route — GET
    # ------------------------------------------------------------------

    @patch(REQUESTS_PATH)
    def test_compute_route_minimal_params(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.route_payload)

        result = self.service.compute_route(
            start="2.337306,48.849319",
            end="2.367776,48.852891",
        )

        self.assertEqual(result, self.route_payload)
        args, kwargs = mock_request.call_args
        self.assertEqual(args[0], "GET")
        self.assertTrue(args[1].endswith("/itineraire"))
        sent_params = kwargs["params"]
        self.assertEqual(sent_params["resource"], "bdtopo-osrm")
        self.assertEqual(sent_params["start"], "2.337306,48.849319")
        self.assertEqual(sent_params["end"], "2.367776,48.852891")
        self.assertEqual(sent_params["profile"], "car")
        self.assertEqual(sent_params["optimization"], "fastest")

    @patch(REQUESTS_PATH)
    def test_compute_route_normalizes_tuple_points(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.route_payload)

        self.service.compute_route(
            start=(2.337306, 48.849319),
            end=(2.367776, 48.852891),
        )

        sent_params = mock_request.call_args.kwargs["params"]
        self.assertEqual(sent_params["start"], "2.337306,48.849319")
        self.assertEqual(sent_params["end"], "2.367776,48.852891")

    @patch(REQUESTS_PATH)
    def test_compute_route_with_intermediates_serialized(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.route_payload)

        self.service.compute_route(
            start=(2.337, 48.849),
            end=(2.368, 48.853),
            intermediates=[(2.350, 48.850), "2.360,48.851"],
        )

        sent_params = mock_request.call_args.kwargs["params"]
        # intermediates est une liste — sérialisée en JSON pour GET.
        parsed = json.loads(sent_params["intermediates"])
        self.assertEqual(parsed, ["2.35,48.85", "2.360,48.851"])

    @patch(REQUESTS_PATH)
    def test_compute_route_booleans_serialized_as_strings(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.route_payload)

        self.service.compute_route(
            start=(2.337, 48.849),
            end=(2.368, 48.853),
            get_steps=True,
            get_bbox=False,
        )

        sent_params = mock_request.call_args.kwargs["params"]
        self.assertEqual(sent_params["getSteps"], "true")
        self.assertEqual(sent_params["getBbox"], "false")

    # ------------------------------------------------------------------
    # compute_route — POST
    # ------------------------------------------------------------------

    @patch(REQUESTS_PATH)
    def test_compute_route_with_constraints_post(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.route_payload)

        constraints = [{
            "constraintType": "banned",
            "key": "wayType",
            "operator": "=",
            "value": "tunnel",
        }]

        self.service.compute_route(
            start=(2.337, 48.849),
            end=(2.368, 48.853),
            constraints=constraints,
            use_post=True,
        )

        args, kwargs = mock_request.call_args
        self.assertEqual(args[0], "POST")
        body = kwargs["json"]
        # POST : corps JSON natif, constraints reste une liste Python.
        self.assertEqual(body["constraints"], constraints)
        self.assertIsNone(kwargs.get("params"))

    # ------------------------------------------------------------------
    # Gestion des erreurs
    # ------------------------------------------------------------------

    @patch(REQUESTS_PATH)
    def test_compute_route_http_error_raises_api_error(self, mock_request):
        mock_request.return_value = _make_response(
            status_code=500,
            json_data={"error": "boom"},
            text='{"error":"boom"}',
        )

        with self.assertRaises(GeoplateformeAPIError) as cm:
            self.service.compute_route(start=(2.337, 48.849), end=(2.368, 48.853))

        self.assertEqual(cm.exception.status_code, 500)
        self.assertIn("boom", cm.exception.body or "")

    @patch(REQUESTS_PATH)
    def test_compute_route_timeout_raises_network_error(self, mock_request):
        mock_request.side_effect = requests.Timeout("timed out")

        with self.assertRaises(GeoplateformeNetworkError):
            self.service.compute_route(start=(2.337, 48.849), end=(2.368, 48.853))

    @patch(REQUESTS_PATH)
    def test_compute_route_connection_error_raises_network_error(self, mock_request):
        mock_request.side_effect = requests.ConnectionError("dns fail")

        with self.assertRaises(GeoplateformeNetworkError):
            self.service.compute_route(start=(2.337, 48.849), end=(2.368, 48.853))

    @patch(REQUESTS_PATH)
    def test_compute_route_invalid_json_raises(self, mock_request):
        mock_request.return_value = _make_response(
            status_code=200, text="<html>not json</html>", raise_json=True,
        )

        with self.assertRaises(GeoplateformeInvalidResponseError):
            self.service.compute_route(start=(2.337, 48.849), end=(2.368, 48.853))

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @patch(REQUESTS_PATH)
    def test_config_param_overrides_base_url(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.route_payload)
        self.env["ir.config_parameter"].sudo().set_param(
            "geoplateforme.base_url", "https://geo-proxy.test/navigation"
        )

        self.service.compute_route(start=(2.337, 48.849), end=(2.368, 48.853))

        args, _kwargs = mock_request.call_args
        self.assertEqual(args[1], "https://geo-proxy.test/navigation/itineraire")

    @patch(REQUESTS_PATH)
    def test_config_param_overrides_default_resource(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.route_payload)
        self.env["ir.config_parameter"].sudo().set_param(
            "geoplateforme.default_resource", "bdtopo-valhalla"
        )

        self.service.compute_route(start=(2.337, 48.849), end=(2.368, 48.853))

        sent_params = mock_request.call_args.kwargs["params"]
        self.assertEqual(sent_params["resource"], "bdtopo-valhalla")

    @patch(REQUESTS_PATH)
    def test_config_param_overrides_timeout(self, mock_request):
        mock_request.return_value = _make_response(json_data=self.route_payload)
        self.env["ir.config_parameter"].sudo().set_param(
            "geoplateforme.timeout", "42"
        )

        self.service.compute_route(start=(2.337, 48.849), end=(2.368, 48.853))

        timeout = mock_request.call_args.kwargs["timeout"]
        self.assertEqual(timeout, 42.0)

    # ------------------------------------------------------------------
    # Cache : sanity
    # ------------------------------------------------------------------

    def test_clear_capabilities_cache_resets_state(self):
        service_module._capabilities_cache["data"] = {"x": 1}
        service_module._capabilities_cache["expires_at"] = 99999999.0
        self.service.clear_capabilities_cache()
        self.assertIsNone(service_module._capabilities_cache["data"])
        self.assertIsNone(service_module._capabilities_cache["expires_at"])
