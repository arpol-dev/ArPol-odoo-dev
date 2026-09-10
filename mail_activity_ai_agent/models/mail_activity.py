# -*- coding: utf-8 -*-
import json
import logging
import secrets

import requests
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.tools import html2plaintext

from .ai_selections import (
    AI_AGENT_DONE_MARKER,
    AI_MODEL_HELP,
    AI_MODEL_SELECTION,
    AI_PERMISSION_MODE_HELP,
    AI_PERMISSION_MODE_SELECTION,
)

_logger = logging.getLogger(__name__)

# Champs systématiquement exclus du dump JSON transmis à l'agent : binaires (trop volumineux,
# inutiles en texte) et champs mail.thread qui dupliqueraient l'historique déjà transmis à part.
AI_AGENT_EXCLUDED_FIELD_NAMES = {
    'message_ids', 'message_follower_ids', 'message_partner_ids',
    'message_main_attachment_id', 'activity_ids', 'website_message_ids',
}
AI_AGENT_EXCLUDED_FIELD_TYPES = {'binary'}


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    # Préremplis depuis le type d'activité (comme summary/note/activity_user_id dans le core),
    # mais librement modifiables à la création : compute + readonly=False, pas related. Une
    # valeur passée explicitement à create() (ex. par le wizard, voir mail_activity_schedule.py)
    # prend le pas sur le compute — c'est le mécanisme standard Odoo pour "défaut éditable".
    # `activity_category` (related='activity_type_id.category', champ core) sert de test
    # "est-ce une activité AI Agent ?" — pas besoin d'un booléen custom.
    ai_model = fields.Selection(
        AI_MODEL_SELECTION, string="AI Model", compute='_compute_ai_model',
        store=True, readonly=False, help=AI_MODEL_HELP,
    )
    ai_permission_mode = fields.Selection(
        AI_PERMISSION_MODE_SELECTION, string="Permission Mode", compute='_compute_ai_permission_mode',
        store=True, readonly=False, help=AI_PERMISSION_MODE_HELP,
    )
    ai_status = fields.Selection(
        [
            ('to_launch', "To launch"),
            ('running', "Running"),
            ('needs_attention', "Needs your attention"),
            ('error', "Error"),
        ],
        string="Agent Status", default='to_launch', readonly=True, copy=False,
    )
    ai_session_name = fields.Char(string="Agent Session", readonly=True, copy=False)
    ai_remote_url = fields.Char(string="Remote Session URL", readonly=True, copy=False)
    ai_callback_secret = fields.Char(readonly=True, copy=False)
    # Trace de suivi indépendante (voir ai_agent_session.py) : survit à la suppression de
    # l'activité elle-même à la clôture, alimente le menu de notifications dédié.
    ai_agent_session_id = fields.Many2one('ai.agent.session', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        activities = super().create(vals_list)
        for activity in activities:
            if activity.activity_category == 'ai_agent':
                activity._ai_agent_launch()
        return activities

    @api.depends('activity_type_id')
    def _compute_ai_model(self):
        for activity in self:
            if activity.activity_type_id.ai_model:
                activity.ai_model = activity.activity_type_id.ai_model

    @api.depends('activity_type_id')
    def _compute_ai_permission_mode(self):
        for activity in self:
            if activity.activity_type_id.ai_permission_mode:
                activity.ai_permission_mode = activity.activity_type_id.ai_permission_mode

    # -- Lancement -----------------------------------------------------------

    def _ai_agent_launch(self):
        """Appelle le webhook de l'utilisateur responsable pour démarrer une session agent."""
        self.ensure_one()
        user = self.user_id
        if not user.claude_webhook_url or not user.claude_webhook_token:
            self._ai_agent_report_error(_(
                "%(user)s has no AI Agent webhook configured (Preferences > AI Agent).",
                user=user.display_name,
            ))
            return

        secret = secrets.token_urlsafe(24)
        self.write({'ai_callback_secret': secret, 'ai_status': 'running'})

        payload = {
            'cwd': user.claude_webhook_cwd or '',
            'prompt': self._ai_agent_build_prompt(),
            'model': self.ai_model or None,
            'permissionMode': self.ai_permission_mode or None,
            'label': self._ai_agent_session_label(),
            'idempotencyKey': f'odoo-activity-{self.id}',
            'callbackUrl': self._ai_agent_callback_url(secret),
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
            _logger.warning("AI Agent webhook call failed for activity %s: %s", self.id, exc)
            self._ai_agent_report_error(_("Could not reach the AI Agent webhook: %s", exc))
            return

        self.write({
            'ai_session_name': data.get('name'),
            'ai_remote_url': data.get('remoteControlUrl'),
        })
        self._ai_agent_sync_session_record(
            status='running', session_name=data.get('name'), remote_url=data.get('remoteControlUrl'),
        )

    def _ai_agent_report_error(self, message):
        self.write({'ai_status': 'error'})
        self._ai_agent_sync_session_record(status='error', conclusion=str(message))
        record = self._ai_agent_related_record()
        if record:
            record.message_post(body=Markup("<p>🤖 %s</p>") % message)

    def _ai_agent_sync_session_record(self, **vals):
        """Crée ou met à jour la trace de suivi (ai.agent.session) qui alimente le menu systray
        de notifications — voir models/ai_agent_session.py pour pourquoi ce modèle est séparé
        de mail.activity."""
        self.ensure_one()
        session = self.ai_agent_session_id
        if not session:
            record = self._ai_agent_related_record()
            session = self.env['ai.agent.session'].sudo().create({
                'name': self._ai_agent_session_label(),
                'user_id': self.user_id.id,
                'activity_id': self.id,
                'res_model': self.res_model,
                'res_id': self.res_id,
                'res_name': record.display_name if record else self.res_name,
                **vals,
            })
            self.ai_agent_session_id = session.id
        else:
            session.sudo().write(vals)
        session._notify_systray()
        return session

    def _ai_agent_session_label(self):
        # Le résumé de l'activité sert de nom de session (visible dans claude.ai/code, l'appli
        # mobile, et la liste de sessions IAssistant) — c'est ce que l'utilisateur a tapé comme
        # intitulé de sa demande, donc le plus parlant pour reconnaître une session dans une liste.
        if self.summary:
            return self.summary[:80]
        record = self._ai_agent_related_record()
        record_label = record.display_name if record else self.res_name or ''
        return (f"{record_label} — {self.activity_type_id.name}" if record_label
                else self.activity_type_id.name)[:80]

    def _ai_agent_callback_url(self, secret):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f'{base_url}/claude_agent/callback?activity_id={self.id}&secret={secret}'

    def _ai_agent_related_record(self):
        self.ensure_one()
        if self.res_model and self.res_id:
            return self.env[self.res_model].browse(self.res_id)
        return False

    # -- Construction du prompt ----------------------------------------------

    def _ai_agent_build_prompt(self):
        self.ensure_one()
        record = self._ai_agent_related_record()
        sections = [
            self._ai_agent_prompt_boundaries(),
            self._ai_agent_prompt_context(record),
            self._ai_agent_prompt_process_instructions(),
            self._ai_agent_prompt_record_json(record),
            self._ai_agent_prompt_chatter_history(record),
            self._ai_agent_prompt_user_request(),
        ]
        return '\n\n'.join(section for section in sections if section)

    def _ai_agent_prompt_boundaries(self):
        # En tête du prompt, avant tout le reste : garde-fou de sécurité ajouté suite à un
        # incident réel (2026-09-02) où l'agent est allé au-delà de ce qui était attendu sur un
        # ticket client. Volontairement sans exception ni nuance — la moindre ambiguïté ici a un
        # coût réel (contact client non souhaité, enregistrement clôturé à tort).
        return (
            "# Hard limits — always apply, no exception\n"
            "You act on behalf of Armand only. He is the only person you take instructions from "
            "and the only person you address.\n"
            "- NEVER contact, reply to, or communicate with a client/customer directly, through "
            "any channel — no email, no message on a ticket or record visible to a client/portal "
            "user, nothing sent on Armand's behalf without him reviewing it first. If a "
            "client-facing reply seems warranted, draft it and give it to Armand instead of "
            "sending it — don't send or post it yourself, under any circumstance.\n"
            "- NEVER close, resolve, or otherwise change the status/stage of this ticket or any "
            "other record (e.g. marking a helpdesk ticket solved, changing a stage, closing an "
            "opportunity). You may read and explore freely, but only Armand decides when "
            "something in the business data is actually done.\n"
            "- This applies no matter how you access the database (the Odoo web session, "
            "JSON-RPC/XML-RPC with your own credentials, or anything else) — these limits are "
            "about what you're allowed to do, not which tool you use to do it.\n"
            "- If completing the task would require doing either of the above, stop and ask "
            "Armand instead (see below for how) rather than doing it yourself."
        )

    def _ai_agent_prompt_context(self, record):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        db_name = self.env.cr.dbname
        lines = [
            "# Context",
            "You were invoked automatically by a webhook from an Odoo activity. "
            "Below is everything needed to understand what this task is about.",
            f"- Odoo database: {db_name} ({base_url})",
        ]
        if record:
            record_url = f"{base_url}/odoo/{record._name.replace('.', '-')}/{record.id}"
            lines.append(f"- Related record: {record._name} #{record.id} — {record.display_name}")
            lines.append(f"- Direct link: {record_url}")
            company = getattr(record, 'company_id', False)
            if company:
                lines.append(f"- Company: {company.display_name}")
        lines.append(
            "You may connect to this database yourself via JSON-RPC/XML-RPC with your own "
            "credentials, if you have any configured, to explore further than what is included "
            "below — read/exploration only, the hard limits above still apply."
        )
        return '\n'.join(lines)

    def _ai_agent_prompt_process_instructions(self):
        # Session à tour unique (2026-09-01, à la demande d'Armand) : dès que l'agent s'arrête de
        # générer (busy->idle), la session est automatiquement tuée côté serveur — que la réponse
        # soit une conclusion ou une question bloquante. Il n'y a donc plus de "reprise" possible
        # dans la même session : le prompt doit être explicite là-dessus pour que l'agent ne
        # planifie pas un futur échange qui n'aura jamais lieu.
        return (
            "# How this session works (important)\n"
            "This session runs a single unattended turn — nobody is watching it live, and as "
            "soon as you stop generating, this session is automatically terminated. There is no "
            "back-and-forth: you will not get a chance to ask something and wait here for a "
            "reply. Do as much as you reasonably can on your own (including using your own "
            "database access, see above) before concluding.\n"
            f"- When your task is ENTIRELY complete (nothing left pending, no question), end "
            f"your final reply with this exact line, alone, with nothing after it:\n"
            f"{AI_AGENT_DONE_MARKER}\n"
            "- If you genuinely cannot proceed without a decision or input from Armand, end your "
            "reply instead with a clear, self-contained question or summary of what's blocking "
            "you. He will see it in Odoo and decide whether to follow up (e.g. by launching a "
            f"new session with the answer) — do not add {AI_AGENT_DONE_MARKER} in that case."
        )

    def _ai_agent_prompt_record_json(self, record):
        if not record:
            return ''
        field_names = [
            name for name, field in record._fields.items()
            if field.type not in AI_AGENT_EXCLUDED_FIELD_TYPES
            and name not in AI_AGENT_EXCLUDED_FIELD_NAMES
        ]
        try:
            data = record.read(field_names)[0]
        except Exception as exc:  # noqa: BLE001 - best-effort, ne doit jamais bloquer l'envoi
            _logger.warning("AI Agent: could not serialize record %s: %s", record, exc)
            return ''
        return (
            "# Full record data (JSON)\n"
            "This is every stored field of the related record, as Odoo's technical 'view "
            "record data' would show it:\n"
            f"```json\n{json.dumps(data, default=str, ensure_ascii=False, indent=2)}\n```"
        )

    def _ai_agent_prompt_chatter_history(self, record):
        if not record or not hasattr(record, 'message_ids'):
            return ''
        lines = []
        for message in record.message_ids.sorted(key=lambda m: m.date or m.create_date):
            author = message.author_id.display_name or message.email_from or 'System'
            body = html2plaintext(message.body) if message.body else ''
            if not body:
                continue
            lines.append(f"[{message.date}] {author}: {body}")
        if not lines:
            return ''
        return "# Full chatter history (includes past activities)\n" + '\n'.join(lines)

    def _ai_agent_prompt_user_request(self):
        note = html2plaintext(self.note) if self.note else ''
        request_text = note or self.summary or ''
        return "# User request (your main task)\n" + request_text

    # -- Réception du callback ------------------------------------------------

    def _ai_agent_handle_callback(self, status, session_name):
        """Traite un événement busy->idle ('idle') ou de fin de process ('ended') renvoyé par le
        webhook pour la session liée à cette activité. Session à tour unique (voir
        _ai_agent_prompt_process_instructions) : les deux statuts sont traités de façon identique
        et terminent systématiquement la session, qu'il s'agisse d'une conclusion ou d'une
        question bloquante — pas de statut 'busy' à gérer, une session tuée ne redémarre jamais
        toute seule. Le nom de session transmis n'est utilisé que pour du logging : la lecture se
        base sur ai_session_name, celui qu'on a nous-mêmes enregistré au lancement (le secret
        suffit à authentifier l'appelant, mais on ne fait pas pour autant confiance à un nom de
        session arbitraire dans le payload)."""
        self.ensure_one()
        if status not in ('idle', 'ended'):
            return
        # Le contrôleur tourne en public (auth='public', appelé par un serveur externe) : on
        # bascule sur OdooBot pour que les messages/actions postés soient attribués proprement,
        # plutôt qu'à l'utilisateur public anonyme.
        self = self.with_user(self.env.ref('base.user_root')).sudo()
        if session_name and session_name != self.ai_session_name:
            _logger.warning(
                "AI Agent: callback session name mismatch on activity %s (got %s, expected %s)",
                self.id, session_name, self.ai_session_name,
            )

        last_message = self._ai_agent_fetch(self.ai_session_name, 'last-message').get('text') or ''
        is_done = status == 'ended' or AI_AGENT_DONE_MARKER in last_message

        if is_done:
            self._ai_agent_close(last_message)
        else:
            self._ai_agent_notify_needs_attention(last_message)

    def _ai_agent_fetch(self, session_name, endpoint):
        user = self.user_id
        if not session_name or not user.claude_webhook_url:
            return {}
        try:
            response = requests.get(
                f'{user.claude_webhook_url.rstrip("/")}/api/webhook/sessions/{session_name}/{endpoint}',
                headers={'X-Webhook-Token': user.claude_webhook_token},
                timeout=15,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            _logger.warning("AI Agent: could not fetch %s for session %s: %s", endpoint, session_name, exc)
            return {}

    def _ai_agent_close(self, last_message):
        conclusion = (last_message.replace(AI_AGENT_DONE_MARKER, '').strip()
                      or _("Session ended."))
        transcript = self._ai_agent_fetch(self.ai_session_name, 'transcript').get('text') or ''
        attachment_ids = []
        if transcript:
            attachment = self.env['ir.attachment'].sudo().create({
                'name': 'session_log.txt',
                'res_model': 'mail.activity',
                'res_id': self.id,
                'raw': transcript.encode(),
                'mimetype': 'text/plain',
            })
            attachment_ids = attachment.ids
        # La tâche est définitivement close côté Odoo : on termine aussi la session côté serveur,
        # plutôt que de la laisser tourner indéfiniment sans plus personne pour en suivre l'issue.
        # Avant action_feedback (qui supprime l'activité) tant que ai_session_name est encore lisible.
        self._ai_agent_kill_session()
        # Idem pour la trace de suivi : ai_agent_session_id doit encore être lisible sur self.
        self._ai_agent_sync_session_record(status='done', conclusion=conclusion)
        # action_feedback déplace les pièces jointes liées à l'activité sur le message final,
        # puis supprime l'activité : ne plus rien lire sur self après cet appel.
        self.sudo().action_feedback(feedback=conclusion, attachment_ids=attachment_ids)

    def _ai_agent_kill_session(self):
        user = self.user_id
        if not self.ai_session_name or not user.claude_webhook_url:
            return
        try:
            requests.delete(
                f'{user.claude_webhook_url.rstrip("/")}/api/webhook/sessions/{self.ai_session_name}',
                headers={'X-Webhook-Token': user.claude_webhook_token},
                timeout=15,
            )
        except requests.RequestException as exc:
            _logger.warning("AI Agent: could not kill session %s: %s", self.ai_session_name, exc)

    def _ai_agent_notify_needs_attention(self, last_message):
        # Session à tour unique : une question bloquante termine la session comme une conclusion
        # (voir _ai_agent_handle_callback) — on la tue ici aussi, sinon elle resterait allumée
        # indéfiniment sans que plus personne ne la pilote. Pas de lien "reconnectez-vous à la
        # session" : il n'y a plus de session vivante à rejoindre une fois celle-ci tuée. Pour
        # répondre, Armand relance une nouvelle activité/session avec sa réponse.
        self._ai_agent_kill_session()
        self.write({'ai_status': 'needs_attention'})
        self._ai_agent_sync_session_record(status='needs_attention', conclusion=last_message)
        record = self._ai_agent_related_record()
        if not record:
            return
        body = Markup(
            "<p>🤖 The AI Agent stopped on activity <b>%s</b>, waiting for your input:</p>"
            "<p>%s</p>"
        ) % (self.summary or self.activity_type_id.name, last_message)
        record.message_post(body=body)
