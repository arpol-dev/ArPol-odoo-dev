from odoo.tests import TransactionCase


class TestHostCustomer(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Equipment = cls.env["maintenance.equipment"]
        Host = cls.env["maintenance.host"]
        Partner = cls.env["res.partner"]
        cls.h1 = Host.create({"name": "vps-1"})
        cls.h2 = Host.create({"name": "vps-2"})
        cls.c1 = Partner.create({"name": "Customer One", "is_company": True})
        cls.c1_contact = Partner.create({"name": "Jane", "parent_id": cls.c1.id})
        cls.c2 = Partner.create({"name": "Customer Two", "is_company": True})
        cls.os = cls.Equipment.create({
            "name": "Debian", "equipment_kind": "software",
            "host_id": cls.h1.id, "customer_id": cls.c1.id,
        })
        cls.stack = cls.Equipment.create(
            {"name": "Stack", "equipment_kind": "software", "parent_id": cls.os.id}
        )
        cls.container = cls.Equipment.create(
            {"name": "Container", "equipment_kind": "software", "parent_id": cls.stack.id}
        )

    def test_children_inherit_host_and_customer(self):
        self.assertEqual(self.container.physical_host_id, self.h1)
        self.assertEqual(self.container.effective_customer_id, self.c1)
        self.assertFalse(self.container.host_id)
        self.assertFalse(self.container.customer_id)

    def test_forced_value_on_child_survives_parent_change(self):
        self.stack.write({"host_id": self.h2.id, "customer_id": self.c2.id})
        h3 = self.env["maintenance.host"].create({"name": "vps-3"})
        self.os.write({"host_id": h3.id, "customer_id": self.c1_contact.id})
        self.assertEqual(self.container.physical_host_id, self.h2)
        self.assertEqual(self.container.effective_customer_id, self.c2)

    def test_parent_change_propagates(self):
        self.os.write({"host_id": self.h2.id, "customer_id": self.c2.id})
        self.assertEqual(self.container.physical_host_id, self.h2)
        self.assertEqual(self.container.effective_customer_id, self.c2)

    def test_reparenting_changes_inherited_values(self):
        other = self.Equipment.create(
            {"name": "Ubuntu", "equipment_kind": "software", "host_id": self.h2.id}
        )
        self.container.parent_id = other
        self.assertEqual(self.container.physical_host_id, self.h2)
        self.assertFalse(self.container.effective_customer_id)

    def test_clearing_forced_value_falls_back_to_parent(self):
        self.stack.host_id = self.h2
        self.stack.host_id = False
        self.assertEqual(self.container.physical_host_id, self.h1)

    def test_needs_attachment_inherited_host(self):
        self.assertFalse(self.container.needs_attachment)
        self.os.host_id = False
        self.assertTrue(self.container.needs_attachment)

    def test_needs_attachment_parent_without_host(self):
        hardware = self.Equipment.create({"name": "Box"})
        software = self.Equipment.create(
            {"name": "App", "equipment_kind": "software", "parent_id": hardware.id}
        )
        self.assertTrue(software.needs_attachment)

    def test_owner_domains(self):
        domain = self.env["maintenance.domain"].create({"name": "one.fr", "partner_id": self.c1.id})
        self.assertIn(domain, self.c1.maintenance_domain_ids)
        self.assertNotIn(domain, self.c2.maintenance_domain_ids)

    def test_domains_through_equipment(self):
        domain = self.env["maintenance.domain"].create(
            {"name": "served.fr", "equipment_ids": [(4, self.container.id)]}
        )
        self.assertIn(domain, self.c1.maintenance_domain_ids)
        self.assertEqual(self.c1.maintenance_domain_count, 1)
        self.assertNotIn(domain, self.c2.maintenance_domain_ids)

    def test_domains_through_company_contact(self):
        owned = self.env["maintenance.domain"].create({"name": "owned.fr", "partner_id": self.c1.id})
        served = self.env["maintenance.domain"].create(
            {"name": "served.fr", "equipment_ids": [(4, self.container.id)]}
        )
        self.assertEqual(self.c1_contact.maintenance_domain_ids, owned | served)
        action = self.c1_contact.action_view_maintenance_domains()
        self.assertEqual(self.env["maintenance.domain"].search(action["domain"]), owned | served)

    def test_equipment_domain_ids_reverse(self):
        domain = self.env["maintenance.domain"].create({"name": "rev.fr"})
        self.container.domain_ids = [(4, domain.id)]
        self.assertEqual(domain.equipment_ids, self.container)

    def test_host_software_count(self):
        self.env.invalidate_all()
        self.assertEqual(self.h1.software_count, 3)
        action = self.h1.action_view_software()
        self.assertEqual(self.Equipment.search(action["domain"]), self.os | self.stack | self.container)

    def test_host_software_label_is_plural(self):
        # "Software" alone is the equipment kind (singular "Logiciel" in French).
        self.assertEqual(self.h1.action_view_software()["name"], "Installed Software")
        self.assertEqual(self.env["maintenance.host"]._fields["software_ids"].string, "Installed Software")
