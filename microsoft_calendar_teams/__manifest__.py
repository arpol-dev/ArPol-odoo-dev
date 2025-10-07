# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "Microsoft Teams Calendar Sync",
    "version": "1.0",
    "category": "Sales/Subscriptions",
    "summary": "Allows to use (or not) Teams links for odoo meetings",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "depends": ["microsoft_calendar"],
    "data": [
        "views/calendar_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "AGPL-3",
    "description": "Natively, the module microsoft_calendar (if synced) forces Teams links for all online meetings in Odoo, this module removes that behavior and allows to choose if you want a Teams link or not."
}