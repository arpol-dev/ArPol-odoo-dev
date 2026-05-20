# mail_partner_unified_history/models/ir_model.py
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class IrModel(models.Model):
    _inherit = 'ir.model'

    partner_history_enabled = fields.Boolean(
        string="Show partner history",
        help="Adds a 'Partner History' tab in this model's chatter.",
        default=False,
    )

    @api.constrains('partner_history_enabled')
    def _check_partner_history_enabled(self):
        for record in self:
            if not record.partner_history_enabled:
                continue
            if record.model == 'res.partner':
                continue
            try:
                field = self.env[record.model]._fields.get('partner_id')
                if not field or getattr(field, 'comodel_name', None) != 'res.partner':
                    raise UserError(_(
                        "Partner history can only be enabled on the Contact model "
                        "or models with a 'partner_id' field linking to Contacts. "
                        "The model '%(model)s' does not qualify.",
                        model=record.name,
                    ))
            except KeyError:
                pass

    @api.model
    def get_partner_history_enabled_models(self):
        records = self.search([('partner_history_enabled', '=', True)])
        return records.mapped('model')
