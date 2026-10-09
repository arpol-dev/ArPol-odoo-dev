import ipaddress

from odoo import models


def _normalize(address):
    """Canonical form of an IP address (so that IPv6 spellings compare equal), None if invalid."""
    try:
        return str(ipaddress.ip_address(str(address).strip().split("/")[0]))
    except ValueError:
        return None


class MaintenanceHost(models.Model):
    _inherit = "maintenance.host"

    def _discovery_find_host(self, ips):
        host = super()._discovery_find_host(ips)
        if host:
            return host
        wanted = {_normalize(ip) for ip in ips or []} - {None}
        if not wanted:
            return host
        # The importer user may have no right on OVH data. The json payload cannot be searched
        # by content portably: the (few) active VPS and dedicated servers are scanned.
        services = self.env["ovh.service"].sudo().search([("kind", "in", ("vps", "dedicated"))])
        for service in services:
            if wanted & self._ovh_service_ips(service):
                linked = service.maintenance_host_ids.filtered("active")[:1]
                if linked:
                    return linked.with_env(self.env)
        return host

    @staticmethod
    def _ovh_service_ips(service):
        """Addresses of an OVH service: VPS "ips" list, dedicated server main address (detail.ip)."""
        payload = service.raw_payload
        if not isinstance(payload, dict):
            return set()
        found = list(payload.get("ips") or [])
        detail = payload.get("detail")
        if isinstance(detail, dict) and detail.get("ip"):
            found.append(detail["ip"])
        return {ip for ip in map(_normalize, found) if ip}
