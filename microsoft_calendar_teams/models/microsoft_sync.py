# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models, _

class MicrosoftSync(models.AbstractModel):
    _inherit = 'microsoft.calendar.sync'

    # Returns True only if the meeting location is left empty (with the placeholder "online meeting") and the videocall_source is 'teams'
    def _need_video_call(self):
        res = super()._need_video_call()
        if self.location:
            res = False
        return res