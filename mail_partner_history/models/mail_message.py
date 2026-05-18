# mail_partner_history/models/mail_message.py
from collections import defaultdict

from odoo import api, models
from odoo.exceptions import AccessError


class MailMessage(models.Model):
    _inherit = 'mail.message'

    @api.model
    def get_partner_history_messages(self, partner_id, limit=30, offset=0):
        """Retourne les messages impliquant partner_id (auteur ou destinataire),
        filtrés silencieusement selon les droits d'accès aux documents liés."""
        domain = [
            '|',
            ('author_id', '=', partner_id),
            ('partner_ids', 'in', [partner_id]),
        ]
        messages = self.search(domain, order='date desc', limit=limit, offset=offset)

        accessible = []
        by_model = defaultdict(list)

        for msg in messages:
            if not msg.model or not msg.res_id:
                accessible.append(msg)
            else:
                by_model[msg.model].append(msg)

        for model_name, model_msgs in by_model.items():
            try:
                Model = self.env[model_name]
                res_ids = list({m.res_id for m in model_msgs})
                accessible_ids = set(Model.search([('id', 'in', res_ids)]).ids)
                accessible.extend(m for m in model_msgs if m.res_id in accessible_ids)
            except (KeyError, AccessError):
                pass

        accessible.sort(key=lambda m: m.date or m.id, reverse=True)

        return [
            {
                'id': msg.id,
                'author_id': [msg.author_id.id, msg.author_id.display_name]
                             if msg.author_id else False,
                'date': msg.date.isoformat() if msg.date else False,
                'body': msg.body or '',
                'message_type': msg.message_type,
                'is_internal': msg.is_internal,
                'model': msg.model or False,
                'res_id': msg.res_id or False,
                'record_name': msg.record_name or '',
            }
            for msg in accessible
        ]
