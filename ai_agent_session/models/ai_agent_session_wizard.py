# -*- coding: utf-8 -*-
# Wizard ouvert par le bouton "AI Agent" du chatter : lance une session sur IArPol. Mêmes options
# (modèle, permission) que l'action serveur "AI Agent".
from odoo import _, fields, models

from .ai_selections import (
    AI_AGENT_MODEL_HELP,
    AI_AGENT_PERMISSION_DEFAULT,
    AI_AGENT_PERMISSION_HELP,
    AI_AGENT_PERMISSION_SELECTION,
)


class AiAgentSessionWizard(models.TransientModel):
    _name = 'ai.agent.session.wizard'
    _description = 'Launch an AI Agent session from the chatter'

    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    summary = fields.Char(
        string="Title", help="Optional. Names the session in IArPol and in the chatter note.",
    )
    request = fields.Text(string="Request", required=True)
    ai_model_id = fields.Many2one(
        'ai.agent.model', string="AI Model", domain=[('active', '=', True)], help=AI_AGENT_MODEL_HELP,
    )
    ai_permission = fields.Selection(
        AI_AGENT_PERMISSION_SELECTION, string="Permissions", default=AI_AGENT_PERMISSION_DEFAULT,
        required=True, help=AI_AGENT_PERMISSION_HELP,
    )

    def action_launch(self):
        self.ensure_one()
        self.env['ai.agent.launcher']._ai_agent_launch(
            self.env[self.res_model].browse(self.res_id), self.request,
            label=self.summary, model=self.ai_model_id.code, permission=self.ai_permission,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("AI Agent session started. Its reference is in the chatter."),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
