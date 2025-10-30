# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models, _

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _is_postpaid_line(self):
        # A SO line is already postpaid if the invoicing policy of the product is 'delivered', we just need to add a condition based on the SO plan.
        self.ensure_one()
        res = super()._is_postpaid_line()
        return res or self.order_id.plan_id.subscription_invoice_policy == 'postpaid' 
    
    def _prepare_invoice_line(self, **optional_values):
        self.ensure_one()
        res = super()._prepare_invoice_line(**optional_values)
        if not self.display_type:
            if self.order_id.plan_id and self.recurring_invoice and self.order_id.subscription_state != '7_upsell':
                line_to_invoice = self._is_subscription_line_to_invoice()
                if line_to_invoice:
                    if self._is_postpaid_line() and self.order_id.plan_id.ignore_overdelivery and self.product_id.service_policy != 'ordered_prepaid':
                        qty_to_invoice = min(self.qty_delivered, self.product_uom_qty)
                        res.update({
                            'quantity': qty_to_invoice,
                        })
                    elif self._is_postpaid_line() and self.product_id.service_policy == 'ordered_prepaid':
                        qty_to_invoice = self.product_uom_qty - self.qty_invoiced
                        res.update({
                            'quantity': qty_to_invoice,
                        })
        return res