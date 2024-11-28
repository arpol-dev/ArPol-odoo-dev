from odoo import _, models

class ResUsers(models.Model):
    _inherit="res.users"

    def _signup_create_user(self, values):
        if values['email']:
            partner = self.env["res.partner"].sudo().search([('email','=',values['email'])], limit=1)
        if partner and not values['partner_id']:
            values['partner_id'] = partner.id
        return super(ResUsers, self)._signup_create_user(values)
