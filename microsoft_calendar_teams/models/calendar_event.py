# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models, _

class Meeting(models.Model):
    _inherit = 'calendar.event'

    videocall_source = fields.Selection(selection_add=[('teams', 'Microsoft Teams')], ondelete={'microsoft_teams': 'set null'})
    microsoft_is_calendar_sync_enabled = fields.Boolean(string="Is Outlook Calendar Sync configured and active ?", compute='_compute_microsoft_is_calendar_sync_enabled', store=False)

    def _compute_microsoft_is_calendar_sync_enabled(self):
        user = self.env.user        
        if user.microsoft_calendar_token and user.microsoft_calendar_token_validity and user.microsoft_calendar_token.validity > fields.Datetime.now() and not user.microsoft_synchronisation_stopped:
            self.microsoft_is_calendar_sync_enabled = True
        else:
            self.microsoft_is_calendar_sync_enabled = False

    def set_teams_videocall_location(self):
        self.videocall_source = 'teams'

    def clear_videocall_location(self):
        self.videocall_source = 'custom'
