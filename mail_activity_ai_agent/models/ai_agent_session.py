# -*- coding: utf-8 -*-
# Trace durable d'une session agent, indépendante du cycle de vie de mail.activity (que
# action_feedback() supprime dès qu'une activité est marquée terminée). Sans ce modèle séparé,
# impossible de garder une session "terminée" visible dans la liste de notifications après coup —
# c'est tout l'intérêt de ce modèle : survivre à la suppression de l'activité d'origine.
import logging

import requests
from markupsafe import Markup

from odoo import _, api, fields, models

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
    _description = 'AI Agent Session (notification tracking)'
    _order = 'create_date desc'
    _rec_name = 'name'

    name = fields.Char(required=True)
    user_id = fields.Many2one('res.users', required=True, index=True, ondelete='cascade')
    activity_id = fields.Many2one('mail.activity', ondelete='set null')
    # Copiés depuis l'activité au lancement : le lien vers l'enregistrement d'origine doit
    # survivre même une fois activity_id devenu vide (activité supprimée à la clôture).
    res_model = fields.Char()
    res_id = fields.Integer()
    res_name = fields.Char()
    status = fields.Selection(AI_AGENT_SESSION_STATUS, default='running', required=True, index=True)
    session_name = fields.Char(string="Claude Session")
    remote_url = fields.Char(string="Remote Session URL")
    conclusion = fields.Text()
    is_dismissed = fields.Boolean(default=False, index=True)
    # Copies non-relationnelles (comme res_model/res_id/res_name) : doivent rester lisibles même
    # une fois l'activité d'origine supprimée (activity_id retombe à False, ondelete='set null').
    # Permettent au contrôleur de callback de retrouver et authentifier une session dont l'activité
    # a disparu avant l'arrivée d'un callback tardif — voir controllers/main.py et
    # mail_activity.py::_ai_agent_cancel.
    source_activity_id = fields.Integer(readonly=True, copy=False)
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

    def _handle_late_callback(self, status, conclusion):
        """Callback reçu pour une session dont le mail.activity d'origine n'existe déjà plus
        (annulée entretemps côté module, ou disparue hors flux normal — trou historique documenté
        dans ArPol-Mind Projets/application_claude.md). Impossible d'agir sur l'activité, mais on
        peut encore finaliser proprement cette trace au lieu de la laisser bloquée en
        'running'/'needs_attention' indéfiniment, et prévenir sur l'enregistrement d'origine si
        possible (res_model/res_id survivent, contrairement à activity_id)."""
        self.ensure_one()
        if self.status not in ('running', 'needs_attention'):
            return  # déjà finalisée par ailleurs (ex. cette même requête a déjà été traitée)
        if status not in ('idle', 'ended', 'task_done', 'needs_input'):
            return
        self._kill_remote_session()
        text = (conclusion or '').strip() or _(
            "Session ended after its source Odoo activity had already been removed."
        )
        new_status = 'done' if status in ('ended', 'task_done') else 'needs_attention'
        self.write({'status': new_status, 'conclusion': text})
        self._notify_systray()
        if self.res_model and self.res_id:
            record = self.env[self.res_model].browse(self.res_id)
            if record.exists():
                record.message_post(body=Markup(
                    "<p>🤖 AI Agent session <b>%s</b> ended, but its Odoo activity had already "
                    "been removed in the meantime:</p><p>%s</p>"
                ) % (self.name, text))
