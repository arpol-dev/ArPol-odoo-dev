from odoo import fields, models


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    deployment_method_id = fields.Many2one(
        "software.deployment.method", ondelete="restrict", tracking=True
    )
    software_product_id = fields.Many2one(
        "software.product", string="Software", ondelete="restrict", tracking=True
    )
    software_version_id = fields.Many2one(
        "software.version", string="Version", ondelete="restrict", tracking=True
    )
