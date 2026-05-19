from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    custom_videolink = fields.Char(string="Custom Video Link")
