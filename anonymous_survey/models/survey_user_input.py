# -*- coding: utf-8 -*-
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, api, SUPERUSER_ID

class SurveyUserInput(models.Model):
    _inherit = "survey.user_input"

    def _register_postcommit_hook_for_anonymous_survey(self, record_ids):
        """Register a postcommit hook to force write_uid=OdooBot and create_uid=OdooBot for anonymous surveys.

        This is necessary because Odoo's ORM automatically updates write_uid during
        the flush() operation that happens in commit(), overwriting any previous value.
        Using a postcommit hook ensures our correction happens AFTER all ORM operations.

        :param record_ids: tuple of survey.user_input IDs to fix
        """
        if not record_ids:
            return

        dbname = self.env.cr.dbname

        @self.env.cr.postcommit.add
        def fix_metadata_for_anonymous_survey():
            """Reset write_uid and create_uid to OdooBot after all ORM operations complete."""
            from odoo import registry
            db_registry = registry(dbname)
            with db_registry.cursor() as cr:
                cr.execute(
                    "UPDATE survey_user_input SET write_uid = %s, create_uid = %s WHERE id IN %s",
                    (SUPERUSER_ID, SUPERUSER_ID, record_ids)
                )

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to clean personal data and register postcommit hook for anonymous surveys."""
        # Separate anonymous and non-anonymous surveys
        anonymous_vals = []
        normal_vals = []

        for vals in vals_list:
            survey = self.env["survey.survey"].browse(vals.get('survey_id'))
            if survey and survey.anonymous_survey:
                # Remove personal information for anonymous surveys
                vals['partner_id'] = False
                vals['email'] = False
                vals['nickname'] = False
                anonymous_vals.append(vals)
            else:
                normal_vals.append(vals)

        records = self.env['survey.user_input']

        # Create anonymous surveys - use sudo to ensure OdooBot is used initially
        if anonymous_vals:
            records |= super(SurveyUserInput, self.sudo()).create(anonymous_vals)

        # Create non-anonymous surveys with current context
        if normal_vals:
            records |= super(SurveyUserInput, self).create(normal_vals)

        # Register postcommit hook for anonymous records to fix UIDs after flush
        anonymous_records = records.filtered(lambda r: r.survey_id.anonymous_survey)
        if anonymous_records:
            self._register_postcommit_hook_for_anonymous_survey(tuple(anonymous_records.ids))

        return records

    def write(self, vals):
        """Override write to clean personal data and register postcommit hook for anonymous surveys.

        This captures ALL write operations including:
        - Direct writes (_mark_in_progress, _mark_done, _save_lines)
        - Field assignments (last_displayed_page_id)
        - Computed field updates (scoring_percentage, scoring_total, scoring_success)
        """
        # Separate records by survey type
        anonymous_records = self.filtered(lambda r: r.survey_id.anonymous_survey)
        normal_records = self - anonymous_records

        result = True

        # For anonymous surveys, clean personal data and use sudo
        if anonymous_records:
            vals_copy = vals.copy()
            # Remove personal information if present in vals
            vals_copy.pop('partner_id', None)
            vals_copy.pop('email', None)
            vals_copy.pop('nickname', None)

            result &= super(SurveyUserInput, anonymous_records.sudo()).write(vals_copy)

        # For non-anonymous surveys, preserve current context
        if normal_records:
            result &= super(SurveyUserInput, normal_records).write(vals)

        # Register postcommit hook for anonymous records to fix UIDs after flush
        if anonymous_records:
            self._register_postcommit_hook_for_anonymous_survey(tuple(anonymous_records.ids))

        return result