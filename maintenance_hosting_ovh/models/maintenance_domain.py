from odoo import api, fields, models


class MaintenanceDomain(models.Model):
    _inherit = "maintenance.domain"

    ovh_service_id = fields.Many2one(
        "ovh.service",
        string="OVH Service",
        ondelete="set null",
        index=True,
        groups="ovh_api.group_ovh_user",
    )
    is_ovh_managed = fields.Boolean(
        "Managed at OVH",
        compute="_compute_is_ovh_managed",
        store=True,
        help="Expiration and renewal come from OVH and are rewritten at each synchronization.",
    )

    _sql_constraints = [
        (
            "ovh_service_uniq",
            "unique(ovh_service_id)",
            "This OVH service is already linked to a domain name.",
        ),
    ]

    @api.depends("ovh_service_id")
    def _compute_is_ovh_managed(self):
        for domain in self.sudo():
            domain.is_ovh_managed = bool(domain.ovh_service_id)
