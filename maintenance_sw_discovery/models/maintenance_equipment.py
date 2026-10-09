from odoo import fields, models


def create_discovery_key_index(cr, table):
    """Unique discovery key when set (several records may have none)."""
    cr.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {table}_discovery_key_uniq "
        f"ON {table} (discovery_key) WHERE discovery_key IS NOT NULL"
    )


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    discovery_key = fields.Char(
        copy=False,
        help="Identity of the equipment in the discovery files (e.g. machine:<machine-id>, "
        "container:<machine-id>:<name>): a new discovery updates it instead of creating another.",
    )
    discovery_hostname = fields.Char(
        readonly=True, copy=False,
        help="Host name of the server at its last discovery (operating system of a discovered "
        "tree): a file with the same identity but another host name (e.g. a cloned virtual "
        "machine sharing its machine-id) is refused unless confirmed as the same server.",
    )
    last_discovery = fields.Datetime(
        readonly=True, copy=False, help="Collection time of the last discovery that saw it."
    )
    missing_since_discovery = fields.Boolean(
        copy=False,
        help="Absent from the last discovery of its server: archived until it shows up again.",
    )

    def init(self):
        super().init()
        create_discovery_key_index(self.env.cr, self._table)
