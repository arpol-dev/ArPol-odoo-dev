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

# Fields inherited from the parent equipment, with the flag telling they were set by hand.
INHERITED_FIELDS = {"physical_host_id": "physical_host_forced", "customer_id": "customer_forced"}


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
    physical_host_id = fields.Many2one(
        "maintenance.host",
        string="Physical Host",
        ondelete="restrict",
        compute="_compute_physical_host_id",
        store=True,
        readonly=False,
        recursive=True,
        index=True,
        tracking=True,
        help="Inherited from the parent equipment unless set here. Clear it to inherit again.",
    )
    physical_host_forced = fields.Boolean(copy=True)
    customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
        compute="_compute_customer_id",
        store=True,
        readonly=False,
        recursive=True,
        index=True,
        tracking=True,
        help="Inherited from the parent equipment unless set here. Clear it to inherit again.",
    )
    customer_forced = fields.Boolean(copy=True)
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

    @api.depends("parent_id.physical_host_id", "physical_host_forced")
    def _compute_physical_host_id(self):
        self._compute_inherited("physical_host_id")

    @api.depends("parent_id.customer_id", "customer_forced")
    def _compute_customer_id(self):
        self._compute_inherited("customer_id")

    def _compute_inherited(self, fname):
        """Keep a value set on the equipment (flag set), otherwise take the parent's."""
        flag = INHERITED_FIELDS[fname]
        for equipment in self:
            if equipment[flag]:
                equipment[fname] = equipment[fname]
            else:
                equipment[fname] = equipment.parent_id[fname]

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

    @api.model
    def _set_inherited_flags(self, vals, parent_change=False):
        """A value written on an inherited field forces it, an empty one inherits again.

        The flag is derived from the value unless it is given. With ``parent_change`` (write), a
        form saving a new parent sends the recomputed value (the new parent's one) without the
        unchanged flag: that value is the inherited one, not a forced one.
        """
        def to_id(value):
            return value.id if isinstance(value, models.BaseModel) else value

        parent_change = parent_change and "parent_id" in vals
        parent = self.browse(to_id(vals.get("parent_id")) or ())
        for fname, flag in INHERITED_FIELDS.items():
            if fname in vals and flag not in vals:
                value = to_id(vals[fname])
                vals[flag] = bool(value) and not (parent_change and value == parent[fname].id)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._set_inherited_flags(dict(vals)) for vals in vals_list]
        for vals in vals_list:
            for fname, flag in INHERITED_FIELDS.items():
                if not vals.get(flag):
                    # not forced: let the ORM compute it from the parent
                    vals.pop(fname, None)
        return super().create(vals_list)

    def write(self, vals):
        vals = self._set_inherited_flags(dict(vals), parent_change=True)
        res = super().write(vals)
        for fname, flag in INHERITED_FIELDS.items():
            if fname in vals and not vals[flag]:
                # write() protects the written field from recomputation: compute it from the
                # parent now, and make the descendants follow.
                self.env.add_to_compute(self._fields[fname], self)
                self.modified([fname])
        return res

    @api.onchange("physical_host_id")
    def _onchange_physical_host_id(self):
        self._onchange_inherited("physical_host_id")

    @api.onchange("customer_id")
    def _onchange_customer_id(self):
        self._onchange_inherited("customer_id")

    def _onchange_inherited(self, fname):
        """Cleared: show the parent's value again. Set: force it, unless it is the parent's value.

        The onchange also runs when the field is recomputed in the form (new parent): the value
        is then the parent's one, and must stay inherited.
        """
        parent_value = self.parent_id[fname]
        if not self[fname]:
            self[fname] = parent_value
        self[INHERITED_FIELDS[fname]] = self[fname] != parent_value

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
