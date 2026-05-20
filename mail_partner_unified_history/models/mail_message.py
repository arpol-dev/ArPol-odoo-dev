# mail_partner_unified_history/models/mail_message.py
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
            ('author_id', 'child_of', partner_id),
            ('notification_ids.res_partner_id', 'child_of', [partner_id]),
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

        # Batch-fetch internal user IDs for author partners
        author_partner_ids = list({m.author_id.id for m in accessible if m.author_id})
        if author_partner_ids:
            users_data = self.env['res.users'].sudo().search_read(
                [('partner_id', 'in', author_partner_ids), ('share', '=', False)],
                ['partner_id'],
            )
            partner_to_user = {u['partner_id'][0]: u['id'] for u in users_data}
        else:
            partner_to_user = {}

        model_name_cache = {}
        result = []
        for msg in accessible:
            model_key = msg.model
            if model_key and model_key not in model_name_cache:
                try:
                    model_name_cache[model_key] = self.env['ir.model']._get(model_key).name
                except Exception:
                    model_name_cache[model_key] = False

            email_status = None
            notifs = msg.notification_ids.filtered(
                lambda n: n.notification_type == 'email'
            )
            if notifs:
                statuses = set(notifs.mapped('notification_status'))
                if statuses & {'exception', 'bounce'}:
                    email_status = 'exception'
                elif 'ready' in statuses:
                    email_status = 'ready'
                else:
                    email_status = 'sent'

            result.append({
                'id': msg.id,
                'author_id': [msg.author_id.id, msg.author_id.display_name]
                             if msg.author_id else False,
                'author_user_id': partner_to_user.get(msg.author_id.id) if msg.author_id else None,
                'date': msg.date.isoformat() if msg.date else False,
                'body': msg.body or '',
                'message_type': msg.message_type,
                'is_internal': msg.is_internal,
                'model': msg.model or False,
                'res_id': msg.res_id or False,
                'record_name': msg.record_name or '',
                'model_description': model_name_cache.get(model_key or '', False),
                'email_status': email_status,
            })
        return result
