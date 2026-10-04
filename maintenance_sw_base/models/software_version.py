from odoo import _, api, fields, models

CHANNELS = [
    ("stable", "Stable"),
    ("lts", "LTS"),
    ("saas", "SaaS"),
    ("other", "Other"),
]


class SoftwareVersion(models.Model):
    _name = "software.version"
    _description = "Software Version"
    _order = "product_id, sequence desc, id desc"
    _rec_names_search = ["name", "product_id.name"]

    product_id = fields.Many2one(
        "software.product", required=True, ondelete="cascade", index=True
    )
    name = fields.Char(required=True)
    release_date = fields.Date()
    end_of_support_date = fields.Date("End of Support")
    channel = fields.Selection(CHANNELS, default="stable")
    is_latest = fields.Boolean(
        "Latest", help="Latest known version of the product. Only one version per product."
    )
    sequence = fields.Integer(
        default=10,
        help="Orders the versions of a product: the higher, the more recent. "
        "Version names do not sort reliably as text (9 comes after 12).",
    )
    installation_ids = fields.One2many(
        "maintenance.equipment", "software_version_id", string="Installations"
    )
    installation_count = fields.Integer(compute="_compute_installation_count")
    note = fields.Html()

    _sql_constraints = [
        (
            "product_name_uniq",
            "unique(product_id, name)",
            "This version already exists for this software.",
        ),
    ]

    @api.depends("product_id.name", "name")
    def _compute_display_name(self):
        for version in self:
            if version.product_id:
                version.display_name = f"{version.product_id.name} {version.name or ''}".strip()
            else:
                version.display_name = version.name

    @api.depends("installation_ids")
    def _compute_installation_count(self):
        for version in self:
            version.installation_count = len(version.installation_ids)

    @api.model_create_multi
    def create(self, vals_list):
        versions = super().create(vals_list)
        versions.filtered("is_latest")._unset_other_latest()
        return versions

    def write(self, vals):
        res = super().write(vals)
        if vals.get("is_latest") or "product_id" in vals:
            self.filtered("is_latest")._unset_other_latest()
        return res

    def _unset_other_latest(self):
        """Keep a single latest version per product: the last one of self wins."""
        winners = {}
        for version in self:
            winners[version.product_id.id] = version
        for product_id, version in winners.items():
            self.search([
                ("product_id", "=", product_id),
                ("is_latest", "=", True),
                ("id", "!=", version.id),
            ]).write({"is_latest": False})

    def action_view_installations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Installations"),
            "res_model": "maintenance.equipment",
            "view_mode": "list,form",
            "domain": [("software_version_id", "=", self.id)],
            "context": {
                "default_equipment_kind": "software",
                "default_software_version_id": self.id,
            },
        }
