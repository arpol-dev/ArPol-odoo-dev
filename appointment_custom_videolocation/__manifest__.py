# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "Appointment Custom Video Location",
    "version": "1.0",
    "summary": "Allow to manually define the video link for each meeting.",
    "author": "Armand POLMARD",
    "category": "Services",
    "depends": ["appointment"],
    "data": [
        "views/appointment_view.xml",
        "views/res_users_view.xml",
    ],
    "license": 'LGPL-3',
    "installable": True,
    "application": False,
}