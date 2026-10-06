from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from odoo.tools import mute_logger


class TestHostDomain(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Host = cls.env["maintenance.host"]
        cls.Domain = cls.env["maintenance.domain"]
        cls.alwaysdata = cls.env["res.partner"].create({"name": "Alwaysdata", "is_company": True})

    def test_host_defaults(self):
        host = self.Host.create({"name": "Tardis"})
        self.assertEqual(host.host_type, "other")
        self.assertTrue(host.active)

    def test_host_name_search_by_provider(self):
        host = self.Host.create({"name": "web-1", "provider_id": self.alwaysdata.id})
        self.assertIn(host.id, [row[0] for row in self.Host.name_search("Alwaysdata")])
        self.assertFalse(self.Host.name_search("zzz-no-such-host"))

    def test_domain_name_normalized(self):
        domain = self.Domain.create({"name": "  Example.FR. "})
        self.assertEqual(domain.name, "example.fr")
        domain.write({"name": "Other.Example.fr."})
        self.assertEqual(domain.name, "other.example.fr")

    def test_domain_name_unique_after_normalization(self):
        self.Domain.create({"name": "example.fr"})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self.Domain.create({"name": "EXAMPLE.fr."})

    def test_domain_name_cannot_be_blank(self):
        with self.assertRaises(ValidationError):
            self.Domain.create({"name": " . "})

    def test_domain_name_cannot_contain_space(self):
        with self.assertRaises(ValidationError):
            self.Domain.create({"name": "exa mple.fr"})
