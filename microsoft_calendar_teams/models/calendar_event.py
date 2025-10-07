# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models, _

class Meeting(models.Model):
    _inherit = 'calendar.event'

    videocall_source = fields.Selection(selection_add=[('teams', 'Microsoft Teams')])
    microsoft_is_calendar_sync_enabled = fields.Boolean(string="Is Outlook Calendar Sync configured and active ?", compute='_compute_microsoft_is_calendar_sync_enabled', default='_compute_microsoft_is_calendar_sync_enabled', store=False)

    @api.depends_context('uid')
    def _compute_microsoft_is_calendar_sync_enabled(self):
        if self.env.user._get_microsoft_sync_status() == "sync_active":
            self.microsoft_is_calendar_sync_enabled = True

    # Microsoft sync will force every meeting that has no location as a Teams meeting, we need to force the location for other types.   
    @api.onchange('location', 'videocall_source')
    def _onchange_location_videocall_source(self):
        if self.videocall_source != 'teams' and (not self.location or self.location == ""):
            self.location = "Online"
    
    @api.model
    def create(self, vals):
        event = super(Meeting, self).create(vals)
        if event.videocall_source != 'teams' and (not event.location or event.location == ""):
            event.location = "Online"
        return event

    def set_teams_videocall_location(self):
        self.ensure_one()
        self.location = False
        self.videocall_location = "Please close/reopen your event. MC Teams will overwrite this text with the meeting link."

    # Somehow, with only the previous method, web.base.url is added as prefix to the message. This next method corrects that behavior.
    @api.model
    def _set_videocall_location(self, vals_list):
        res = super(Meeting, self)._set_videocall_location(vals_list)
        for vals in vals_list:
            if vals.get('videocall_location') and 'MC Teams' in vals.get('videocall_location'):
                vals['videocall_location'] = "Please close/reopen your event. MC Teams will overwrite this text with the meeting link."

    @api.depends('videocall_location')
    def _compute_videocall_source(self):
        super(Meeting, self)._compute_videocall_source()
        for event in self:
            if event.videocall_location:
                if 'MC Teams' in event.videocall_location or 'teams.microsoft' in event.videocall_location:
                    event.videocall_source = 'teams'


