# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Amélioration du modèle de reçu du point de vente',
    'summary': '[ArPol] Module personnalisé pour Casa Angels',
    'version': '16.0.1',
    'category': 'Sales/Point Of Sale',    
    'depends': ['point_of_sale','l10n_fr_siret'],
    'assets': {
        'point_of_sale.assets': [
            'pos_receipt_upgrade/static/xml/OrderReceipt_inherit.xml',
        ],
    },
}