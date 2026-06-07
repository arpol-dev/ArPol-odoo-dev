# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"
    _check_company_auto = True

    mileage_fee_config = fields.Boolean(
        string="Config Frais kilométriques")
    mileage_fee_product_id = fields.Many2one(
        "product.product", string="Mileage Fee Product",
        domain="[('type', '=', 'service')]",
    )
