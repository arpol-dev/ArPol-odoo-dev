from odoo.tests import TransactionCase


class TestDockerViews(TransactionCase):
    def test_equipment_form_has_docker_page(self):
        arch = self.env["maintenance.equipment"].get_view(view_type="form")["arch"]
        self.assertIn('name="docker"', arch)
        self.assertIn('name="effective_component_ids"', arch)

    def test_image_form_has_chain_page(self):
        arch = self.env["docker.image"].get_view(view_type="form")["arch"]
        self.assertIn('name="chain_ids"', arch)

    def test_mount_form_restricts_override_target(self):
        arch = self.env["docker.mount"].get_view(view_type="form")["arch"]
        self.assertIn('name="image_component_ids"', arch)
        self.assertIn("parent.image_component_ids", arch)

    def test_menus(self):
        self.assertEqual(
            self.env.ref("maintenance_sw_docker.menu_docker_image").parent_id,
            self.env.ref("maintenance_sw_base.menu_sw_config"),
        )
