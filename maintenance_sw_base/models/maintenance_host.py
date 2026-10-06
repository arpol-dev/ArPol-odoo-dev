from odoo import fields, models

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
