# -*- coding: utf-8 -*-
# Type d'action serveur "Launch AI Agent session" : déclenche une session IArPol depuis une action
# serveur (bouton, menu Action, automatisation) avec la même mécanique que le bouton du chatter
# (voir ai.agent.launcher._ai_agent_launch).
from odoo import fields, models

from .ai_selections import (
    AI_AGENT_MODEL_HELP,
    AI_AGENT_PERMISSION_DEFAULT,
    AI_AGENT_PERMISSION_HELP,
    AI_AGENT_PERMISSION_SELECTION,
)


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    state = fields.Selection(
        selection_add=[('ai_agent', "Launch AI Agent Session")],
        ondelete={'ai_agent': 'cascade'},
    )
    ai_agent_user_id = fields.Many2one(
        'res.users', string="AI Agent Of", default=lambda self: self.env.user,
        help="User whose AI Agent webhook (Preferences > AI Agent) runs the session. Needed "
             "because automated actions run as OdooBot, which has no webhook.",
    )
    ai_agent_title = fields.Char(
        string="Session Title", help="Optional. Names the session; defaults to the first line of the request.",
    )
    ai_agent_request = fields.Text(
        string="Agent Request",
        help="Main task sent to the agent. It also receives the full data of the record the "
             "action runs on, and its chatter history.",
    )
    ai_agent_model_id = fields.Many2one(
        'ai.agent.model', string="AI Model", domain=[('active', '=', True)], help=AI_AGENT_MODEL_HELP,
    )
    ai_agent_permission = fields.Selection(
        AI_AGENT_PERMISSION_SELECTION, string="Permissions", default=AI_AGENT_PERMISSION_DEFAULT,
        help=AI_AGENT_PERMISSION_HELP,
    )

    def _run_action_ai_agent(self, eval_context=None):
        # Non-multi : appelé une fois par active_id, avec eval_context['record'] positionné.
        self.ensure_one()
        record = (eval_context or {}).get('record')
        if not record or not self.ai_agent_request:
            return False
        user = self.ai_agent_user_id
        model = self.ai_agent_model_id or user.sudo().ai_agent_default_model_id
        self.env['ai.agent.launcher']._ai_agent_launch(
            record, self.ai_agent_request, user=user,
            label=self.ai_agent_title, model=model.code,
            permission=self.ai_agent_permission,
        )
        return False
