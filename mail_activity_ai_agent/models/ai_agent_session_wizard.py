# -*- coding: utf-8 -*-
# Wizard ouvert par le bouton "AI Agent" du chatter : lance une session agent. Mêmes options
# (modèle, mode de permissions) que l'action serveur "AI Agent".
from odoo import _, fields, models

from .ai_selections import (
    AI_MODEL_DEFAULT,
    AI_MODEL_HELP,
    AI_MODEL_SELECTION,
    AI_PERMISSION_MODE_HELP,
    AI_PERMISSION_MODE_SELECTION,
)


class AiAgentSessionWizard(models.TransientModel):
    _name = 'ai.agent.session.wizard'
    _description = 'Launch an AI Agent session from the chatter'

    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    summary = fields.Char(
        string="Title", help="Optional. Names the session in Claude Code and in the notifications menu.",
    )
    request = fields.Text(string="Request", required=True)
    ai_model = fields.Selection(
        AI_MODEL_SELECTION, string="AI Model", default=AI_MODEL_DEFAULT,
        help=AI_MODEL_HELP,
    )
    ai_permission_mode = fields.Selection(
        AI_PERMISSION_MODE_SELECTION, string="Permission Mode", default='auto',
        help=AI_PERMISSION_MODE_HELP,
    )

    def action_launch(self):
        self.ensure_one()
        self.env['ai.agent.session']._launch_for_record(
            self.env[self.res_model].browse(self.res_id), self.request,
            label=self.summary, ai_model=self.ai_model, permission_mode=self.ai_permission_mode,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("AI Agent session started. You will be notified here when it finishes."),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
