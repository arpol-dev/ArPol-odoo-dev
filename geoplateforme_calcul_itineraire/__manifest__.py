# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    'name': "Géoplateforme - Calcul d'itinéraire",
    'version': '1.0',
    'summary': "Connecteur API IGN Géoplateforme - calcul d'itinéraire",
    'description': """
Connecteur Odoo v16 vers l'API de calcul d'itinéraire de la Géoplateforme IGN
(https://data.geopf.fr/navigation/).

Ce module est une brique de base : il n'agit sur aucun modèle métier et n'a
pas de vue utilisateur. Il expose un AbstractModel `geoplateforme.itineraire`
que d'autres modules peuvent consommer pour calculer des itinéraires.

Endpoints couverts :
  - GET /getCapabilities  (découverte de l'API)
  - GET/POST /itineraire  (calcul d'itinéraire)

Voir le README.md et le dossier doc/ pour le détail.
""",
    'author': 'Armand Polmard',
    'category': 'Tools',
    'license': 'AGPL-3',
    'depends': ['base'],
    'data': [],
    'external_dependencies': {
        'python': ['requests'],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
