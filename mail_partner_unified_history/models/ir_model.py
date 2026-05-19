# mail_partner_unified_history/models/ir_model.py
from odoo import api, fields, models


class IrModel(models.Model):
    _inherit = 'ir.model'

    partner_history_enabled = fields.Boolean(
        string="Show partner history",
        help="Adds a 'Partner History' tab in this model's chatter.",
        default=False,
    )

    @api.model
    def get_partner_history_enabled_models(self):
        records = self.search([('partner_history_enabled', '=', True)])
        return records.mapped('model')
