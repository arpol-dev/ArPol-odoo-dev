from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestSoftwareEquipment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Equipment = cls.env["maintenance.equipment"]
        Method = cls.env["software.deployment.method"]
        cls.method_0k = Method.create({"name": "0k test"})
        cls.method_saas = Method.create({"name": "SaaS test", "managed_by_provider": True})
        cls.debian = cls.env["software.product"].create({"name": "Debian test"})
        cls.odoo = cls.env["software.product"].create({"name": "Odoo test"})
        cls.debian12 = cls.env["software.version"].create(
            {"product_id": cls.debian.id, "name": "12"}
        )
        cls.vps = cls.Equipment.create({"name": "vps-test"})

    def _software(self, **values):
        return self.Equipment.create({"name": "sw", "equipment_kind": "software", **values})

    def test_default_kind_is_hardware(self):
        self.assertEqual(self.vps.equipment_kind, "hardware")
        self.assertFalse(self.vps.needs_attachment)

    def test_software_without_parent_needs_attachment(self):
        self.assertTrue(self._software(deployment_method_id=self.method_0k.id).needs_attachment)

    def test_software_without_method_needs_attachment(self):
        self.assertTrue(self._software().needs_attachment)

    def test_software_with_parent_does_not_need_attachment(self):
        software = self._software(parent_id=self.vps.id, deployment_method_id=self.method_0k.id)
        self.assertFalse(software.needs_attachment)

    def test_saas_without_parent_does_not_need_attachment(self):
        software = self._software(install_type="saas", deployment_method_id=self.method_saas.id)
        self.assertFalse(software.needs_attachment)

    def test_needs_attachment_recomputed_when_parent_set(self):
        software = self._software(deployment_method_id=self.method_0k.id)
        software.parent_id = self.vps
        self.assertFalse(software.needs_attachment)

    def test_needs_attachment_follows_method_flag(self):
        software = self._software(deployment_method_id=self.method_0k.id)
        self.method_0k.managed_by_provider = True
        self.assertFalse(software.needs_attachment)

    def test_needs_attachment_filter(self):
        software = self._software()
        self.assertIn(software, self.Equipment.search([("needs_attachment", "=", True)]))
        self.assertNotIn(self.vps, self.Equipment.search([("needs_attachment", "=", True)]))

    def test_version_sets_product(self):
        software = self._software(software_version_id=self.debian12.id)
        self.assertEqual(software.software_product_id, self.debian)

    def test_product_without_version_is_kept(self):
        software = self._software(software_product_id=self.odoo.id)
        self.assertEqual(software.software_product_id, self.odoo)
        self.assertFalse(software.software_version_id)

    def test_version_of_other_product_rejected(self):
        software = self._software(software_version_id=self.debian12.id)
        with self.assertRaises(ValidationError):
            software.software_product_id = self.odoo

    def test_mismatch_on_create_rejected(self):
        with self.assertRaises(ValidationError):
            self._software(
                software_product_id=self.odoo.id, software_version_id=self.debian12.id
            )

    def test_catalog_installation_counts(self):
        software = self._software(
            software_version_id=self.debian12.id, deployment_method_id=self.method_0k.id
        )
        self.env.invalidate_all()  # counts are non-stored computes over one2many caches
        self.assertEqual(self.debian.installation_count, 1)
        self.assertEqual(self.debian12.installation_count, 1)
        self.assertEqual(self.method_0k.installation_count, 1)
        action = self.debian12.action_view_installations()
        self.assertEqual(self.Equipment.search(action["domain"]), software)
