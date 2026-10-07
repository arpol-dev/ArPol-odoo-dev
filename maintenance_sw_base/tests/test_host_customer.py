from odoo.tests import Form, TransactionCase


class TestHostCustomer(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Equipment = cls.env["maintenance.equipment"]
        Host = cls.env["maintenance.host"]
        Partner = cls.env["res.partner"]
        cls.h1 = Host.create({"name": "vps-1"})
        cls.h2 = Host.create({"name": "vps-2"})
        cls.h3 = Host.create({"name": "vps-3"})
        cls.c1 = Partner.create({"name": "Customer One", "is_company": True})
        cls.c1_contact = Partner.create({"name": "Jane", "parent_id": cls.c1.id})
        cls.c2 = Partner.create({"name": "Customer Two", "is_company": True})
        cls.os = cls.Equipment.create({
            "name": "Debian", "equipment_kind": "software",
            "physical_host_id": cls.h1.id, "customer_id": cls.c1.id,
        })
        cls.stack = cls.Equipment.create(
            {"name": "Stack", "equipment_kind": "software", "parent_id": cls.os.id}
        )
        cls.container = cls.Equipment.create(
            {"name": "Container", "equipment_kind": "software", "parent_id": cls.stack.id}
        )

    def assertHostCustomer(self, equipment, host, customer):
        self.assertEqual(equipment.physical_host_id, host)
        self.assertEqual(equipment.customer_id, customer)

    def assertForced(self, equipment, host_forced, customer_forced):
        self.assertEqual(equipment.physical_host_forced, host_forced)
        self.assertEqual(equipment.customer_forced, customer_forced)

    def test_single_fields(self):
        fields = self.Equipment._fields
        self.assertNotIn("host_id", fields)
        self.assertNotIn("effective_customer_id", fields)
        for fname in ("physical_host_id", "customer_id"):
            field = fields[fname]
            self.assertTrue(field.compute and field.store and field.recursive, fname)
            self.assertFalse(field.readonly, fname)
            self.assertEqual(
                field.help,
                "Inherited from the parent equipment unless set here. Clear it to inherit again.",
            )
        self.assertEqual(fields["physical_host_id"].string, "Physical Host")
        self.assertEqual(fields["customer_id"].string, "Customer")

    def test_children_inherit_host_and_customer(self):
        self.assertForced(self.os, True, True)
        for equipment in (self.stack, self.container):
            self.assertHostCustomer(equipment, self.h1, self.c1)
            self.assertForced(equipment, False, False)

    def test_create_with_value_forces_without_inherits(self):
        forced = self.Equipment.create({
            "name": "Forced", "parent_id": self.os.id,
            "physical_host_id": self.h2.id, "customer_id": self.c2.id,
        })
        self.assertHostCustomer(forced, self.h2, self.c2)
        self.assertForced(forced, True, True)
        cleared = self.Equipment.create({
            "name": "Cleared", "parent_id": self.os.id,
            "physical_host_id": False, "customer_id": False,
        })
        self.assertHostCustomer(cleared, self.h1, self.c1)
        self.assertForced(cleared, False, False)

    def test_create_with_flag_given_keeps_it(self):
        # what the form sends: the parent's value with the flag cleared
        child = self.Equipment.create({
            "name": "From form", "parent_id": self.os.id,
            "physical_host_id": self.h1.id, "physical_host_forced": False,
        })
        self.assertForced(child, False, False)
        self.os.physical_host_id = self.h2
        self.assertEqual(child.physical_host_id, self.h2)

    def test_forced_value_on_middle_survives_root_change(self):
        self.stack.write({"physical_host_id": self.h2.id, "customer_id": self.c2.id})
        self.assertForced(self.stack, True, True)
        self.assertHostCustomer(self.container, self.h2, self.c2)
        self.os.write({"physical_host_id": self.h3.id, "customer_id": self.c1_contact.id})
        self.assertHostCustomer(self.stack, self.h2, self.c2)
        self.assertHostCustomer(self.container, self.h2, self.c2)
        self.env.invalidate_all()
        self.assertHostCustomer(self.container, self.h2, self.c2)

    def test_root_change_propagates(self):
        self.os.write({"physical_host_id": self.h2.id, "customer_id": self.c2.id})
        for equipment in (self.stack, self.container):
            self.assertHostCustomer(equipment, self.h2, self.c2)
        self.env.invalidate_all()
        for equipment in (self.stack, self.container):
            self.assertHostCustomer(equipment, self.h2, self.c2)
            self.assertForced(equipment, False, False)

    def test_clearing_forced_value_falls_back_to_parent(self):
        self.stack.write({"physical_host_id": self.h2.id, "customer_id": self.c2.id})
        self.stack.write({"physical_host_id": False, "customer_id": False})
        self.assertForced(self.stack, False, False)
        for equipment in (self.stack, self.container):
            self.assertHostCustomer(equipment, self.h1, self.c1)
        self.env.invalidate_all()
        for equipment in (self.stack, self.container):
            self.assertHostCustomer(equipment, self.h1, self.c1)
        # inherited again: follows the root
        self.os.write({"physical_host_id": self.h3.id, "customer_id": self.c2.id})
        for equipment in (self.stack, self.container):
            self.assertHostCustomer(equipment, self.h3, self.c2)

    def test_clearing_by_assignment(self):
        self.stack.physical_host_id = self.h2
        self.stack.physical_host_id = False
        self.assertEqual(self.stack.physical_host_id, self.h1)
        self.assertEqual(self.container.physical_host_id, self.h1)

    def test_write_with_flag_given_keeps_it(self):
        self.stack.write({"physical_host_id": self.h2.id})
        self.stack.write({"physical_host_id": self.h1.id, "physical_host_forced": False})
        self.assertFalse(self.stack.physical_host_forced)
        self.os.physical_host_id = self.h3
        self.assertEqual(self.stack.physical_host_id, self.h3)
        self.assertEqual(self.container.physical_host_id, self.h3)

    def test_form_set_forces_value(self):
        with Form(self.stack) as form:
            form.physical_host_id = self.h2
            form.customer_id = self.c2
            self.assertTrue(form.physical_host_forced)
            self.assertTrue(form.customer_forced)
        self.assertForced(self.stack, True, True)
        self.assertHostCustomer(self.container, self.h2, self.c2)
        self.os.write({"physical_host_id": self.h3.id, "customer_id": self.c1_contact.id})
        self.assertHostCustomer(self.stack, self.h2, self.c2)

    def test_form_clear_shows_parent_value_and_inherits(self):
        self.stack.write({"physical_host_id": self.h2.id, "customer_id": self.c2.id})
        with Form(self.stack) as form:
            form.physical_host_id = self.env["maintenance.host"]
            form.customer_id = self.env["res.partner"]
            self.assertEqual(form.physical_host_id, self.h1)
            self.assertEqual(form.customer_id, self.c1)
            self.assertFalse(form.physical_host_forced)
            self.assertFalse(form.customer_forced)
        self.assertForced(self.stack, False, False)
        self.assertHostCustomer(self.stack, self.h1, self.c1)
        self.assertHostCustomer(self.container, self.h1, self.c1)
        self.os.write({"physical_host_id": self.h3.id, "customer_id": self.c2.id})
        self.assertHostCustomer(self.stack, self.h3, self.c2)
        self.assertHostCustomer(self.container, self.h3, self.c2)

    def test_form_reparenting_does_not_force(self):
        other = self.Equipment.create({
            "name": "Ubuntu", "equipment_kind": "software",
            "physical_host_id": self.h2.id, "customer_id": self.c2.id,
        })
        with Form(self.container) as form:
            form.parent_id = other
            self.assertEqual(form.physical_host_id, self.h2)
            self.assertEqual(form.customer_id, self.c2)
            self.assertFalse(form.physical_host_forced)
            self.assertFalse(form.customer_forced)
        self.assertForced(self.container, False, False)
        other.physical_host_id = self.h3
        self.assertEqual(self.container.physical_host_id, self.h3)

    def test_reparenting_changes_inherited_values_not_forced_ones(self):
        other = self.Equipment.create(
            {"name": "Ubuntu", "equipment_kind": "software", "physical_host_id": self.h2.id}
        )
        self.container.parent_id = other
        self.assertHostCustomer(self.container, self.h2, self.Equipment.customer_id)
        self.stack.physical_host_id = self.h3
        self.stack.parent_id = other
        self.assertHostCustomer(self.stack, self.h3, self.Equipment.customer_id)

    def test_copy_keeps_forced_and_inherited_values(self):
        self.stack.physical_host_id = self.h2
        stack_copy = self.stack.copy()
        self.assertEqual(stack_copy.physical_host_id, self.h2)
        self.assertTrue(stack_copy.physical_host_forced)
        container_copy = self.container.copy()
        self.assertEqual(container_copy.physical_host_id, self.h2)
        self.assertFalse(container_copy.physical_host_forced)

    def test_needs_attachment_inherited_host(self):
        self.assertFalse(self.container.needs_attachment)
        self.os.physical_host_id = False
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

    def test_partner_hosts(self):
        self.Equipment.create({
            "name": "Other", "equipment_kind": "software",
            "physical_host_id": self.h2.id, "customer_id": self.c2.id,
        })
        self.assertEqual(self.c1.maintenance_host_ids, self.h1)
        self.assertEqual(self.c1.maintenance_host_count, 1)
        self.assertEqual(self.c2.maintenance_host_ids, self.h2)
        self.assertNotIn(self.h3, self.c1.maintenance_host_ids | self.c2.maintenance_host_ids)

    def test_partner_hosts_through_company_contact(self):
        self.container.physical_host_id = self.h2
        self.assertEqual(self.c1_contact.maintenance_host_ids, self.h1 | self.h2)
        action = self.c1_contact.action_view_maintenance_hosts()
        self.assertEqual(action["res_model"], "maintenance.host")
        self.assertEqual(self.env["maintenance.host"].search(action["domain"]), self.h1 | self.h2)

    def test_partner_hosts_new_partner(self):
        partner = self.env["res.partner"].new({"name": "Draft"})
        self.assertFalse(partner.maintenance_host_ids)
        self.assertEqual(partner.maintenance_host_count, 0)

    def test_equipment_domain_ids_reverse(self):
        domain = self.env["maintenance.domain"].create({"name": "rev.fr"})
        self.container.domain_ids = [(4, domain.id)]
        self.assertEqual(domain.equipment_ids, self.container)

    def test_host_software_count(self):
        self.env.invalidate_all()
        self.assertEqual(self.h1.software_count, 3)
        action = self.h1.action_view_software()
        self.assertEqual(self.Equipment.search(action["domain"]), self.os | self.stack | self.container)

    def test_host_software_action_creates_forced(self):
        other = self.Equipment.create({"name": "Ubuntu", "physical_host_id": self.h2.id})
        action = self.h1.action_view_software()
        software = self.Equipment.with_context(**action["context"]).create(
            {"name": "New", "parent_id": other.id}
        )
        self.assertEqual(software.physical_host_id, self.h1)
        self.assertTrue(software.physical_host_forced)

    def test_host_software_label_is_plural(self):
        # "Software" alone is the equipment kind (singular "Logiciel" in French).
        self.assertEqual(self.h1.action_view_software()["name"], "Installed Software")
        self.assertEqual(self.env["maintenance.host"]._fields["software_ids"].string, "Installed Software")
