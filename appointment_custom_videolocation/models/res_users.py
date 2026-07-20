from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    custom_videolink = fields.Char(string="Custom Video Link")

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['custom_videolink']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['custom_videolink']
