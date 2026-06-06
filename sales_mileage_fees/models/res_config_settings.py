# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    company_mileage_fee_config = fields.Boolean(
        string="Frais kilométriques", readonly=False,
        related="company_id.mileage_fee_config")
    company_mileage_fee_product = fields.Many2one(
        'product.product', string="Produit de frais kilométriques",
        related="company_id.mileage_fee_product_id", readonly=False,
        domain="[('type', '=', 'service'), ('sale_ok', '=', True)]",
        help="Produit utilisé pour facturer les frais kilométriques sur les bons de commande. Doit être un service et vendable.")

    @api.onchange('company_mileage_fee_config')
    def _onchange_company_mileage_fee_config(self):
        if not self.company_mileage_fee_config:
            self.company_mileage_fee_product = False