# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "Sale Subscription Postpaid Invoicing",
    "version": "1.0",
    "category": "Sales/Subscriptions",
    "summary": "Allows to set subscriptions as postpaid invoicing",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "depends": ["sale_subscription"],
    "data": [
        "views/sale_subscription_plan.xml",
    ],
    "installable": True,
    "application": False,
    "license": "AGPL-3",
    "description": "With his module, you can configure your subscription plans to invoice for the previous period, from one billing period in the past until the day before the invoicing date. this forces all the subscription to be postpaid. You can also choose to ignore overdeliveries on postpaid lines when invoicing."
}