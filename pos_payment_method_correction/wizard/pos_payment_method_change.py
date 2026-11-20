from odoo import Command, _, api, fields, models


class PosPaymentMethodChange(models.TransientModel):
    _name = 'pos.payment.method.change'
    _description = 'Correct the payment method of a POS payment'

    payment_id = fields.Many2one('pos.payment', required=True, readonly=True)
    session_id = fields.Many2one(related='payment_id.session_id')
    currency_id = fields.Many2one(related='session_id.currency_id')
    amount = fields.Monetary(related='payment_id.amount')
    current_payment_method_id = fields.Many2one(related='payment_id.payment_method_id')
    available_payment_method_ids = fields.Many2many('pos.payment.method', compute='_compute_available_payment_method_ids')
    new_payment_method_id = fields.Many2one(
        'pos.payment.method',
        string='New payment method',
        required=True,
        domain="[('id', 'in', available_payment_method_ids), ('id', '!=', current_payment_method_id)]",
    )
    cash_impact = fields.Monetary(
        string='Change of the cash balance',
        compute='_compute_cash_impact',
        help="Amount added to the theoretical closing cash of the session, and to the opening and closing cash of the following sessions of the same point of sale.",
    )
    session_end_before = fields.Monetary(string='Closing cash before', compute='_compute_cash_impact')
    session_end_after = fields.Monetary(string='Closing cash after', compute='_compute_cash_impact')
    line_ids = fields.One2many('pos.payment.method.change.line', 'wizard_id', string='Following sessions')

    @api.depends('payment_id.session_id.config_id.payment_method_ids')
    def _compute_available_payment_method_ids(self):
        for wizard in self:
            wizard.available_payment_method_ids = wizard.session_id.config_id.payment_method_ids

    @api.depends('payment_id', 'new_payment_method_id', 'amount', 'current_payment_method_id')
    def _compute_cash_impact(self):
        for wizard in self:
            impact = 0.0
            if wizard.new_payment_method_id and wizard.current_payment_method_id:
                impact = wizard.amount * (
                    int(wizard.new_payment_method_id.is_cash_count) - int(wizard.current_payment_method_id.is_cash_count)
                )
            wizard.cash_impact = impact
            wizard.session_end_before = wizard.session_id.cash_register_balance_end_real
            wizard.session_end_after = wizard.session_end_before + impact

    @api.onchange('new_payment_method_id')
    def _onchange_new_payment_method_id(self):
        commands = [Command.clear()]
        if self.cash_impact and self.session_id:
            following = self.env['pos.session'].search([
                ('config_id', '=', self.session_id.config_id.id),
                ('id', '>', self.session_id.id),
            ], order='id asc')
            for session in following:
                closed = session.state == 'closed'
                start = session.cash_register_balance_start
                end = session.cash_register_balance_end_real if closed else 0.0
                commands.append(Command.create({
                    'session_id': session.id,
                    'start_before': start,
                    'start_after': start + self.cash_impact,
                    'end_before': end,
                    'end_after': end + self.cash_impact if closed else 0.0,
                }))
        self.line_ids = commands

    def action_apply(self):
        self.ensure_one()
        session = self.session_id.sudo()
        impact = self.payment_id.sudo()._change_payment_method(self.new_payment_method_id)
        if not self.currency_id.is_zero(impact):
            session.cash_register_balance_end_real += impact
        for line in self.line_ids.sorted(lambda l: l.session_id.id):
            vals = {'cash_register_balance_start': line.start_after}
            if line.session_id.state == 'closed':
                vals['cash_register_balance_end_real'] = line.end_after
            line.session_id.sudo().write(vals)
        return {'type': 'ir.actions.act_window_close'}


class PosPaymentMethodChangeLine(models.TransientModel):
    _name = 'pos.payment.method.change.line'
    _description = 'Following session cash balances to correct'

    wizard_id = fields.Many2one('pos.payment.method.change', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    session_id = fields.Many2one('pos.session', string='Session', required=True)
    session_state = fields.Selection(related='session_id.state')
    start_before = fields.Monetary(string='Opening cash before', readonly=True)
    start_after = fields.Monetary(string='Opening cash after', required=True)
    end_before = fields.Monetary(string='Closing cash before', readonly=True)
    end_after = fields.Monetary(string='Closing cash after')
