from odoo.tests import TransactionCase


class TestShippedData(TransactionCase):
    def test_deployment_methods(self):
        ref = self.env.ref
        self.assertTrue(ref("maintenance_sw_base.deployment_method_odoo_online").managed_by_provider)
        self.assertTrue(ref("maintenance_sw_base.deployment_method_odoo_sh").managed_by_provider)
        for xmlid in ("myc", "cloudron", "manual"):
            method = ref(f"maintenance_sw_base.deployment_method_{xmlid}")
            self.assertFalse(method.managed_by_provider)

    def test_equipment_form_has_software_page(self):
        arch = self.env["maintenance.equipment"].get_view(view_type="form")["arch"]
        self.assertIn('name="software"', arch)
        self.assertIn('name="equipment_kind"', arch)

    def test_deployment_method_search_view_reaches_archived(self):
        arch = self.env["software.deployment.method"].get_view(view_type="search")["arch"]
        self.assertIn('name="name"', arch)
        self.assertIn("('active', '=', False)", arch)
