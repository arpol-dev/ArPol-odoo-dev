# -*- coding: utf-8 -*-
# Session agent lancée depuis le chatter (wizard) ou une action serveur : porte l'état, le secret du
# callback, et alimente le menu systray de notifications (y compris les sessions terminées).
import logging
import secrets

import requests
from markupsafe import Markup

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import plaintext2html

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
    # Conversation Discuss où l'agent pose ses questions et reçoit les réponses.
    channel_id = fields.Many2one('discuss.channel', string="Chat", index=True, ondelete='set null', copy=False)

    def action_dismiss(self):
        # Une session en attente est toujours vivante côté serveur : la masquer sans l'arrêter la
        # laisserait tourner indéfiniment sans que plus personne ne la suive.
        for session in self.sudo().filtered(lambda s: s.status == 'needs_attention'):
            session._kill_remote_session()
            session.write({'status': 'cancelled'})
        self.write({'is_dismissed': True})

    def action_open_chat(self):
        self.ensure_one()
        if not self.channel_id:
            return False
        active_id = f'discuss.channel_{self.channel_id.id}'
        return {
            'type': 'ir.actions.client',
            'tag': 'mail.action_discuss',
            'context': {'active_id': active_id},
            'params': {'active_id': active_id},
        }

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
        user = self.env.user.sudo()
        base_url = (user.claude_webhook_url or '').rstrip('/')
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
                # Page de la session dans IAssistant (même serveur que le webhook) : seule cible
                # exploitable, l'URL Remote Control de claude.ai n'existe pas avec `--bg`.
                'session_url': (f'{base_url}/s/{s.session_name}'
                                if base_url and s.session_name and s.status in ('running', 'needs_attention')
                                else False),
                'conclusion': s.conclusion,
                'channel_id': s.channel_id.id,
            } for s in sessions],
        }

    def _notify_systray(self):
        """Signale au(x) navigateur(s) ouvert(s) de l'utilisateur qu'il faut rafraîchir le menu
        (voir static/src/ai_agent_menu.js) — évite d'attendre un rechargement de page."""
        for user in self.user_id:
            self.env['bus.bus']._sendone(user.partner_id, 'ai_agent_session/session_update', {})

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
        session._create_channel(record, request_text)
        session._launch(record, request_text, ai_model, permission_mode)
        return session

    # -- Conversation Discuss -------------------------------------------------

    def _create_channel(self, record, request_text):
        """Ouvre le chat privé (utilisateur + interlocuteur « Claude ») dans lequel l'agent posera
        ses questions ; ce que l'utilisateur y écrit lui est transmis (voir _forward_chat_message)."""
        self.ensure_one()
        bot = self._ai_agent_partner()
        self.channel_id = self.env['discuss.channel'].sudo().create({
            'name': f'🤖 {self.name}',
            'channel_type': 'group',
            'channel_member_ids': [
                Command.create({'partner_id': self.user_id.partner_id.id}),
                Command.create({'partner_id': bot.id}),
            ],
        })
        self._post_in_channel(Markup("%s<br/>%s") % (
            _("Session started on %s.", record.display_name),
            _("I'll ask my questions here — just answer in this conversation."),
        ))

    def _ai_agent_partner(self):
        return self.env.ref('ai_agent_session.partner_claude').sudo()

    def _post_in_channel(self, body):
        """Poste `body` (HTML) dans le chat de la session, au nom de l'agent."""
        self.ensure_one()
        if not self.channel_id:
            return
        self.channel_id.sudo().with_context(ai_agent_no_forward=True).message_post(
            body=body,
            author_id=self._ai_agent_partner().id,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

    def _forward_chat_message(self, text):
        """Message écrit par l'utilisateur dans le chat : répond à la question en attente, ou
        s'ajoute à la session en cours. Un échec est signalé dans le chat par l'agent plutôt que
        levé (le message de l'utilisateur doit rester posté)."""
        self.ensure_one()
        if not text:
            return
        session = self.sudo()
        try:
            # Savepoint : un échec ne doit pas laisser la session 'En cours' sans que l'agent ait reçu la réponse.
            with self.env.cr.savepoint():
                if session.status == 'needs_attention':
                    delivered = session.action_reply(text, echo=False)
                elif session.status == 'running':
                    delivered = session._send_to_agent(text)
                else:
                    session._post_in_channel(Markup("<p>%s</p>") % _(
                        "This session is over. Start a new one from the record's chatter."))
                    return
        except UserError as exc:
            session._post_in_channel(Markup("<p>%s</p>") % exc.args[0])
            return
        if not delivered:
            session._post_in_channel(Markup("<p>%s</p>") % _(
                "The session no longer exists on the agent server (it was probably stopped). "
                "Start a new session instead."))

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
        d'origine (log complet en pièce jointe). Deux familles de signaux :
        - task_done/needs_input : explicites (report-status.sh), source de vérité. Acceptés aussi
          quand la session est déjà en attente : l'utilisateur a pu reprendre la main depuis
          IAssistant, la suite doit alors être suivie dans Odoo comme après une réponse d'ici.
        - idle/ended : heuristique busy/idle de claude-console, simple filet de sécurité si l'agent
          plante avant d'appeler report-status.sh. Ignorée dès que la session est en attente : une
          session vivante repasse 'idle' après chaque tour, ce serait un doublon du needs_input.
        Une question (needs_input) laisse la session VIVANTE pour qu'on puisse y répondre (depuis
        Odoo, voir action_reply, ou depuis IAssistant) ; seule la fin de tâche la termine."""
        self.ensure_one()
        if status not in ('idle', 'ended', 'task_done', 'needs_input'):
            return
        explicit = status in ('task_done', 'needs_input')
        if self.status != 'running' and not (explicit and self.status == 'needs_attention'):
            return  # déjà finalisée (callback dédoublonné) ou signal ignoré
        # Le contrôleur tourne en public : OdooBot pour que le message soit attribué proprement.
        self = self.with_user(self.env.ref('base.user_root')).sudo()
        if status in ('idle', 'ended') and not (conclusion or '').strip():
            conclusion = self._fetch('last-message').get('text') or ''
            is_done = status == 'ended' or AI_AGENT_DONE_MARKER in conclusion
        else:
            is_done = status in ('task_done', 'ended')
        text = (conclusion or '').replace(AI_AGENT_DONE_MARKER, '').strip() or _("Session ended.")

        attachment_ids = []
        if is_done:
            attachment_ids = self._attach_transcript()
            self._kill_remote_session()
        self.write({'status': 'done' if is_done else 'needs_attention', 'conclusion': text})
        self._notify_systray()
        self._post_conclusion(text, is_done, attachment_ids)
        self._post_in_channel(Markup("<p>%s %s</p>") % (
            '✅' if is_done else '❓', Markup(plaintext2html(text))))

    # -- Réponse / fin depuis Odoo ---------------------------------------------

    def action_reply(self, text, echo=True):
        """Transmet la réponse de l'utilisateur à la session restée vivante après une question
        (`/message` du webhook) ; la session repasse 'En cours' et le callback suivant (fin de tâche
        ou nouvelle question) est posté comme d'habitude. Renvoie False (et passe la session en
        'Annulée') si elle n'existe plus côté serveur : cas des sessions arrêtées avant que les
        questions la laissent vivante, ou arrêtées depuis."""
        self.ensure_one()
        session = self.sudo()
        text = (text or '').strip()
        if not text:
            raise UserError(_("Please type your answer."))
        # Verrou de ligne : le callback de l'agent peut arriver avant le commit de cette requête ;
        # sans verrou il verrait l'ancien statut puis notre 'running' écraserait son 'done'.
        self.env.cr.execute("SELECT id FROM ai_agent_session WHERE id = %s FOR UPDATE", [session.id])
        session.invalidate_recordset(['status'])
        if session.status != 'needs_attention':
            raise UserError(_("This session is not waiting for an answer."))
        session.write({'status': 'running'})
        if not session._send_to_agent(text):
            return False
        if echo and session.channel_id:
            # Réponse donnée hors du chat (systray) : on la recopie pour que la conversation reste complète.
            session.channel_id.sudo().with_context(ai_agent_no_forward=True).message_post(
                body=plaintext2html(text), author_id=session.user_id.partner_id.id,
                message_type='comment', subtype_xmlid='mail.mt_comment')
        return True

    def _send_to_agent(self, text):
        """Envoie `text` à la session vivante (`/message`). Renvoie False, session passée en
        'Annulée', si elle n'existe plus côté serveur."""
        self.ensure_one()
        session = self
        user = session.user_id
        try:
            response = requests.post(
                f'{user.claude_webhook_url.rstrip("/")}/api/webhook/sessions/{session.session_name}/message',
                json={'text': text},
                headers={'X-Webhook-Token': user.claude_webhook_token},
                timeout=15,
            )
        except requests.RequestException as exc:
            _logger.warning("AI Agent: could not send the answer to session %s: %s", session.session_name, exc)
            raise UserError(_("Could not reach the AI Agent webhook: %s", exc)) from exc
        # claude-console répond 400 « nom de session invalide » (et non 404) dès qu'une session a été
        # retirée de son suivi — c'est ce que fait l'arrêt par DELETE — et 404 si elle a disparu de
        # `claude agents` : dans les deux cas elle n'existe plus, ce n'est pas un souci réseau.
        if response.status_code in (400, 404):
            session.write({
                'status': 'cancelled',
                'conclusion': _("The session no longer exists on the agent server (it was probably stopped)."),
            })
            session._notify_systray()
            return False
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise UserError(_("Could not reach the AI Agent webhook: %s", exc)) from exc
        session._notify_systray()
        return True

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
