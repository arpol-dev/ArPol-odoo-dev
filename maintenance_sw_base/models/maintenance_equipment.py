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
        string="Software Product",
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
    host_id = fields.Many2one(
        "maintenance.host",
        string="Set Physical Host",
        ondelete="restrict",
        tracking=True,
        help="Physical host of this equipment, when it is not the one of its parent.",
    )
    physical_host_id = fields.Many2one(
        "maintenance.host",
        string="Physical Host",
        compute="_compute_physical_host_id",
        store=True,
        recursive=True,
        index=True,
        help="The set physical host, or else the one of the parent equipment.",
    )
    customer_id = fields.Many2one(
        "res.partner",
        string="Set Customer",
        tracking=True,
        help="Customer of this equipment, when it is not the one of its parent.",
    )
    effective_customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
        compute="_compute_effective_customer_id",
        store=True,
        recursive=True,
        index=True,
        help="The set customer, or else the one of the parent equipment.",
    )
    domain_ids = fields.Many2many(
        "maintenance.domain",
        "maintenance_domain_equipment_rel",
        "equipment_id",
        "domain_id",
        string="Domain Names",
    )
    needs_attachment = fields.Boolean(
        "To Attach",
        compute="_compute_needs_attachment",
        store=True,
        help="Software with no physical host (set on it or on a parent) whose deployment "
        "method is not managed by the provider.",
    )

    @api.depends("software_version_id.product_id")
    def _compute_software_product_id(self):
        for equipment in self:
            if equipment.software_version_id:
                equipment.software_product_id = equipment.software_version_id.product_id
            else:
                equipment.software_product_id = equipment.software_product_id

    @api.depends("host_id", "parent_id.physical_host_id")
    def _compute_physical_host_id(self):
        for equipment in self:
            equipment.physical_host_id = equipment.host_id or equipment.parent_id.physical_host_id

    @api.depends("customer_id", "parent_id.effective_customer_id")
    def _compute_effective_customer_id(self):
        for equipment in self:
            equipment.effective_customer_id = (
                equipment.customer_id or equipment.parent_id.effective_customer_id
            )

    @api.depends(
        "equipment_kind", "physical_host_id", "deployment_method_id.managed_by_provider"
    )
    def _compute_needs_attachment(self):
        for equipment in self:
            equipment.needs_attachment = (
                equipment.equipment_kind == "software"
                and not equipment.physical_host_id
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
