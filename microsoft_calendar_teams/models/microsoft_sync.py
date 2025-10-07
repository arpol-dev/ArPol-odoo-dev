# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models, _

class MicrosoftSync(models.AbstractModel):
    _inherit = 'microsoft.calendar.sync'

    def _need_video_call(self):
        res = super()._need_video_call()
        if self.videocall_source == 'teams':
            res = True
        return res