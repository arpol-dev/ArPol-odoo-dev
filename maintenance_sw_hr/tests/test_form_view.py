from lxml import etree

from odoo.tests import TransactionCase


class TestHrAssignmentHidden(TransactionCase):
    def test_hr_assignment_fields_hidden_on_software(self):
        view = self.env["maintenance.equipment"].get_view(view_type="form")
        arch = etree.fromstring(view["arch"])
        for name in ("equipment_assign_to", "employee_id", "department_id"):
            nodes = arch.xpath(f"//field[@name='{name}']")
            self.assertTrue(nodes, f"{name} is in the form")
            for node in nodes:
                self.assertIn("equipment_kind == 'software'", node.get("invisible", ""), name)
