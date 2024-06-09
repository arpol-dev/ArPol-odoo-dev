from odoo import models, api

class LoyaltyProgram(models.Model):
    _inherit = 'loyalty.program'

    @api.depends('program_type', 'applies_on')
    def _compute_is_nominative(self):
        for program in self:
            program.is_nominative = program.applies_on == 'both' or\
                (program.program_type == 'ewallet' and program.applies_on == 'future') or\
                program.program_type == 'loyalty'