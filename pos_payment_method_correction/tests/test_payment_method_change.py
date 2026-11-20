import uuid

from odoo.addons.point_of_sale.tests.common import TestPoSCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestPosPaymentMethodChange(TestPoSCommon):

    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.product = self.create_product('Product_correction', self.categ_basic, 100, 50)

    def _run_session(self, opening_cash, payments):
        """Open a session, make one order per payment, close it with the theoretical cash."""
        session = self._start_pos_session(self.cash_pm1 | self.bank_pm1, opening_cash)
        self._create_orders([
            {
                'pos_order_lines_ui_args': [(self.product, amount / 100.0)],
                'payments': [(method, amount)],
                'customer': self.customer,
                'is_invoiced': False,
                'uuid': str(uuid.uuid4()),
            }
            for method, amount in payments
        ])
        cash = sum(amount for method, amount in payments if method.is_cash_count)
        session.post_closing_cash_details(opening_cash + cash)
        session.close_session_from_ui()
        return session

    def _correct(self, payment, new_method):
        wizard = self.env['pos.payment.method.change'].create({
            'payment_id': payment.id,
            'new_payment_method_id': new_method.id,
        })
        wizard._onchange_new_payment_method_id()
        wizard.action_apply()
        return wizard

    def _assert_session_accounting_consistent(self, session):
        move = session.move_id
        self.assertEqual(move.state, 'posted')
        self.assertAlmostEqual(sum(move.line_ids.mapped('balance')), 0.0, places=2)
        receivable = move.line_ids.filtered(lambda l: l.display_type == 'payment_term')
        self.assertTrue(receivable)
        for line in receivable:
            self.assertAlmostEqual(line.amount_residual, 0.0, places=2, msg=line.name)
        payments = self.env['account.payment'].search([('pos_session_id', '=', session.id)])
        self.assertTrue(all(payment.state != 'draft' and payment.move_id.state == 'posted' for payment in payments))

    def test_cash_to_bank_propagates_to_following_session(self):
        session_a = self._run_session(100, [(self.cash_pm1, 70), (self.bank_pm1, 28)])
        self.assertEqual(session_a.cash_register_balance_end_real, 170)
        session_b = self._run_session(170, [(self.cash_pm1, 10)])
        self.assertEqual(session_b.cash_register_balance_start, 170)
        self.assertEqual(session_b.cash_register_balance_end_real, 180)

        payment = session_a.order_ids.payment_ids.filtered(lambda p: p.payment_method_id == self.cash_pm1)
        self._correct(payment, self.bank_pm1)

        self.assertEqual(payment.payment_method_id, self.bank_pm1)
        self.assertEqual(session_a.cash_register_balance_end_real, 100)
        self.assertEqual(session_a.cash_register_balance_end, 100)
        self.assertAlmostEqual(session_a.cash_register_difference, 0.0)
        self.assertEqual(session_b.cash_register_balance_start, 100)
        self.assertEqual(session_b.cash_register_balance_end_real, 110)
        self.assertAlmostEqual(session_b.cash_register_difference, 0.0)
        self.assertFalse(session_a.statement_line_ids)
        self._assert_session_accounting_consistent(session_a)
        self._assert_session_accounting_consistent(session_b)
        bank_line = session_a.move_id.line_ids.filtered(lambda l: l.display_type == 'payment_term' and l.name.endswith(self.bank_pm1.name))
        self.assertAlmostEqual(sum(bank_line.mapped('balance')), 98.0, places=2)

    def test_cash_to_bank_creates_missing_bank_line(self):
        session_a = self._run_session(100, [(self.cash_pm1, 70)])
        session_b = self._run_session(170, [(self.cash_pm1, 5)])
        payment = session_a.order_ids.payment_ids
        wizard = self.env['pos.payment.method.change'].create({
            'payment_id': payment.id,
            'new_payment_method_id': self.bank_pm1.id,
        })
        wizard._onchange_new_payment_method_id()
        self.assertEqual(wizard.cash_impact, -70)
        self.assertEqual(wizard.line_ids.session_id, session_b)
        self.assertEqual(wizard.line_ids.start_after, 100)
        wizard.action_apply()

        self.assertEqual(session_a.cash_register_balance_end_real, 100)
        self.assertEqual(session_b.cash_register_balance_start, 100)
        self.assertEqual(session_b.cash_register_balance_end_real, 105)
        self._assert_session_accounting_consistent(session_a)
        self.assertFalse(session_a.statement_line_ids)
        bank_line = session_a.move_id.line_ids.filtered(lambda l: l.display_type == 'payment_term' and l.name.endswith(self.bank_pm1.name))
        self.assertAlmostEqual(sum(bank_line.mapped('balance')), 70.0, places=2)

    def test_correction_after_payment_method_renamed(self):
        session = self._run_session(100, [(self.cash_pm1, 36)])
        self.cash_pm1.name = 'Espèce renamed'
        payment = session.order_ids.payment_ids
        self._correct(payment, self.bank_pm1)
        self.assertEqual(payment.payment_method_id, self.bank_pm1)
        self.assertEqual(session.cash_register_balance_end_real, 100)
        self._assert_session_accounting_consistent(session)

    def test_line_session_is_not_readonly(self):
        fields_info = self.env['pos.payment.method.change.line'].fields_get(['session_id'])
        self.assertFalse(fields_info['session_id']['readonly'])

    def test_bank_to_cash_in_closed_session(self):
        session = self._run_session(50, [(self.bank_pm1, 40)])
        self.assertEqual(session.cash_register_balance_end_real, 50)

        payment = session.order_ids.payment_ids
        self._correct(payment, self.cash_pm1)

        self.assertEqual(payment.payment_method_id, self.cash_pm1)
        self.assertEqual(session.cash_register_balance_end_real, 90)
        self.assertEqual(session.cash_register_balance_end, 90)
        self.assertEqual(session.statement_line_ids.mapped('amount'), [40.0])
        self._assert_session_accounting_consistent(session)
