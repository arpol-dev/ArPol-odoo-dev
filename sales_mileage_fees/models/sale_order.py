# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models, api
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    mileage_fee_included = fields.Boolean(
        string="Frais kilométriques inclus",
        help="Indique si des frais kilométriques ont été inclus dans les lignes de commande. Cela permet d'éviter d'ajouter plusieurs lignes de frais kilométriques lorsque la commande est mise à jour plusieurs fois.",
        store=True, compute="_compute_mileage_fee_included")
    
    @api.depends('order_line')
    def _compute_mileage_fee_included(self):
        for order in self:
            order.mileage_fee_included = any(line.is_mileage_fee for line in order.order_line)
    
    def action_add_mileage_fee(self):
        mileage_fee_product_id = self.company_id.mileage_fee_product_id
        if not mileage_fee_product_id:
            raise UserError("Aucun produit de frais kilométriques configuré. Veuillez configurer un produit de frais kilométriques dans les paramètres.")
        values = self._prepare_mileage_fee_line_vals(mileage_fee_product_id)
        return self.env['sale.order.line'].create(values)

    def action_update_mileage_fee(self):
        mileage_fee_product_id = self.company_id.mileage_fee_product_id
        if not mileage_fee_product_id:
            raise UserError("Aucun produit de frais kilométriques configuré. Veuillez configurer un produit de frais kilométriques dans les paramètres.")
        
        mileage_fee_line = self.order_line.filtered(lambda line: line.is_mileage_fee)
        if not mileage_fee_line:
            raise UserError("Aucune ligne de frais kilométriques trouvée à mettre à jour.")
        
        values = self._prepare_mileage_fee_line_vals(mileage_fee_product_id)
        mileage_fee_line.write(values)
    
    def _prepare_mileage_fee_line_vals(self, product_id):
        context = {}
        if self.partner_id:
            if self.partner_id.itineraire_state != 'computed':
                self.partner_id.action_compute_itineraire()

            distance = 2 * self.partner_id.itineraire_distance_km - 10

        # Create the sales order line values
        values = {
            'order_id': self.id,
            'product_uom_qty': round(distance, 0) or 1.0,
            'product_id': product_id.id,
        }
        return values
    
class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_mileage_fee = fields.Boolean(
        string="Est une ligne de frais kilométriques", 
        compute="_compute_is_mileage_fee", store=True)
    
    @api.depends('product_id')
    def _compute_is_mileage_fee(self):        
        for line in self:
            mileage_fee_product_id = self.company_id.mileage_fee_product_id
            line.is_mileage_fee = (mileage_fee_product_id and line.product_id.id == mileage_fee_product_id.id)