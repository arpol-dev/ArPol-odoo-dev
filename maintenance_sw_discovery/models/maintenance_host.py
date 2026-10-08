from odoo import fields, models

from .maintenance_equipment import create_discovery_key_index


class MaintenanceHost(models.Model):
    _inherit = "maintenance.host"

    discovery_key = fields.Char(
        copy=False,
        help="Identity of the host in the discovery files (pve-guest:<machine-id>:<vmid>).",
    )

    def init(self):
        super().init()
        create_discovery_key_index(self.env.cr, self._table)

    def _discovery_find_host(self, ips):
        """Physical host of a discovered server, from its IP addresses.

        Nothing is known here: bridge modules (e.g. with a hosting provider) override it.
        """
        return self.browse()
