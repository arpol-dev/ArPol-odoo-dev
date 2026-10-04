# -*- coding: utf-8 -*-
# Type d'action serveur "Launch AI Agent session" : permet de déclencher une session agent depuis
# une action serveur (bouton, menu Action, ou automatisation) avec la même mécanique que le bouton
# "AI Agent" du chatter (voir ai.agent.session._launch_for_record).
from odoo import fields, models

from .ai_selections import (
    AI_MODEL_DEFAULT,
    AI_MODEL_HELP,
    AI_MODEL_SELECTION,
    AI_PERMISSION_MODE_HELP,
    AI_PERMISSION_MODE_SELECTION,
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
    ai_agent_model = fields.Selection(
        AI_MODEL_SELECTION, string="AI Model", default=AI_MODEL_DEFAULT,
        help=AI_MODEL_HELP,
    )
    ai_agent_permission_mode = fields.Selection(
        AI_PERMISSION_MODE_SELECTION, string="Permission Mode", default='auto',
        help=AI_PERMISSION_MODE_HELP,
    )

    def _run_action_ai_agent(self, eval_context=None):
        # Non-multi : appelé une fois par active_id, avec eval_context['record'] positionné.
        self.ensure_one()
        record = (eval_context or {}).get('record')
        if not record or not self.ai_agent_request:
            return False
        self.env['ai.agent.session']._launch_for_record(
            record, self.ai_agent_request, user=self.ai_agent_user_id,
            label=self.ai_agent_title, ai_model=self.ai_agent_model,
            permission_mode=self.ai_agent_permission_mode,
        )
        return False
