from odoo import _, fields, models

# OVH families that are a machine (or a shared hosting) software can run on.
HOST_TYPES = {
    "dedicated": "physical",
    "vps": "vps",
    "hosting": "shared_hosting",
}


class OvhService(models.Model):
    _inherit = "ovh.service"

    maintenance_host_ids = fields.One2many(
        "maintenance.host", "ovh_service_id", string="Physical Hosts"
    )
    maintenance_domain_ids = fields.One2many(
        "maintenance.domain", "ovh_service_id", string="Domain Names"
    )
    maintenance_link_count = fields.Integer(compute="_compute_maintenance_link_count")

    def _compute_maintenance_link_count(self):
        for service in self:
            service.maintenance_link_count = len(service.maintenance_host_ids) + len(
                service.maintenance_domain_ids
            )

    def _upsert(self, account, kind, service_name, payload):
        service, is_new = super()._upsert(account, kind, service_name, payload)
        service._sync_maintenance_link()
        return service, is_new

    def write(self, vals):
        res = super().write(vals)
        if "active" in vals:
            self._sync_maintenance_active()
        return res

    # The links are a consequence of the synchronization, which an OVH operator
    # may run without any right on the maintenance inventory: they are written
    # as superuser.
    def _sync_maintenance_link(self):
        ovhcloud = self.env.ref("maintenance_hosting_ovh.partner_ovhcloud")
        for service in self.sudo():
            if service.kind in HOST_TYPES:
                service._sync_maintenance_host(ovhcloud)
            elif service.kind == "domain":
                service._sync_maintenance_domain(ovhcloud)

    def _sync_maintenance_host(self, ovhcloud):
        self.ensure_one()
        Host = self.env["maintenance.host"].sudo().with_context(active_test=False)
        host = Host.search([("ovh_service_id", "=", self.id)], limit=1)
        if host:
            if host.active != self.active:
                host.active = self.active
            return host
        return Host.create({
            "name": self.display_name_ovh or self.service_name,
            "host_type": HOST_TYPES[self.kind],
            "provider_id": ovhcloud.id,
            "ovh_service_id": self.id,
            "active": self.active,
        })

    def _sync_maintenance_domain(self, ovhcloud):
        self.ensure_one()
        Domain = self.env["maintenance.domain"].sudo().with_context(active_test=False)
        domain = Domain.search([("ovh_service_id", "=", self.id)], limit=1)
        if not domain:
            # A domain typed by hand before the sync is the same domain: link it.
            domain = Domain.search(
                [("name", "=", Domain._normalize_name(self.service_name)),
                 ("ovh_service_id", "=", False)],
                limit=1,
            )
        values = {
            "expiration_date": self.expiration_date,
            "auto_renew": self.renew_automatic,
            "active": self.active,
        }
        if domain:
            values["ovh_service_id"] = self.id
            if not domain.registrar_id:
                values["registrar_id"] = ovhcloud.id
            domain.write(values)
        else:
            domain = Domain.create(dict(
                values, name=self.service_name, registrar_id=ovhcloud.id, ovh_service_id=self.id,
            ))
        if not domain.partner_id:
            owner = self._maintenance_owner()
            if owner:
                domain.partner_id = owner
        return domain

    def _maintenance_owner(self):
        """The customer whose OVH account is the administrative contact, if known."""
        self.ensure_one()
        nic = (self.contact_admin or "").strip().lower()
        if not nic:
            return self.env["res.partner"]
        partner = self.env["res.partner"].sudo().search([("ovh_nic_handle", "=", nic)], limit=1)
        return partner.commercial_partner_id

    def _sync_maintenance_active(self):
        for model in ("maintenance.host", "maintenance.domain"):
            records = self.env[model].sudo().with_context(active_test=False).search(
                [("ovh_service_id", "in", self.ids)]
            )
            for record in records:
                if record.active != record.ovh_service_id.active:
                    record.active = record.ovh_service_id.active

    def action_view_maintenance_links(self):
        self.ensure_one()
        if self.maintenance_host_ids:
            records, model = self.maintenance_host_ids, "maintenance.host"
        else:
            records, model = self.maintenance_domain_ids, "maintenance.domain"
        return {
            "type": "ir.actions.act_window",
            "name": _("Maintenance"),
            "res_model": model,
            "view_mode": "form",
            "res_id": records[:1].id,
        }
