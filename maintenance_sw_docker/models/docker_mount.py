from odoo import api, fields, models

MOUNT_USAGES = [
    ("repos", "Code Repositories"),
    ("data", "Data"),
    ("config", "Configuration"),
    ("logs", "Logs"),
    ("other", "Other"),
]


class DockerMount(models.Model):
    _name = "docker.mount"
    _description = "Docker Mount"
    _order = "equipment_id, destination, id"

    equipment_id = fields.Many2one(
        "maintenance.equipment", string="Container", required=True, ondelete="cascade", index=True
    )
    mount_type = fields.Selection(
        [("bind", "Bind"), ("volume", "Volume")], string="Type", default="bind", required=True
    )
    source = fields.Char(required=True, help="Host path, or volume name.")
    destination = fields.Char(required=True, help="Path inside the container.")
    mode = fields.Selection(
        [("rw", "Read-write"), ("ro", "Read-only")], default="rw", required=True
    )
    usage = fields.Selection(MOUNT_USAGES, default="other", required=True)
    component_ids = fields.One2many("docker.component", "mount_id", string="Components")

    @api.depends("source", "destination")
    def _compute_display_name(self):
        for mount in self:
            mount.display_name = f"{mount.source or ''} → {mount.destination or ''}"
