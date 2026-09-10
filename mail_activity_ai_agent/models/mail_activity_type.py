# -*- coding: utf-8 -*-
# Le modèle IA et le mode de permission sont configurés au niveau du TYPE d'activité, pas de
# chaque activité individuelle : un utilisateur crée un type d'action "AI Agent Session" (ou
# plusieurs variantes, ex. "Analyse approfondie" en Opus, "Vérification rapide" en Haiku) une
# fois, avec sa config, puis n'a plus qu'à choisir le type au moment de planifier.
from odoo import fields, models

from .ai_selections import AI_MODEL_HELP, AI_MODEL_SELECTION, AI_PERMISSION_MODE_HELP, AI_PERMISSION_MODE_SELECTION


class MailActivityType(models.Model):
    _inherit = 'mail.activity.type'

    category = fields.Selection(
        selection_add=[('ai_agent', "AI Agent Session")],
        ondelete={'ai_agent': 'set default'},
    )
    ai_model = fields.Selection(
        AI_MODEL_SELECTION, string="AI Model", default='sonnet', help=AI_MODEL_HELP,
    )
    ai_permission_mode = fields.Selection(
        AI_PERMISSION_MODE_SELECTION, string="Permission Mode", default='acceptEdits',
        help=AI_PERMISSION_MODE_HELP,
    )
