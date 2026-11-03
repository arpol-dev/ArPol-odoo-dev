# -*- coding: utf-8 -*-
# Modèles disponibles sur le serveur IArPol, copiés depuis GET /api/webhook/models. Liste partagée :
# un seul serveur OpenCode. Les modèles absents de la dernière synchronisation sont désactivés et
# non supprimés, pour garder le lien avec les sessions déjà lancées.
from odoo import fields, models


class AiAgentModel(models.Model):
    _name = 'ai.agent.model'
    _description = 'AI Agent Model'
    _order = 'provider, name'

    code = fields.Char(string="Code", required=True, index=True, help="Identifier sent to the server: provider/model.")
    name = fields.Char(string="Name", required=True)
    provider = fields.Char(string="Provider")
    variants = fields.Char(string="Variants", help="Variants reported by the server (not used yet).")
    status = fields.Char(string="Status")
    active = fields.Boolean(default=True)
    _sql_constraints = [
        ('code_unique', 'unique(code)', "Each AI Agent model must have a unique code."),
    ]

    def _sync_from_server(self, models_data):
        """Crée ou met à jour les modèles reçus, désactive ceux qui ne sont plus listés."""
        seen = set()
        for data in models_data:
            code = data.get('id')
            if not code or code in seen:
                continue
            seen.add(code)
            values = {
                'name': data.get('name') or code,
                'provider': data.get('provider'),
                'variants': ', '.join(data.get('variants') or []),
                'status': data.get('status'),
                'active': True,
            }
            record = self.search([('code', '=', code)], limit=1)
            if record:
                record.write(values)
            else:
                self.create(dict(values, code=code))
        self.search([('code', 'not in', list(seen)), ('active', '=', True)]).write({'active': False})
        return len(seen)
