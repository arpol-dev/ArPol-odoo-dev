# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_invoice_legal_documents(self, filetype, allow_fallback=False):
        # Flux 1 — backend "Download > PDF": render a real invoice instead of proforma
        # for posted invoices that have no stored PDF yet (same engine as the Print button).
        if filetype == 'pdf' and allow_fallback and not self.invoice_pdf_report_id and self.state == 'posted':
            report = self.env['account.move.send']._get_default_pdf_report_id(self)
            content, report_type = self.env['ir.actions.report']._pre_render_qweb_pdf(report.report_name, self.ids)
            content_by_id = self.env['ir.actions.report']._get_splitted_report(report.report_name, content, report_type)
            return {
                'filename': self._get_invoice_report_filename(),
                'filetype': 'pdf',
                'content': content_by_id[self.id],
            }
        return super()._get_invoice_legal_documents(filetype, allow_fallback=allow_fallback)

    def _get_invoice_legal_documents_all(self, allow_fallback=False):
        # Flux 3 — portal "Download": same fix as above.
        if allow_fallback and not self.invoice_pdf_report_id and self.state == 'posted':
            report = self.env['account.move.send']._get_default_pdf_report_id(self)
            content, report_type = self.env['ir.actions.report']._pre_render_qweb_pdf(report.report_name, self.ids)
            content_by_id = self.env['ir.actions.report']._get_splitted_report(report.report_name, content, report_type)
            return [{
                'filename': self._get_invoice_report_filename(),
                'filetype': 'pdf',
                'content': content_by_id[self.id],
            }]
        return super()._get_invoice_legal_documents_all(allow_fallback=allow_fallback)
