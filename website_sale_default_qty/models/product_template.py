# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    website_default_qty = fields.Integer(
        string='Default Cart Quantity',
        default=1,
        company_dependent=True,
        help='Default quantity pre-filled in the eCommerce cart quantity selector for this product.',
    )
