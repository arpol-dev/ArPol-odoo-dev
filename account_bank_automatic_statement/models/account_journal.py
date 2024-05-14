# Copyright 2023 ArPol
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def __get_bank_statements_available_sources(self):
        result = super().__get_bank_statements_available_sources()
        result.append(("manual", _("Création manuelle des transactions")))
        return result