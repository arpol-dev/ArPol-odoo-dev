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

    def test_equipment_form_shows_host_customer_domains(self):
        arch = self.env["maintenance.equipment"].get_view(view_type="form")["arch"]
        for field in ("physical_host_id", "host_id", "effective_customer_id", "customer_id", "domain_ids"):
            self.assertIn(f'name="{field}"', arch)

    def test_host_and_domain_menus(self):
        parent = self.env.ref("maintenance_sw_base.menu_sw_config")
        self.assertEqual(self.env.ref("maintenance_sw_base.menu_maintenance_host").parent_id, parent)
        self.assertEqual(self.env.ref("maintenance_sw_base.menu_maintenance_domain").parent_id, parent)
