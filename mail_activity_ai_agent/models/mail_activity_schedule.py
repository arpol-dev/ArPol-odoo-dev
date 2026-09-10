# -*- coding: utf-8 -*-
# Le bouton "Activities" du chatter ouvre ce wizard (mail.activity.schedule), pas directement
# mail.activity — voir models/mail_activity_type.py pour le pourquoi. Préremplis depuis le type
# choisi mais librement modifiables (compute + readonly=False, comme summary/note dans le core) :
# l'utilisateur peut ajuster modèle/permission pour CETTE activité sans toucher au type.
from odoo import api, fields, models

from .ai_selections import (
    AI_MODEL_HELP,
    AI_MODEL_SELECTION,
    AI_PERMISSION_MODE_HELP,
    AI_PERMISSION_MODE_SELECTION,
)


class MailActivitySchedule(models.TransientModel):
    _inherit = 'mail.activity.schedule'

    ai_model = fields.Selection(
        AI_MODEL_SELECTION, string="AI Model", compute='_compute_ai_model',
        store=True, readonly=False, help=AI_MODEL_HELP,
    )
    ai_permission_mode = fields.Selection(
        AI_PERMISSION_MODE_SELECTION, string="Permission Mode", compute='_compute_ai_permission_mode',
        store=True, readonly=False, help=AI_PERMISSION_MODE_HELP,
    )

    @api.depends('activity_type_id')
    def _compute_ai_model(self):
        for scheduler in self:
            if scheduler.activity_type_id.ai_model:
                scheduler.ai_model = scheduler.activity_type_id.ai_model

    @api.depends('activity_type_id')
    def _compute_ai_permission_mode(self):
        for scheduler in self:
            if scheduler.activity_type_id.ai_permission_mode:
                scheduler.ai_permission_mode = scheduler.activity_type_id.ai_permission_mode

    def _action_schedule_activities(self):
        return self._get_applied_on_records().activity_schedule(
            activity_type_id=self.activity_type_id.id,
            automated=False,
            summary=self.summary,
            note=self.note,
            user_id=self.activity_user_id.id,
            date_deadline=self.date_deadline,
            ai_model=self.ai_model,
            ai_permission_mode=self.ai_permission_mode,
        )
