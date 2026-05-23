# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    'name': "Partner Itinéraire",
    'version': '1.0',
    'summary': "Affiche sur la fiche contact l'itinéraire depuis la société courante",
    'description': """
Ajoute un onglet "Itinéraire" sur la vue formulaire de res.partner.

L'itinéraire est calculé via l'API IGN Géoplateforme entre l'adresse
géolocalisée de la société courante et celle du contact ouvert.
La carte est rendue avec Leaflet + tuiles IGN WMTS.

Dépend de :
  - base_geolocalize (fournit partner_latitude / partner_longitude
    et l'action de géolocalisation)
  - geoplateforme_calcul_itineraire (connecteur API itinéraire)
""",
    'author': 'Armand Polmard',
    'category': 'Contacts',
    'license': 'AGPL-3',
    'depends': [
        'base_geolocalize',
        'geoplateforme_calcul_itineraire',
    ],
    'data': [
        'views/res_partner_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'partner_itineraire/static/lib/leaflet/leaflet.css',
            'partner_itineraire/static/lib/leaflet/leaflet.js',
            'partner_itineraire/static/src/partner_itineraire_widget/partner_itineraire_widget.scss',
            'partner_itineraire/static/src/partner_itineraire_widget/partner_itineraire_widget.js',
            'partner_itineraire/static/src/partner_itineraire_widget/partner_itineraire_widget.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
