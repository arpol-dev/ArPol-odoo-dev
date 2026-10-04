from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

INSTALL_TYPES = [
    ("os", "Operating System"),
    ("package", "Package"),
    ("docker_container", "Docker Container"),
    ("compose_stack", "Compose Stack"),
    ("git_checkout", "Git Checkout"),
    ("saas", "SaaS"),
    ("manual", "Manual"),
]


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    equipment_kind = fields.Selection(
        [("hardware", "Hardware"), ("software", "Software")],
        string="Kind",
        required=True,
        default="hardware",
        tracking=True,
    )
    install_type = fields.Selection(INSTALL_TYPES, tracking=True)
    deployment_method_id = fields.Many2one(
        "software.deployment.method", ondelete="restrict", tracking=True
    )
    software_product_id = fields.Many2one(
        "software.product",
        string="Software",
        ondelete="restrict",
        compute="_compute_software_product_id",
        store=True,
        readonly=False,
        tracking=True,
    )
    software_version_id = fields.Many2one(
        "software.version",
        string="Version",
        ondelete="restrict",
        domain="[('product_id', '=?', software_product_id)]",
        tracking=True,
    )
    version_note = fields.Char(help="Free-form version, when it is not in the catalog.")
    install_path = fields.Char(help="Where it is installed, e.g. /opt/apps/myc-deploy.")
    needs_attachment = fields.Boolean(
        "To Attach",
        compute="_compute_needs_attachment",
        store=True,
        help="Software with no parent equipment whose deployment method is not managed by "
        "the provider: the server it runs on is missing.",
    )

    @api.depends("software_version_id")
    def _compute_software_product_id(self):
        for equipment in self:
            if equipment.software_version_id:
                equipment.software_product_id = equipment.software_version_id.product_id
            else:
                equipment.software_product_id = equipment.software_product_id

    @api.depends("equipment_kind", "parent_id", "deployment_method_id.managed_by_provider")
    def _compute_needs_attachment(self):
        for equipment in self:
            equipment.needs_attachment = (
                equipment.equipment_kind == "software"
                and not equipment.parent_id
                and not equipment.deployment_method_id.managed_by_provider
            )

    @api.onchange("software_product_id")
    def _onchange_software_product_id(self):
        version = self.software_version_id
        if version and version.product_id != self.software_product_id:
            self.software_version_id = False

    @api.constrains("software_product_id", "software_version_id")
    def _check_software_version_product(self):
        for equipment in self:
            version = equipment.software_version_id
            if version and version.product_id != equipment.software_product_id:
                raise ValidationError(
                    _(
                        "Version %(version)s does not belong to %(product)s.",
                        version=version.display_name,
                        product=equipment.software_product_id.display_name or _("no software"),
                    )
                )
