from odoo import _, api, fields, models

HOST_TYPES = [
    ("physical", "Physical Server"),
    ("vps", "VPS"),
    ("vm", "Virtual Machine"),
    ("shared_hosting", "Shared Hosting"),
    ("other", "Other"),
]


class MaintenanceHost(models.Model):
    _name = "maintenance.host"
    _description = "Physical Host"
    _order = "name"
    _rec_names_search = ["name", "provider_id.name"]

    name = fields.Char(required=True)
    host_type = fields.Selection(HOST_TYPES, string="Type", required=True, default="other")
    provider_id = fields.Many2one(
        "res.partner",
        string="Provider",
        help="Hosting company (OVHcloud, Alwaysdata...). Empty for a machine of your own.",
    )
    equipment_id = fields.Many2one(
        "maintenance.equipment",
        string="Hardware Equipment",
        domain="[('equipment_kind', '=', 'hardware')]",
        ondelete="set null",
        help="The hardware equipment, when you maintain the machine yourself.",
    )
    location = fields.Char()
    note = fields.Html()
    active = fields.Boolean(default=True)

    software_ids = fields.One2many(
        "maintenance.equipment", "physical_host_id", string="Software"
    )
    software_count = fields.Integer(compute="_compute_software_count")

    @api.depends("software_ids")
    def _compute_software_count(self):
        for host in self:
            host.software_count = len(host.software_ids)

    def action_view_software(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Software"),
            "res_model": "maintenance.equipment",
            "view_mode": "list,form",
            "domain": [("physical_host_id", "=", self.id)],
            "context": {"default_equipment_kind": "software", "default_host_id": self.id},
        }
