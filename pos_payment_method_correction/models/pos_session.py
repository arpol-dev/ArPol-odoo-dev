from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _shift_payment_method_amounts(self, shifts):
        """Move amounts between payment methods of a closed session, in place.

        ``shifts`` is a list of ``(payment_method, amount)``. ``amount`` is added to the
        session receivable line of the method (``<session> - <method>``), and to the
        document it is reconciled with: the cash statement line of a cash method, or the
        account payment of a bank method. The session move is reset to draft, adjusted,
        posted again and the lines are reconciled again.
        """
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("Session %(session)s has no accounting entry.", session=self.name))
        if self.currency_id != self.company_id.currency_id:
            raise UserError(_("Payment method correction is only supported for sessions in company currency."))
        rounding = self.currency_id.rounding
        shifts = [(method, amount) for method, amount in shifts if not float_is_zero(amount, precision_rounding=rounding)]
        if not shifts:
            return

        AccountMoveLine = self.env['account.move.line']
        plan = []
        for method, amount in shifts:
            if method.type == 'pay_later':
                raise UserError(_("Pay later payments cannot be corrected."))
            line, counterpart = self._find_payment_method_ledger(method)
            if line:
                line.remove_move_reconcile()
            elif amount < 0:
                raise UserError(_("No %(method)s amount to remove from %(session)s.", method=method.name, session=self.name))
            plan.append([method, amount, line, counterpart])

        self.move_id.button_draft()
        moves = self.env['account.move']
        payments = self.env['account.payment']
        for entry in plan:
            method, amount, line, counterpart = entry
            if not line:
                line = AccountMoveLine.create(self._get_combine_receivable_vals(method, amount, amount))
                if method.is_cash_count:
                    statement_line = self.env['account.bank.statement.line'].create(
                        self._get_combine_statement_line_vals(method.journal_id.id, amount, method)
                    )
                    counterpart = statement_line.move_id.line_ids.filtered(lambda l: l.account_id == line.account_id)
                    moves |= statement_line.move_id
                else:
                    counterpart = self._create_combine_account_payment(method, {'amount': amount, 'amount_converted': amount}, 0)
                entry[2], entry[3] = line, counterpart
            else:
                document = self._shift_counterpart(line, counterpart, amount)
                if document._name == 'account.payment':
                    payments |= document
                else:
                    moves |= document

        payments.exists().filtered(lambda p: p.state == 'draft').action_post()
        moves = (moves | self.move_id).exists()
        moves.filtered(lambda m: m.state != 'posted' and m.line_ids).action_post()

        for method, amount, line, counterpart in plan:
            if line.exists() and counterpart.exists():
                (line | counterpart).with_context(no_cash_basis=True).reconcile()

    def _find_payment_method_ledger(self, payment_method):
        """Return the session receivable line of a payment method and its counterpart.

        The line is found through the cash statement line (cash method) or the account
        payment (bank method) of the session, not through its name: the name is written
        at closing, with the name the payment method had at that time.
        """
        self.ensure_one()
        receivable = self._get_receivable_account(payment_method)
        if payment_method.is_cash_count:
            statement_lines = self.env['account.bank.statement.line'].search([
                ('pos_session_id', '=', self.id),
                ('journal_id', '=', payment_method.journal_id.id),
            ])
            counterparts = statement_lines.move_id.line_ids.filtered(lambda l: l.account_id == receivable)
        else:
            payments = self.env['account.payment'].search([
                ('pos_session_id', '=', self.id),
                ('pos_payment_method_id', '=', payment_method.id),
            ])
            counterparts = payments.move_id.line_ids.filtered(lambda l: l.account_id == receivable)
        if not counterparts:
            return self.env['account.move.line'], self.env['account.move.line']
        if len(counterparts) != 1:
            raise UserError(_("Several cash or bank documents for %(method)s in %(session)s.", method=payment_method.name, session=self.name))
        line = (counterparts.matched_debit_ids.debit_move_id | counterparts.matched_credit_ids.credit_move_id).filtered(
            lambda l: l.move_id == self.move_id
        )
        if len(line) != 1:
            raise UserError(_(
                "The %(method)s receivable line of %(session)s is not reconciled with a single cash or bank document.",
                method=payment_method.name, session=self.name,
            ))
        return line, counterparts

    def _shift_counterpart(self, line, counterpart, amount):
        """Shift the session line and its counterpart document by ``amount``.

        Returns the account payment or the statement move to post again, or an
        empty move when the document was removed because its amount became zero.
        """
        rounding = self.currency_id.rounding
        new_balance = line.balance + amount
        if float_is_zero(new_balance, precision_rounding=rounding):
            new_balance = 0.0
        line.with_context(check_move_validity=False).write({'debit': max(new_balance, 0.0), 'credit': max(-new_balance, 0.0)})

        document_amount = -counterpart.balance + amount
        if float_is_zero(document_amount, precision_rounding=rounding):
            if counterpart.payment_id:
                counterpart.payment_id.action_draft()
                counterpart.payment_id.unlink()
            else:
                statement_line = counterpart.move_id.statement_line_id
                statement_line.move_id.button_draft()
                statement_line.unlink()
            return self.env['account.move']
        if document_amount < 0:
            raise UserError(_("A correction cannot change the sign of a payment in %(session)s.", session=self.name))

        if counterpart.payment_id:
            payment = counterpart.payment_id
            payment.action_draft()
            payment.write({'amount': document_amount})
            return payment
        statement_line = counterpart.move_id.statement_line_id
        statement_line.move_id.button_draft()
        statement_line.write({'amount': document_amount})
        return statement_line.move_id
