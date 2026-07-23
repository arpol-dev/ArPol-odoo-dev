# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _get_rendering_context(self, report, docids, data):
        data = super()._get_rendering_context(report, docids, data)
        # Flux 2 — portal HTML preview (iframe): the portal controller sets
        # proforma_invoice=True for posted invoices without a stored PDF.
        # Strip the resulting flag since a posted invoice is legally binding.
        # All callers using this context key call ensure_one() first.
        if self.env.context.get('proforma_invoice') and report.model == 'account.move':
            invoices = self.env['account.move'].browse(docids or [])
            if invoices and all(inv.state != 'draft' for inv in invoices):
                data.pop('proforma', None)
        return data
