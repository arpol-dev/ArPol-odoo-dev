# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import json
import logging
import werkzeug

from collections import defaultdict
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from odoo import fields, http, SUPERUSER_ID, _
from odoo.exceptions import UserError
from odoo.http import request, content_disposition
from odoo.osv import expression
from odoo.tools import format_datetime, format_date, is_html_empty
from odoo.addons.base.models.ir_qweb import keep_query
from odoo.addons.survey.controllers.main import Survey as SurveyController


_logger = logging.getLogger(__name__)


class SurveyExtended(SurveyController):

    def _check_validity(self, survey_token, answer_token, ensure_token=True, check_partner=True):
        survey_sudo, answer_sudo = self._fetch_from_access_token(survey_token, answer_token)
        if survey_sudo.anonymous_survey:
            check_partner = False
            _logger.debug("Anonymous survey detected: skipping partner check")

        return super(SurveyExtended, self)._check_validity(survey_token, answer_token, ensure_token=ensure_token, check_partner=check_partner)