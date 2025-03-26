from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)

class ResUsers(models.Model):
    _inherit = 'res.users'

    def remove_unregistered_users(self, after_days=2):
        datetime_limit = fields.Datetime.today() - relativedelta(days=after_days)

        unlogged_users = self.search([
            ('share', '=', True),
            ('create_date', '<', datetime_limit),
            ('state', '=', 'new'),
            ('log_ids', '=', False),
        ])

        for user in unlogged_users:
            partner = user.partner_id
            has_loyalty_card = self.env['loyalty.card'].search([('partner_id', '=', partner.id)])
            has_sale_order = self.env['sale.order'].search([('partner_id', '=', partner.id)])
            has_purchase_order = self.env['purchase.order'].search([('partner_id', '=', partner.id)])
            has_invoice = self.env['account.move'].search([('partner_id', '=', partner.id)])
            has_stock_picking = self.env['stock.picking'].search([('partner_id', '=', partner.id)])

            if not has_loyalty_card and not has_sale_order and not has_invoice and not has_purchase_order and not has_stock_picking:
                _logger.info('User %s has been removed after 10 days witouh mail confirmation' % user.name)
                user.unlink()
                partner.unlink()