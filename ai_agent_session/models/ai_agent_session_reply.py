# -*- coding: utf-8 -*-
# Wizard ouvert depuis le menu systray pour répondre à une session en attente de réponse
# (la session reste vivante après une question, voir ai.agent.session._handle_callback).
from odoo import _, fields, models


class AiAgentSessionReply(models.TransientModel):
    _name = 'ai.agent.session.reply'
    _description = 'Answer an AI Agent session'

    session_id = fields.Many2one('ai.agent.session', string="Session", required=True, ondelete='cascade')
    question = fields.Text(related='session_id.conclusion', string="Question from the agent")
    answer = fields.Text(string="Your answer", required=True)

    def action_send(self):
        self.ensure_one()
        self.session_id.action_reply(self.answer)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("Answer sent. The agent resumes its work."),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
