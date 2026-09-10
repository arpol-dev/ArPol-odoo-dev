# -*- coding: utf-8 -*-
# Trace durable d'une session agent, indépendante du cycle de vie de mail.activity (que
# action_feedback() supprime dès qu'une activité est marquée terminée). Sans ce modèle séparé,
# impossible de garder une session "terminée" visible dans la liste de notifications après coup —
# c'est tout l'intérêt de ce modèle : survivre à la suppression de l'activité d'origine.
from odoo import api, fields, models

AI_AGENT_SESSION_STATUS = [
    ('running', "Running"),
    ('needs_attention', "Needs your attention"),
    ('done', "Done"),
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
