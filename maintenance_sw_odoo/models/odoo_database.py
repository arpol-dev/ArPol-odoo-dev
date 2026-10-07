from odoo import api, fields, models


class MaintenanceOdooDatabase(models.Model):
    _name = "maintenance.odoo.database"
    _description = "Odoo Database"
    _order = "equipment_id, name"
    _rec_names_search = ["name", "equipment_id.name"]

    name = fields.Char(required=True)
    equipment_id = fields.Many2one(
        "maintenance.equipment", string="Container", required=True, ondelete="cascade", index=True
    )
    module_ids = fields.One2many("maintenance.odoo.module", "database_id", string="Modules")
    module_count = fields.Integer(compute="_compute_module_count")
    last_discovery = fields.Datetime(readonly=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "equipment_name_uniq",
            "unique(equipment_id, name)",
            "This Odoo database is already registered for this container.",
        ),
    ]

    @api.depends("module_ids")
    def _compute_module_count(self):
        counts = dict(
            self.env["maintenance.odoo.module"]._read_group(
                [("database_id", "in", self.ids)], ["database_id"], ["__count"]
            )
        )
        for database in self:
            database.module_count = counts.get(database, 0)

    @api.depends("name", "equipment_id.name")
    def _compute_display_name(self):
        for database in self:
            database.display_name = (
                f"{database.name or ''} ({database.equipment_id.name})"
                if database.equipment_id
                else database.name or ""
            )

    def action_view_modules(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Odoo Modules"),
            "res_model": "maintenance.odoo.module",
            "view_mode": "list,form",
            "domain": [("database_id", "=", self.id)],
            "context": {"default_database_id": self.id},
        }
