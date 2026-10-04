# -*- coding: utf-8 -*-
# Chaque utilisateur peut solliciter son propre agent : les accès au webhook (URL, token,
# répertoire de travail par défaut) vivent dans son profil, pas dans une config globale.
from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    claude_webhook_url = fields.Char(
        string="AI Agent Webhook URL",
        help="Base URL of your personal Claude Code webhook server "
             "(e.g. https://iassistant.arpol.fr). Leave empty to disable AI Agent "
             "activities for your account.",
    )
    claude_webhook_token = fields.Char(
        string="AI Agent Webhook Token",
        help="Dedicated webhook token for your server (distinct from any personal "
             "app token). Find it in ~/.claude-console/config.json on your server.",
    )
    claude_webhook_cwd = fields.Char(
        string="AI Agent Working Directory",
        help="Directory the agent opens when a session starts (must be inside the "
             "directories allowed by your webhook server's configuration). The agent "
             "reads and writes files relative to this directory.",
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
