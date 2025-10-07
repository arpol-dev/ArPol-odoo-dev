# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models, _

class Meeting(models.Model):
    _inherit = 'calendar.event'

    videocall_source = fields.Selection(selection_add=[('teams', 'Microsoft Teams')], ondelete={'microsoft_teams': 'set null'})
    microsoft_is_calendar_sync_enabled = fields.Boolean(string="Is Outlook Calendar Sync configured and active ?", compute='_compute_microsoft_is_calendar_sync_enabled', default='_compute_microsoft_is_calendar_sync_enabled', store=False)

    @api.depends_context('uid')
    def _compute_microsoft_is_calendar_sync_enabled(self):
        user = self.env.user        
        if user.microsoft_calendar_token and user.microsoft_calendar_token_validity and user.microsoft_calendar_token_validity > fields.Datetime.now() and not user.microsoft_synchronization_stopped:
            self.microsoft_is_calendar_sync_enabled = True
        else:
            self.microsoft_is_calendar_sync_enabled = False

    def set_teams_videocall_location(self):
        self.ensure_one()
        self.videocall_source = 'teams'

    @api.model
    def _set_videocall_location(self, vals_list):
        res = super(Meeting, self)._set_videocall_location(vals_list)
        for vals in vals_list:
            if vals.get('videocall_source') and vals.get('videocall_source') == 'teams':
                vals['videocall_location'] = "Please refresh your page. Teams will overwrite this text with the meeting link."

    def clear_videocall_location(self):
        self.videocall_source = 'custom'
