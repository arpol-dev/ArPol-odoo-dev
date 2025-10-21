# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api

class SurveySurvey(models.Model):
    _inherit = "survey.survey"

    anonymous_survey = fields.Boolean(
        string="Anonymous Survey",
        default=False,
        help="If checked, the survey will be anonymous. The write_uid will be set to "
             "OdooBot for all operations on survey responses to preserve anonymity."
    )