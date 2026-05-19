# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models, _

class AppointmentType(models.Model):
    _inherit = "appointment.type"

    event_videocall_source = fields.Selection(
        selection_add=[('custom', 'Custom video provider')],
        ondelete={'custom': 'set default'}
    )
    custom_videocall_location = fields.Char(string="Custom Videocall Link", help="Custom video call link to be used when 'Custom video provider' is selected as video call source.")

class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    @api.depends('videocall_source', 'access_token')
    def _compute_videocall_location(self):
        super()._compute_videocall_location()
        for event in self:
            if event.videocall_source != 'custom':
                continue
            if event.appointment_type_id and event.appointment_type_id.custom_videocall_location:
                event.videocall_location = event.appointment_type_id.custom_videocall_location
            elif event.user_id and event.user_id.custom_videolink:
                event.videocall_location = event.user_id.custom_videolink

    @api.depends('videocall_location', 'access_token')
    def _compute_videocall_redirection(self):
        super()._compute_videocall_redirection()
        for event in self:
            if event.videocall_source == 'custom' and event.videocall_location:
                event.videocall_redirection = event.videocall_location