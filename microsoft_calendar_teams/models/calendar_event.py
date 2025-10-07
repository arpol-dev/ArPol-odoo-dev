# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models, _

class Meeting(models.Model):
    _inherit = 'calendar.event'

    videocall_source = fields.Selection(selection_add=[('teams', 'Microsoft Teams')], ondelete={'microsoft_teams': 'set null'})
    
    def set_teams_videocall_location(self):
        self.videocall_source = 'teams'

    def clear_videocall_location(self):
        self.videocall_source = 'custom'
