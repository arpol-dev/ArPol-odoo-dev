# mail_partner_unified_history/tests/test_partner_history.py
from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestPartnerHistory(TransactionCase):

    def test_get_partner_history_enabled_models_empty(self):
        """Sans modèle activé, retourne une liste vide."""
        result = self.env['ir.model'].get_partner_history_enabled_models()
        self.assertIsInstance(result, list)
        # res.partner n'est pas activé par défaut
        self.assertNotIn('res.partner', result)

    def test_get_partner_history_enabled_models_with_enabled(self):
        """Retourne uniquement les modèles avec partner_history_enabled = True."""
        partner_model = self.env['ir.model'].search([('model', '=', 'res.partner')], limit=1)
        partner_model.write({'partner_history_enabled': True})
        result = self.env['ir.model'].get_partner_history_enabled_models()
        self.assertIn('res.partner', result)
        # Nettoyage
        partner_model.write({'partner_history_enabled': False})
