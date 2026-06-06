# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    'name': "Frais kilométriques sur les ventes",
    'version': '1.0',
    'summary': "Gestion des frais de déplacement pour les ventes",
    'description': """
Ajoute un bouton sur la vue formulaire de sale.order pour permettre d'ajouter des frais kilométriques.

Dépend de :
  - partner_itineraire : pour calculer la distance entre l'entreprise et le client
""",
    'author': 'Armand Polmard',
    'category': 'Sales',
    'license': 'AGPL-3',
    'depends': [
        'sale',
        'partner_itineraire',
    ],
    'data': [
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
