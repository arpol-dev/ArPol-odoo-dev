from odoo import fields, models


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    docker_image_id = fields.Many2one("docker.image", ondelete="restrict", tracking=True)
