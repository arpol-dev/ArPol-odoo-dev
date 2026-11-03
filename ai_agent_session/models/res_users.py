# -*- coding: utf-8 -*-
# Chaque utilisateur peut solliciter son propre agent : les accès au webhook (URL, token,
# répertoire de travail par défaut) vivent dans son profil, pas dans une config globale.
from odoo import _, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    claude_webhook_url = fields.Char(
        string="AI Agent Webhook URL",
        help="Base URL of the IArPol webhook server (e.g. https://hook.arpol.fr). "
             "Leave empty to disable AI Agent sessions for your account.",
    )
    claude_webhook_token = fields.Char(
        string="AI Agent Webhook Token",
        help="Token of the IArPol webhook, sent in the X-Webhook-Token header. "
             "Find it in ~/.config/iarpol/webhook.json on the IArPol server.",
    )
    claude_webhook_cwd = fields.Char(
        string="AI Agent Working Directory",
        help="Directory the agent opens when a session starts (must be inside the "
             "allowedRoots of the IArPol webhook configuration).",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            'claude_webhook_url', 'claude_webhook_token', 'claude_webhook_cwd',
        ]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + [
            'claude_webhook_url', 'claude_webhook_token', 'claude_webhook_cwd',
        ]

    def action_sync_ai_agent_models(self):
        """Copie la liste des modèles du serveur IArPol dans ai.agent.model."""
        self.ensure_one()
        launcher = self.env['ai.agent.launcher']
        data = launcher._ai_agent_webhook(self, 'GET', '/api/webhook/models')
        count = self.env['ai.agent.model'].sudo()._sync_from_server(data.get('models') or [])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("%s AI Agent models synchronized.", count),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
