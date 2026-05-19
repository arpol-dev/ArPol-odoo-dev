# mail_partner_unified_history/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    'name': 'Mail - Partner Message History',
    'version': '18.0.1.0.0',
    'summary': 'Consolidated partner message history in chatter',
    'author': 'Armand Polmard',
    'category': 'Discuss',
    'depends': ['mail'],
    'data': [
        'views/ir_model_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mail_partner_unified_history/static/src/partner_history_service.js',
            'mail_partner_unified_history/static/src/chatter_patch.xml',
            'mail_partner_unified_history/static/src/chatter_patch.js',
            'mail_partner_unified_history/static/src/partner_history_list.xml',
            'mail_partner_unified_history/static/src/partner_history_list.js',
        ],
    },
    'license': 'AGPL-3',
    'installable': True,
    'application': False,
}
