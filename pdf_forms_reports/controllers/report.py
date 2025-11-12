# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
# -*- coding: utf-8 -*-

import json
from odoo import http
from odoo.http import request, content_disposition
from odoo.tools.safe_eval import safe_eval
import time


class PdfFormReportController(http.Controller):
    """
    Custom controller for PDF Form reports.
    Provides a direct route that calls _render() which dispatches to _render_pdf_form()
    """

    @http.route([
        '/report/pdf_form/<reportname>',
        '/report/pdf_form/<reportname>/<docids>',
    ], type='http', auth='user', website=True, readonly=True, methods=['GET', 'POST'])
    def report_pdf_form(self, reportname, docids=None, converter=None, **data):
        """
        Direct route for PDF Form reports.
        Calls _render() which will dispatch to _render_pdf_form() automatically.
        """
        report_sudo = request.env['ir.actions.report'].sudo()
        context = dict(request.env.context)

        if docids:
            docids = [int(i) for i in docids.split(',') if i.isdigit()]

        if data.get('options'):
            data.update(json.loads(data.pop('options')))

        if data.get('context'):
            data['context'] = json.loads(data['context'])
            context.update(data['context'])

        # Call _render() which will automatically dispatch to _render_pdf_form()
        import logging
        _logger = logging.getLogger(__name__)

        _logger.info(f"[PDF Form Controller] Rendering report: {reportname} for docids: {docids}")
        pdf_content = report_sudo.with_context(context)._render(reportname, docids, data=data)[0]
        _logger.info(f"[PDF Form Controller] PDF generated, size: {len(pdf_content)} bytes")

        # Set proper filename
        report = report_sudo._get_report_from_name(reportname)
        filename = f"{report.name}.pdf"

        if docids:
            obj = request.env[report.model].browse(docids)
            if report.print_report_name and not len(obj) > 1:
                report_name = safe_eval(report.print_report_name, {'object': obj, 'time': time})
                filename = f"{report_name}.pdf"

        _logger.info(f"[PDF Form Controller] Filename: {filename}")

        pdfhttpheaders = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf_content)),
            ('Content-Disposition', content_disposition(filename))
        ]

        _logger.info(f"[PDF Form Controller] Sending response with headers: {pdfhttpheaders}")

        return request.make_response(pdf_content, headers=pdfhttpheaders)
