# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import _, api, fields, models


class SaleSubscriptionPlan(models.Model):
    _inherit = 'sale.subscription.plan'

    subscription_invoice_policy = fields.Selection(
        selection=[
            ('mixed', "Standard"),
            ('postpaid', "Force postpaid invoicing")
        ],
        string="Default Subscription Invoicing Policy",
        default='prepaid',
        help="Determines whether the subscriptions are invoiced in advance or in arrears.",
    )

    ignore_overdelivery = fields.Boolean(
        string="ignore overdelivery",
        default=False,
        help="If checked, the deliveries that are not ordered will not be invoiced on the subscription's postpaid lines.",
    )
    