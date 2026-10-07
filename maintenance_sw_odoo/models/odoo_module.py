from odoo import fields, models


class MaintenanceOdooModule(models.Model):
    _name = "maintenance.odoo.module"
    _description = "Odoo Module"
    _order = "name"

    database_id = fields.Many2one(
        "maintenance.odoo.database", string="Database", required=True, ondelete="cascade", index=True
    )
    name = fields.Char(required=True)
    installed_version = fields.Char()
    state = fields.Selection(
        [("installed", "Installed"), ("to_upgrade", "To Upgrade"), ("to_remove", "To Remove")],
        default="installed",
        required=True,
    )
    component_id = fields.Many2one(
        "docker.component",
        string="Provided By",
        ondelete="set null",
        help="The docker component (git repository in the container) that provides this module.",
    )
    repository_id = fields.Many2one(
        "git.repository", related="component_id.repository_id", store=True, string="Repository"
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "database_name_uniq",
            "unique(database_id, name)",
            "This module is already registered for this database.",
        ),
    ]
