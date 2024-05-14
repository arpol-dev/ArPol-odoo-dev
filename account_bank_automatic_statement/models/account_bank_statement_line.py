# Copyright 2024 ArPol
# @author: Armand Polmard <armand@arpol.fr>
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models
import datetime
import logging


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    @api.model_create_multi
    def create(self, vals_list):
        logging.warning('start')
        journal = 0
        logging.info(self)
        new_bank_statement = False
        for vals in vals_list:
            journal = self.env['account.journal'].search([('id','=',vals['journal_id'])])
            if journal.type == 'cash' or journal.bank_statements_source == 'manual':
                date = datetime.datetime.strptime(vals['date'],'%Y-%m-%d')
                month_start = datetime.datetime(date.year, date.month, 1)
                next_month = month_start + datetime.timedelta(days=40)
                month_end = datetime.datetime(next_month.year, next_month.month, 1)

                bank_statement = self.env['account.bank.statement'].search([
                    ('journal_id','=',journal.id),
                    ('date','>=',month_start),
                    ('date','<',month_end)
                ])
                
                if not bank_statement:
                    new_bank_statement = True
                    name = "%s/%s" % (journal.code, month_start.strftime("%Y-%m-%d"))
                    statement_vals = {'name': name, 'journal_id': journal.id}
                    bank_statement = self.env['account.bank.statement'].with_context(journal_id=journal.id,).create(statement_vals)

                vals['statement_id'] = bank_statement.id
                
        res = super().create(vals_list)

        for statement in self.env['account.bank.statement'].search([('journal_id','=',journal.id)], order="name asc"):
            logging.info(statement)
            statement._compute_balance_start()

        logging.warning('end')
        return res




            
