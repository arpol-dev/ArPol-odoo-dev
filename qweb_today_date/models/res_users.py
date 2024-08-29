# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models, api, _
from datetime import datetime
import babel

import logging

class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def get_formatted_today_date(self):
        lang = self.env.user.lang or 'en_US'
        date = datetime.now()

        formatted_date = babel.dates.format_date(date, format='dd MMMM yyyy', locale=lang)
        return formatted_date