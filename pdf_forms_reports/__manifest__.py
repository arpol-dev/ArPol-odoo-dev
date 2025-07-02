# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
# -*- coding: utf-8 -*-

{
    'name': 'PDF Forms Reports',
    'version': '1.0',
    'summary': 'Génération de rapports PDF basés sur des formulaires PDF',
    'author': 'Armand Polmard',
    'category': 'Reporting',
    'depends': ['web'],
    'data': [
        "security/ir.model.access.csv",
        'views/ir_actions_report_views.xml',
    ],
    "assets": {
        "web.assets_backend": [
            "pdf_forms_reports/static/src/js/service.js",
            "pdf_forms_reports/static/src/js/action_service.js",
        ],
    },
    'installable': True,
    'application': False,
    'external_dependencies': {
        'python': ['fitz', 'io', 'base64', 're', 'datetime', 'num2words'],
    },
}