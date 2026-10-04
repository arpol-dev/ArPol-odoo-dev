# -*- coding: utf-8 -*-
# Session agent lancée depuis le chatter (wizard) ou une action serveur : porte l'état, le secret du
# callback, et alimente le menu systray de notifications (y compris les sessions terminées).
import logging
import secrets

import requests
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .ai_selections import AI_AGENT_DONE_MARKER

_logger = logging.getLogger(__name__)

AI_AGENT_SESSION_STATUS = [
    ('running', "Running"),
    ('needs_attention', "Needs your attention"),
    ('done', "Done"),
    ('cancelled', "Cancelled"),
    ('error', "Error"),
]


class AiAgentSession(models.Model):
    _name = 'ai.agent.session'
    _inherit = ['ai.agent.prompt.mixin']
    _description = 'AI Agent Session (notification tracking)'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(required=True)
    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    # Enregistrement d'origine : copies non-relationnelles, lisibles même si l'enregistrement
    # est supprimé ou inaccessible.
    res_model = fields.Char()
    res_id = fields.Integer()
    res_name = fields.Char()
    status = fields.Selection(AI_AGENT_SESSION_STATUS, default='running', required=True, index=True)
    session_name = fields.Char(string="Claude Session")
    remote_url = fields.Char(string="Remote Session URL")
    conclusion = fields.Text()
    is_dismissed = fields.Boolean(default=False, index=True)
    # Authentifie le callback du webhook (voir controllers/main.py).
    callback_secret = fields.Char(readonly=True, copy=False)

    def action_dismiss(self):
        self.write({'is_dismissed': True})

    def action_open_record(self):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'views': [(False, 'form')],
            'target': 'current',
        }

    @api.model
    def get_systray_data(self):
        """Renvoie le compteur (attente + terminées/erreur non masquées, PAS les sessions en
        cours — elles ne réclament rien de l'utilisateur pour l'instant) et la liste affichée
        dans le menu (elle, inclut aussi les sessions en cours)."""
        sessions = self.search([
            ('user_id', '=', self.env.uid),
            ('is_dismissed', '=', False),
        ], limit=50)
        counter = len(sessions.filtered(lambda s: s.status in ('needs_attention', 'done', 'error')))
        return {
            'counter': counter,
            'sessions': [{
                'id': s.id,
                'name': s.name,
                'status': s.status,
                'res_model': s.res_model,
                'res_id': s.res_id,
                'res_name': s.res_name,
                'remote_url': s.remote_url,
                'conclusion': s.conclusion,
            } for s in sessions],
        }

    def _notify_systray(self):
        """Signale au(x) navigateur(s) ouvert(s) de l'utilisateur qu'il faut rafraîchir le menu
        (voir static/src/ai_agent_menu.js) — évite d'attendre un rechargement de page."""
        for user in self.user_id:
            self.env['bus.bus']._sendone(user.partner_id, 'mail_activity_ai_agent/session_update', {})

    def _kill_remote_session(self):
        self.ensure_one()
        user = self.user_id
        if not self.session_name or not user.claude_webhook_url:
            return
        try:
            requests.delete(
                f'{user.claude_webhook_url.rstrip("/")}/api/webhook/sessions/{self.session_name}',
                headers={'X-Webhook-Token': user.claude_webhook_token},
                timeout=15,
            )
        except requests.RequestException as exc:
            _logger.warning("AI Agent: could not kill session %s: %s", self.session_name, exc)

    # -- Lancement ------------------------------------------------------------

    @api.model
    def _launch_for_record(self, record, request_text, user=None, label=None,
                           ai_model=None, permission_mode=None):
        """Crée une session et appelle le webhook de `user` (par défaut l'utilisateur courant),
        sans passer par une activité. Utilisé par le wizard du chatter et par l'action serveur
        "AI Agent" (où l'utilisateur courant peut être OdooBot, d'où le paramètre `user`). Tout
        échec (webhook non configuré, injoignable) lève une UserError : la transaction est
        annulée, aucune trace orpheline n'est laissée."""
        user = (user or self.env.user).sudo()
        if not user.claude_webhook_url or not user.claude_webhook_token:
            raise UserError(_(
                "%(user)s has no AI Agent webhook configured (Preferences > AI Agent).",
                user=user.display_name,
            ))
        record.with_user(user).check_access('read')

        session = self.sudo().create({
            'name': (label or request_text.strip().splitlines()[0])[:80],
            'user_id': user.id,
            'res_model': record._name,
            'res_id': record.id,
            'res_name': record.display_name,
            'callback_secret': secrets.token_urlsafe(24),
        })
        session._launch(record, request_text, ai_model, permission_mode)
        return session

    def _launch(self, record, request_text, ai_model, permission_mode):
        self.ensure_one()
        user = self.user_id
        payload = {
            'cwd': user.claude_webhook_cwd or '',
            'prompt': self._build_prompt(record, request_text),
            'model': ai_model or None,
            'permissionMode': permission_mode or None,
            'label': self.name,
            'idempotencyKey': f'odoo-ai-session-{self.id}',
            'callbackUrl': self._callback_url(),
        }
        try:
            response = requests.post(
                f'{user.claude_webhook_url.rstrip("/")}/api/webhook/sessions',
                json=payload,
                headers={'X-Webhook-Token': user.claude_webhook_token},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            _logger.warning("AI Agent webhook call failed for session %s: %s", self.id, exc)
            raise UserError(_("Could not reach the AI Agent webhook: %s", exc)) from exc
        self.write({
            'session_name': data.get('name'),
            'remote_url': data.get('remoteControlUrl'),
        })
        self._notify_systray()

    def _callback_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f'{base_url}/claude_agent/callback?session_id={self.id}&secret={self.callback_secret}'

    def _build_prompt(self, record, request_text):
        self.ensure_one()
        sections = [
            self._ai_agent_prompt_boundaries(),
            self._ai_agent_prompt_context(record),
            self._ai_agent_prompt_process_instructions(),
            self._ai_agent_prompt_record_json(record),
            self._ai_agent_prompt_chatter_history(record),
            "# User request (your main task)\n" + request_text.strip(),
        ]
        return '\n\n'.join(section for section in sections if section)

    # -- Callback d'une session lancée depuis le chatter ---------------------

    def _handle_callback(self, status, conclusion=None):
        """Traite un callback du webhook : la conclusion est postée en note interne sur l'enregistrement
        d'origine (log complet en pièce jointe). Même sémantique de signaux : task_done/needs_input
        explicites en priorité, idle/ended en filet de sécurité."""
        self.ensure_one()
        if self.status != 'running' or status not in ('idle', 'ended', 'task_done', 'needs_input'):
            return  # déjà finalisée (callback dédoublonné) ou signal ignoré
        # Le contrôleur tourne en public : OdooBot pour que le message soit attribué proprement.
        self = self.with_user(self.env.ref('base.user_root')).sudo()
        if status in ('idle', 'ended') and not (conclusion or '').strip():
            conclusion = self._fetch('last-message').get('text') or ''
            is_done = status == 'ended' or AI_AGENT_DONE_MARKER in conclusion
        else:
            is_done = status in ('task_done', 'ended')
        text = (conclusion or '').replace(AI_AGENT_DONE_MARKER, '').strip() or _("Session ended.")

        # Session à tour unique : dans tous les cas on la termine côté serveur après le callback.
        self._kill_remote_session()
        attachment_ids = self._attach_transcript() if is_done else []
        self.write({'status': 'done' if is_done else 'needs_attention', 'conclusion': text})
        self._notify_systray()
        self._post_conclusion(text, is_done, attachment_ids)

    def _fetch(self, endpoint):
        user = self.user_id
        if not self.session_name or not user.claude_webhook_url:
            return {}
        try:
            response = requests.get(
                f'{user.claude_webhook_url.rstrip("/")}/api/webhook/sessions/{self.session_name}/{endpoint}',
                headers={'X-Webhook-Token': user.claude_webhook_token},
                timeout=15,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            _logger.warning("AI Agent: could not fetch %s for session %s: %s", endpoint, self.session_name, exc)
            return {}

    def _attach_transcript(self):
        self.ensure_one()
        transcript = self._fetch('transcript').get('text') or ''
        if not transcript or not self.res_model or not self.res_id:
            return []
        return self.env['ir.attachment'].create({
            'name': 'session_log.txt',
            'res_model': self.res_model,
            'res_id': self.res_id,
            'raw': transcript.encode(),
            'mimetype': 'text/plain',
        }).ids

    def _post_conclusion(self, text, is_done, attachment_ids):
        self.ensure_one()
        if not self.res_model or not self.res_id:
            return
        record = self.env[self.res_model].browse(self.res_id)
        if not record.exists() or not hasattr(record, 'message_post'):
            return
        intro = (_("The AI Agent finished session <b>%s</b>:") if is_done
                 else _("The AI Agent stopped on session <b>%s</b>, waiting for your input:"))
        record.message_post(
            body=Markup("<p>🤖 %s</p><p>%s</p>") % (Markup(intro) % self.name, text),
            subtype_xmlid='mail.mt_note',
            attachment_ids=attachment_ids,
        )
