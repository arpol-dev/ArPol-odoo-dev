# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
# -*- coding: utf-8 -*-

{
    'name': 'PDF Forms Reports',
    'version': '1.2',
    'summary': 'Génération de rapports PDF basés sur des formulaires PDF',
    'description': """
PDF Forms Reports
=================

This module allows you to generate PDF reports using fillable PDF forms as templates.

Features:
---------
* Upload a PDF form with fillable fields as a report template
* Automatically detect form fields in the PDF
* Map PDF form fields to Odoo record fields
* Support for different evaluation types:
  - Direct values
  - Field references from records
  - Python expressions
  - File/image insertion
* Support for both form fields and manual text/image placement
* Optional signature insertion

Usage:
------
1. Create a new report with type 'PDF Form'
2. Upload your PDF form template
3. Configure field mappings in the 'Form Fields Mapping' tab
4. Use the report like any other Odoo report

Technical Details:
------------------
* Uses PyMuPDF (fitz) library for PDF manipulation
* Integrates seamlessly with Odoo's report system
* Supports multiple records (generates merged PDF)
    """,
    'author': 'Armand Polmard',
    'license': 'AGPL-3',
    'category': 'Reporting',
    'depends': ['web'],
    'data': [
        'security/ir.model.access.csv',
        'views/ir_actions_report_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pdf_forms_reports/static/src/js/pdf_form_handler.js',
        ],
    },
    'installable': True,
    'application': False,
    'external_dependencies': {
        'python': ['fitz'],  # PyMuPDF
    },
}
