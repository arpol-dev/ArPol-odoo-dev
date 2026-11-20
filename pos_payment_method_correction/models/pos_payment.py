from odoo import _, models
from odoo.exceptions import UserError


class PosPayment(models.Model):
    _inherit = 'pos.payment'

    def action_correct_payment_method(self):
        self.ensure_one()
        if self.session_id.state != 'closed':
            raise UserError(_("Only the payments of a closed session can be corrected."))
        return {
            'name': _("Correct payment method"),
            'type': 'ir.actions.act_window',
            'res_model': 'pos.payment.method.change',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_payment_id': self.id},
        }

    def _change_payment_method(self, new_method):
        """Move the payment to ``new_method`` in the session accounting.

        Returns the change of the theoretical cash balance of the session.
        """
        self.ensure_one()
        old_method = self.payment_method_id
        self.session_id._shift_payment_method_amounts([(old_method, -self.amount), (new_method, self.amount)])
        self.payment_method_id = new_method
        return self.amount * (int(new_method.is_cash_count) - int(old_method.is_cash_count))
