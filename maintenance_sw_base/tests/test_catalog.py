from psycopg2 import IntegrityError

from odoo.tests import TransactionCase
from odoo.tools import mute_logger


class TestSoftwareCatalog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Version = cls.env["software.version"]
        cls.debian = cls.env["software.product"].create({"name": "Debian"})
        cls.odoo = cls.env["software.product"].create({"name": "Odoo"})

    def _version(self, product, name, **values):
        return self.Version.create({"product_id": product.id, "name": name, **values})

    def test_version_display_name(self):
        self.assertEqual(self._version(self.debian, "12").display_name, "Debian 12")

    def test_version_name_unique_per_product(self):
        self._version(self.debian, "12")
        self._version(self.odoo, "12")  # same name, other product: allowed
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self._version(self.debian, "12")

    def test_product_name_unique(self):
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self.env["software.product"].create({"name": "Debian"})

    def test_deployment_method_name_unique(self):
        Method = self.env["software.deployment.method"]
        Method.create({"name": "Cloudron test"})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            Method.create({"name": "Cloudron test"})

    def test_is_latest_single_per_product(self):
        v11 = self._version(self.debian, "11", is_latest=True)
        v12 = self._version(self.debian, "12", is_latest=True)
        o18 = self._version(self.odoo, "18.0", is_latest=True)
        self.assertFalse(v11.is_latest)
        self.assertTrue(v12.is_latest)
        self.assertTrue(o18.is_latest, "another product is not affected")
        v11.is_latest = True
        self.assertFalse(v12.is_latest)

    def test_is_latest_batch_create_keeps_last(self):
        versions = self.Version.create([
            {"product_id": self.debian.id, "name": "11", "is_latest": True},
            {"product_id": self.debian.id, "name": "12", "is_latest": True},
        ])
        self.assertEqual(versions.filtered("is_latest").mapped("name"), ["12"])

    def test_is_latest_batch_write_keeps_last(self):
        v11 = self._version(self.debian, "11")
        v12 = self._version(self.debian, "12")
        (v11 | v12).write({"is_latest": True})
        self.assertEqual((v11 | v12).filtered("is_latest"), v12)

    def test_is_latest_moved_to_other_product(self):
        o18 = self._version(self.odoo, "18.0", is_latest=True)
        moved = self._version(self.debian, "19.0", is_latest=True)
        moved.product_id = self.odoo
        self.assertTrue(moved.is_latest)
        self.assertFalse(o18.is_latest)

    def test_versions_ordered_most_recent_first(self):
        old = self._version(self.debian, "9", sequence=9)
        new = self._version(self.debian, "12", sequence=12)
        self.env.invalidate_all()  # read the one2many from the database, in _order
        self.assertEqual(self.debian.version_ids, new | old)
        self.assertEqual(self.debian.version_ids[0], new)
