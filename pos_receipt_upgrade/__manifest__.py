# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Spécificités pour Casa Angels',
    'version': '1.0.1',
    'category': 'Hidden',
    'sequence': 40,
    'summary': '[ArPol] Module personnalisé pour Casa Angels',
    'depends': ['point_of_sale','l10n_fr_siret'],
    'assets': {
        'point_of_sale.assets': [
            'casaangels_custom/static/xml/OrderReceipt_inherit.xml',
        ],
    },
    'installable': True,
    'application': False,
}