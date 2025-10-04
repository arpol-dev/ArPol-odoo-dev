# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models


class SaleSubscriptionPlan(models.Model):
    _inherit = 'sale.subscription.plan'

    subscription_invoice_policy = fields.Selection(
        selection=[
            ('prepaid', "Prepaid Invoicing (in advance)"),
            ('postpaid', "Postpaid Invoicing (in arrears)")
        ],
        string="Default Subscription Invoicing Policy",
        default='prepaid',
        help="Determines whether the subscriptions are invoiced in advance or in arrears.",
    )
    