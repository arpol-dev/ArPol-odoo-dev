from odoo import fields, models


class DockerMount(models.Model):
    _name = "docker.mount"
    _description = "Docker Mount"

    equipment_id = fields.Many2one(
        "maintenance.equipment", required=True, ondelete="cascade", index=True
    )
