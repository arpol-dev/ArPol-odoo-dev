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