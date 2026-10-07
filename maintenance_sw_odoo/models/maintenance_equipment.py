from odoo import api, fields, models


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    odoo_database_ids = fields.One2many(
        "maintenance.odoo.database", "equipment_id", string="Odoo Databases"
    )
    odoo_database_count = fields.Integer(compute="_compute_odoo_database_count")

    @api.depends("odoo_database_ids")
    def _compute_odoo_database_count(self):
        counts = dict(
            self.env["maintenance.odoo.database"]._read_group(
                [("equipment_id", "in", self.ids)], ["equipment_id"], ["__count"]
            )
        )
        for equipment in self:
            equipment.odoo_database_count = counts.get(equipment, 0)

    def action_view_odoo_databases(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Odoo Databases"),
            "res_model": "maintenance.odoo.database",
            "view_mode": "list,form",
            "domain": [("equipment_id", "=", self.id)],
            "context": {"default_equipment_id": self.id},
        }
