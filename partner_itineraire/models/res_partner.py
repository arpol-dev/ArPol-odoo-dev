# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# État du calcul d'itinéraire. Le widget JS lit ce champ pour décider quoi
# afficher (carte, message d'erreur, invitation à géolocaliser, etc.).
ITINERAIRE_STATES = [
    ('todo', "Non calculé"),
    ('computed', "Calculé"),
    ('no_company_coords', "Société non géolocalisée"),
    ('no_partner_coords', "Contact non géolocalisé"),
    ('same_point', "Départ et arrivée identiques"),
    ('error', "Erreur de calcul"),
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    itineraire_state = fields.Selection(
        ITINERAIRE_STATES,
        string="État itinéraire",
        default='todo',
        readonly=True,
        copy=False,
    )
    itineraire_distance_km = fields.Float(
        string="Distance (km)",
        digits=(10, 2),
        readonly=True,
        copy=False,
    )
    itineraire_duration_min = fields.Float(
        string="Durée estimée (min)",
        digits=(10, 0),
        readonly=True,
        copy=False,
    )
    itineraire_geometry = fields.Text(
        string="Géométrie GeoJSON",
        readonly=True,
        copy=False,
    )
    itineraire_bbox = fields.Text(
        string="Bounding box JSON",
        readonly=True,
        copy=False,
    )
    itineraire_start_lat = fields.Float(
        string="Départ (latitude)",
        digits=(16, 8),
        readonly=True,
        copy=False,
    )
    itineraire_start_lon = fields.Float(
        string="Départ (longitude)",
        digits=(16, 8),
        readonly=True,
        copy=False,
    )
    itineraire_computed_date = fields.Datetime(
        string="Date du calcul",
        readonly=True,
        copy=False,
    )
    itineraire_error_message = fields.Char(
        string="Message d'erreur",
        readonly=True,
        copy=False,
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _has_valid_coords(partner):
        """Vrai si le partner a un couple (lat, lon) exploitable.

        partner_latitude/partner_longitude valent 0.0 par défaut tant
        que base_geolocalize n'a pas géolocalisé l'adresse — on traite
        donc (0, 0) comme "absent" (golfe de Guinée, peu probable).
        """
        if not partner:
            return False
        return bool(partner.partner_latitude) or bool(partner.partner_longitude)

    def _reset_itineraire(self, state, message=None):
        self.write({
            'itineraire_state': state,
            'itineraire_distance_km': 0.0,
            'itineraire_duration_min': 0.0,
            'itineraire_geometry': False,
            'itineraire_bbox': False,
            'itineraire_start_lat': 0.0,
            'itineraire_start_lon': 0.0,
            'itineraire_computed_date': False,
            'itineraire_error_message': message or False,
        })

    # ------------------------------------------------------------------
    # Action
    # ------------------------------------------------------------------

    def action_compute_itineraire(self):
        """Calcule l'itinéraire société -> partner et stocke le résultat.

        Déclenché par le bouton "Calculer l'itinéraire" dans l'onglet
        Itinéraire de la fiche contact.
        """
        self.ensure_one()
        company_partner = self.env.company.partner_id

        if not self._has_valid_coords(company_partner):
            self._reset_itineraire(
                'no_company_coords',
                _("L'adresse de la société « %s » n'est pas géolocalisée. "
                  "Ouvrez la fiche société et utilisez « Géolocaliser » "
                  "avant de calculer l'itinéraire.") % self.env.company.name,
            )
            return

        if not self._has_valid_coords(self):
            result = self._geo_localize(
                self.street or '',
                self.zip or '',
                self.city or '',
                self.state_id.name or '',
                self.country_id.name or '',
            )
            if not result:
                self._reset_itineraire(
                    'no_partner_coords',
                    _("Impossible de géolocaliser l'adresse de ce contact. "
                    "Vérifiez la et réessayez."),
                )
                return
            self.write({
                'partner_latitude': result[0],
                'partner_longitude': result[1],
                'date_localization': fields.Date.context_today(self),
            })
            
        start_lat = company_partner.partner_latitude
        start_lon = company_partner.partner_longitude
        end_lat = self.partner_latitude
        end_lon = self.partner_longitude

        if (round(start_lat, 6), round(start_lon, 6)) == \
                (round(end_lat, 6), round(end_lon, 6)):
            self._reset_itineraire(
                'same_point',
                _("Le contact se trouve à la même adresse que la société."),
            )
            return

        service = self.env['geoplateforme.itineraire']
        try:
            route = service.compute_route(
                start=(start_lon, start_lat),
                end=(end_lon, end_lat),
                profile='car',
                optimization='fastest',
                geometry_format='geojson',
                get_bbox=True,
                distance_unit='meter',
                time_unit='second',
            )
        except Exception as exc:
            _logger.exception(
                "Échec du calcul d'itinéraire pour le partner %s (id=%s)",
                self.display_name, self.id,
            )
            self._reset_itineraire('error', str(exc)[:255])
            return

        distance_m = float(route.get('distance') or 0.0)
        duration_s = float(route.get('duration') or 0.0)
        geometry = route.get('geometry')
        bbox = route.get('bbox')

        if not geometry:
            self._reset_itineraire(
                'error',
                _("La réponse de la Géoplateforme ne contient pas de géométrie."),
            )
            return

        self.write({
            'itineraire_state': 'computed',
            'itineraire_distance_km': round(distance_m / 1000.0, 2),
            'itineraire_duration_min': round(duration_s / 60.0, 1),
            'itineraire_geometry': json.dumps(geometry, separators=(',', ':')),
            'itineraire_bbox': json.dumps(bbox, separators=(',', ':')) if bbox else False,
            'itineraire_start_lat': start_lat,
            'itineraire_start_lon': start_lon,
            'itineraire_computed_date': fields.Datetime.now(),
            'itineraire_error_message': False,
        })

    def action_open_company_for_geolocalize(self):
        """Raccourci UI : ouvre la fiche société pour la géolocaliser."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id': self.env.company.partner_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
