from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    maintenance_domain_ids = fields.Many2many(
        "maintenance.domain",
        compute="_compute_maintenance_domain_ids",
        string="Domain Names",
        groups="maintenance.group_equipment_manager",
    )
    maintenance_domain_count = fields.Integer(
        compute="_compute_maintenance_domain_ids",
        groups="maintenance.group_equipment_manager",
    )

    maintenance_host_ids = fields.Many2many(
        "maintenance.host",
        compute="_compute_maintenance_host_ids",
        string="Physical Hosts",
        groups="maintenance.group_equipment_manager",
    )
    maintenance_host_count = fields.Integer(
        compute="_compute_maintenance_host_ids",
        groups="maintenance.group_equipment_manager",
    )

    def _maintenance_domain_domain(self):
        """Domains owned by the commercial partner, or served by its equipment."""
        self.ensure_one()
        commercial_id = self.commercial_partner_id._origin.id
        if not commercial_id:
            return [("id", "=", False)]
        return [
            "|",
            ("partner_id.commercial_partner_id", "=", commercial_id),
            ("equipment_ids.customer_id.commercial_partner_id", "=", commercial_id),
        ]

    def _compute_maintenance_domain_ids(self):
        Domain = self.env["maintenance.domain"]
        for partner in self:
            domains = Domain.search(partner._maintenance_domain_domain())
            partner.maintenance_domain_ids = domains
            partner.maintenance_domain_count = len(domains)

    def action_view_maintenance_domains(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Domain Names"),
            "res_model": "maintenance.domain",
            "view_mode": "list,form",
            "domain": self._maintenance_domain_domain(),
            "context": {"default_partner_id": self.commercial_partner_id.id},
        }

    def _maintenance_host_domain(self):
        """Hosts carrying equipment of the commercial partner."""
        self.ensure_one()
        commercial_id = self.commercial_partner_id._origin.id
        if not commercial_id:
            return [("id", "=", False)]
        return [("software_ids.customer_id.commercial_partner_id", "=", commercial_id)]

    def _compute_maintenance_host_ids(self):
        Host = self.env["maintenance.host"]
        for partner in self:
            hosts = Host.search(partner._maintenance_host_domain())
            partner.maintenance_host_ids = hosts
            partner.maintenance_host_count = len(hosts)

    def action_view_maintenance_hosts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Physical Hosts"),
            "res_model": "maintenance.host",
            "view_mode": "list,form",
            "domain": self._maintenance_host_domain(),
        }
