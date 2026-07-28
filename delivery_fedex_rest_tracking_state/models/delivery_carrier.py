# @author: Armand Polmard (contact@arpol.fr)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

import logging
from datetime import datetime

from odoo import models
from odoo.addons.delivery_fedex_rest.models.fedex_request import FedexRequest

_logger = logging.getLogger(__name__)

# Correspondance codes FedEx → valeurs delivery_state (OCA)
# Les codes non listés ici tombent par défaut sur 'in_transit'
_FEDEX_STATE_MAP = {
    "OC": "shipping_recorded_in_carrier",
    "DL": "customer_delivered",
    "CA": "canceled_shipment",
    # Exceptions et anomalies
    "SE": "incident",
    "DE": "incident",
    "DY": "incident",
    "EA": "incident",
    "DR": "incident",
    "RS": "incident",
}


class ProviderFedex(models.Model):
    _inherit = "delivery.carrier"

    def fedex_rest_tracking_state_update(self, picking):
        """Point d'entrée appelé par le cron delivery_state pour mettre à jour
        le statut de suivi d'un envoi FedEx.
        Attend la convention <delivery_type>_tracking_state_update(picking).
        """
        self.ensure_one()
        if not picking.carrier_tracking_ref:
            return

        # Utilise le premier numéro de tracking (numéro maître de l'envoi)
        master_tracking = picking.carrier_tracking_ref.split(",")[0].strip()

        srm = FedexRequest(self)
        try:
            response = srm._send_fedex_request(
                "/track/v1/trackingnumbers",
                {
                    "trackingInfo": [
                        {"trackingNumberInfo": {"trackingNumber": master_tracking}}
                    ],
                    "includeDetailedScans": True,
                },
            )
        except Exception as e:
            picking.pod_error = str(e)
            return

        track_results = (
            response.get("completeTrackResults", [{}])[0].get("trackResults", [])
        )
        if not track_results:
            picking.pod_error = "No tracking results returned by FedEx"
            return

        result = track_results[0]

        if result.get("error"):
            picking.pod_error = result["error"].get("message", "FedEx tracking error")
            return

        latest = result.get("latestStatusDetail", {})
        code = latest.get("code", "")
        status_label = latest.get("statusByLocale") or latest.get("description", "")

        vals = {
            "delivery_state": self._fedex_rest_map_delivery_state(code),
            "tracking_state": f"[{code}] {status_label}" if code else status_label,
            "tracking_state_history": self._fedex_rest_build_tracking_history(
                result.get("scanEvents", [])
            ),
            "tracking_json": result,
            "pod_error": False,
        }

        self._fedex_rest_extract_dates(result.get("dateAndTimes", []), vals)

        available_images = result.get("availableImages", [])
        if any(img.get("type") == "SIGNATURE_PROOF_OF_DELIVERY" for img in available_images):
            pod_data = self._fedex_rest_get_pod(srm, master_tracking)
            if pod_data:
                vals.update(
                    {
                        "pod_file": pod_data,
                        "pod_filename": f"fedex_pod_{master_tracking}.pdf",
                    }
                )

        picking.write(vals)

    def _fedex_rest_map_delivery_state(self, code):
        """Traduit un code scan FedEx en valeur delivery_state OCA."""
        return _FEDEX_STATE_MAP.get(code, "in_transit")

    def _fedex_rest_build_tracking_history(self, scan_events):
        """Construit l'historique de tracking (un événement par ligne)."""
        lines = []
        for event in scan_events:
            dt = event.get("date", "")
            event_type = event.get("eventType", "")
            description = event.get("eventDescription", "")
            location = event.get("scanLocation", {})
            city = location.get("city", "")
            country = location.get("countryCode", "")
            parts = [p for p in [city, country] if p]
            loc = f" — {', '.join(parts)}" if parts else ""
            lines.append(f"{dt} [{event_type}] {description}{loc}")
        return "\n".join(lines)

    def _fedex_rest_extract_dates(self, date_and_times, vals):
        """Remplit date_shipped et date_delivered depuis la réponse API."""
        for date_info in date_and_times:
            date_type = date_info.get("type", "")
            raw_dt = date_info.get("dateTime", "")
            if not raw_dt:
                continue
            if date_type == "ACTUAL_DELIVERY" and "date_delivered" not in vals:
                vals["date_delivered"] = self._fedex_rest_parse_dt(raw_dt)
            elif date_type == "ACTUAL_PICKUP" and "date_shipped" not in vals:
                parsed = self._fedex_rest_parse_dt(raw_dt)
                if parsed:
                    vals["date_shipped"] = parsed.date()

    def _fedex_rest_parse_dt(self, raw):
        """Parse une datetime ISO 8601 FedEx en datetime naïve (sans timezone)."""
        if not raw:
            return False
        try:
            return datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            _logger.warning("FedEx: impossible de parser la date '%s'", raw)
            return False

    def _fedex_rest_get_pod(self, srm, tracking_number):
        """Récupère l'image SPOD (Signature Proof of Delivery) auprès de FedEx.

        FedEx retourne le contenu en base64 dans la réponse de tracking
        quand documentType est spécifié. L'image est encodée dans le champ
        encodedLabel ou content selon la version de l'API.
        """
        try:
            response = srm._send_fedex_request(
                "/track/v1/trackingnumbers",
                {
                    "trackingInfo": [
                        {"trackingNumberInfo": {"trackingNumber": tracking_number}}
                    ],
                    "includeDetailedScans": False,
                    "accountNumber": {"value": srm.account_number},
                    "documentType": "SIGNATURE_PROOF_OF_DELIVERY",
                },
            )
            result = (
                response.get("completeTrackResults", [{}])[0]
                .get("trackResults", [{}])[0]
            )
            for img in result.get("availableImages", []):
                if img.get("type") == "SIGNATURE_PROOF_OF_DELIVERY":
                    return img.get("encodedLabel") or img.get("content")
        except Exception as e:
            _logger.warning("FedEx POD retrieval failed for %s: %s", tracking_number, e)
        return False
