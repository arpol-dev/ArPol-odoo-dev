from odoo import fields, models


class MaintenanceHost(models.Model):
    _inherit = "maintenance.host"

    ovh_service_id = fields.Many2one(
        "ovh.service",
        string="OVH Service",
        domain="[('kind', 'in', ('dedicated', 'vps', 'hosting'))]",
        ondelete="set null",
        index=True,
        groups="ovh_api.group_ovh_user",
    )
    ovh_expiration_date = fields.Date(
        related="ovh_service_id.expiration_date",
        string="OVH Expiration",
        groups="ovh_api.group_ovh_user",
    )

    _sql_constraints = [
        (
            "ovh_service_uniq",
            "unique(ovh_service_id)",
            "This OVH service is already linked to a physical host.",
        ),
    ]
