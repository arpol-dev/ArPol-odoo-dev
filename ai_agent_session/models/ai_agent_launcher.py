# -*- coding: utf-8 -*-
# Lancement d'une session sur le serveur IArPol : appel du webhook, puis note interne sur
# l'enregistrement pour garder l'historique. Pas de suivi ensuite : la session vit dans IArPol.
import logging
import uuid

import requests
from markupsafe import Markup

from odoo import _, api, models
from odoo.exceptions import UserError

from .ai_selections import AI_AGENT_PERMISSION_DEFAULT, AI_AGENT_PERMISSION_SELECTION

_logger = logging.getLogger(__name__)
WEBHOOK_TIMEOUT = 15


class AiAgentLauncher(models.AbstractModel):
    _name = 'ai.agent.launcher'
    _inherit = ['ai.agent.prompt.mixin']
    _description = 'AI Agent Launcher'

    @api.model
    def _ai_agent_webhook(self, user, method, path, payload=None):
        """Appel du webhook IArPol de `user`. Lève UserError si non configuré ou injoignable."""
        user = user.sudo()
        if not user.claude_webhook_url or not user.claude_webhook_token:
            raise UserError(_(
                "%(user)s has no AI Agent webhook configured (Preferences > AI Agent).",
                user=user.display_name,
            ))
        try:
            response = requests.request(
                method,
                f'{user.claude_webhook_url.rstrip("/")}{path}',
                json=payload,
                headers={'X-Webhook-Token': user.claude_webhook_token},
                timeout=WEBHOOK_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            _logger.warning("AI Agent webhook call failed (%s %s): %s", method, path, exc)
            raise UserError(_("Could not reach the AI Agent webhook: %s", exc)) from exc

    @api.model
    def _ai_agent_launch(self, record, request_text, user=None, label=None, model=None, permission=None):
        """Crée la session sur IArPol pour `record`, puis note le lancement dans son chatter.
        `model` est un code `provider/model` (ou vide pour le défaut du serveur)."""
        user = (user or self.env.user).sudo()
        if not user.claude_webhook_cwd:
            raise UserError(_("Set an AI Agent working directory in your preferences first."))
        record.with_user(user).check_access('read')
        title = (label or request_text.strip().splitlines()[0])[:80]
        permission = permission or AI_AGENT_PERMISSION_DEFAULT
        data = self._ai_agent_webhook(user, 'POST', '/api/webhook/sessions', {
            'cwd': user.claude_webhook_cwd,
            'prompt': self._ai_agent_build_prompt(record, request_text),
            'label': title,
            'model': model or None,
            'permission': permission,
            'idempotencyKey': f'odoo-ai-agent-{uuid.uuid4()}',
        })
        self._ai_agent_post_note(record, data, title, request_text, model, permission)
        return data

    def _ai_agent_build_prompt(self, record, request_text):
        sections = [
            self._ai_agent_prompt_boundaries(),
            self._ai_agent_prompt_context(record),
            self._ai_agent_prompt_process_instructions(),
            self._ai_agent_prompt_record_json(record),
            self._ai_agent_prompt_chatter_history(record),
            "# User request (your main task)\n" + request_text.strip(),
        ]
        return '\n\n'.join(section for section in sections if section)

    def _ai_agent_post_note(self, record, data, title, request_text, model, permission):
        """Note interne : identifiant de session, modèle, permission et demande, pour l'historique."""
        if not hasattr(record, 'message_post'):
            return
        permission_label = dict(AI_AGENT_PERMISSION_SELECTION).get(permission, permission)
        model_label = model or _("server default")
        body = Markup("<p>🤖 %s</p><ul><li>%s <code>%s</code></li><li>%s %s</li><li>%s %s</li></ul>"
                      "<p>%s</p><blockquote>%s</blockquote>") % (
            _("AI Agent session launched: %s", title),
            _("Session:"), data.get('name', ''),
            _("Model:"), model_label,
            _("Permissions:"), permission_label,
            _("Request:"), request_text.strip(),
        )
        if data.get('openUrl'):
            body += Markup('<p><a href="%s">%s</a></p>') % (data['openUrl'], _("Open the session"))
        record.message_post(body=body, subtype_xmlid='mail.mt_note')
