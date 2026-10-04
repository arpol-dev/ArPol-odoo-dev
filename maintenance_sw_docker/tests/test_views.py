from odoo.tests import TransactionCase


class TestDockerViews(TransactionCase):
    def test_equipment_form_has_docker_page(self):
        arch = self.env["maintenance.equipment"].get_view(view_type="form")["arch"]
        self.assertIn('name="docker"', arch)
        self.assertIn('name="effective_component_ids"', arch)

    def test_menus(self):
        self.assertEqual(
            self.env.ref("maintenance_sw_docker.menu_docker_image").parent_id,
            self.env.ref("maintenance_sw_base.menu_sw_config"),
        )
