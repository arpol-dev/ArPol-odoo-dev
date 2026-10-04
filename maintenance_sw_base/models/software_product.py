from odoo import _, api, fields, models


class SoftwareProduct(models.Model):
    _name = "software.product"
    _description = "Software Product"
    _order = "name"

    name = fields.Char(required=True)
    vendor = fields.Char()
    website = fields.Char()
    changelog_url = fields.Char("Changelog URL")
    version_ids = fields.One2many("software.version", "product_id", string="Versions")
    installation_ids = fields.One2many(
        "maintenance.equipment", "software_product_id", string="Installations"
    )
    installation_count = fields.Integer(compute="_compute_installation_count")
    note = fields.Html()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "A software product with this name already exists."),
    ]

    @api.depends("installation_ids")
    def _compute_installation_count(self):
        for product in self:
            product.installation_count = len(product.installation_ids)

    def action_view_installations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Installations"),
            "res_model": "maintenance.equipment",
            "view_mode": "list,form",
            "domain": [("software_product_id", "=", self.id)],
            "context": {
                "default_equipment_kind": "software",
                "default_software_product_id": self.id,
            },
        }
