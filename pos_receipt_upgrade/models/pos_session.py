# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models, _
import logging


class PosSession(models.Model):
    _inherit = "pos.session"

    def _loader_params_res_company(self):
        res = super()._loader_params_res_company()
        
        res['search_params']['fields'].extend(['siret','street','zip','city'])
        logging.error("################### %s" % res)
        return res
    
    def _get_pos_ui_res_company(self,params):
        logging.error("Surcharge")
        return super()._get_pos_ui_res_company(params)