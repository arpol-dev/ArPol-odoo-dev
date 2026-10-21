# -*- coding: utf-8 -*-
# Conversation Discuss d'une session agent : ce que l'utilisateur y écrit est transmis à l'agent.
from odoo import fields, models
from odoo.tools import html2plaintext


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    ai_agent_session_ids = fields.One2many('ai.agent.session', 'channel_id', string="AI Agent Session")

    def _message_post_after_hook(self, message, msg_vals):
        result = super()._message_post_after_hook(message, msg_vals)
        # Le drapeau évite de renvoyer à l'agent un message qu'Odoo a lui-même recopié ici
        # (réponse donnée par l'assistant du systray).
        if self.env.context.get('ai_agent_no_forward') or message.message_type != 'comment':
            return result
        session = self.sudo().ai_agent_session_ids[:1]
        if session and message.author_id == session.user_id.partner_id:
            session._forward_chat_message(html2plaintext(message.body or '').strip())
        return result
