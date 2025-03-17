from odoo import http
from odoo.http import request
from odoo.addons.sale.controllers.variant import VariantController

class WebsiteSaleVariantController(VariantController):
    @http.route(
        ["/sale/get_combination_info_pricelist_atributes"],
        type="json",
        auth="public",
        website=True,
    )
    def get_combination_info_pricelist_atributes(self, product_id, **kwargs):
        res = super(WebsiteSaleVariantController, self).get_combination_info_pricelist_atributes(product_id, **kwargs)
        
        pricelist = (
            request.env["website"]
            .get_current_website()
            .get_current_pricelist()
        )
        product = (
            request.env["product.product"]
            .browse(product_id)
            .with_context(pricelist=pricelist.id)
        )
        # Get global parameter for price display on website
        tax_display = request.env['ir.config_parameter'].sudo().get_param('account.show_line_subtotals_tax_selection')

        for item in res[0]:
            tax_data = product.taxes_id.compute_all(item['price'])
            if tax_display == 'tax_excluded':
                item['price'] = tax_data['total_excluded']
            elif tax_display == 'tax_included':
                item['price'] = tax_data['total_included']
            else: 
                raise ValueError('The parameter "Product Price display" is not correctly configured')
            
        return res