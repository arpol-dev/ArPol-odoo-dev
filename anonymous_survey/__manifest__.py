# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "Anonymous Survey",
    "version": "1.0",
    "summary": "Allow to create surveys without keeping any information on the user that answers.",
    "author": "Armand POLMARD",
    "category": "Survey",
    "depends": ["survey"],
    "data": [
        "views/survey_survey_views.xml",
    ],
    "license": 'LGPL-3',
    "installable": True,
    "application": False,
    "description": "With this module, a survey can be set as anonymous. This allows the survey to be answered without storing any personal information about the respondent. All personal identifiers are removed, ensuring complete anonymity for the user. The removed datas are : create_uid, last_update_uid, partner_id, email, nickname.",
}