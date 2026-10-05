from odoo import Command, api, fields, models


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    docker_image_id = fields.Many2one("docker.image", ondelete="restrict", tracking=True)
    container_name = fields.Char(help="e.g. myc_odoo-v18_1")
    mount_ids = fields.One2many("docker.mount", "equipment_id", string="Mounts")
    effective_component_ids = fields.Many2many(
        "docker.component",
        compute="_compute_effective_component_ids",
        string="Effective Components",
        help="What really runs in the container: the components of the image chain, then the "
        "mounts, which add components or override image ones.",
    )
    runtime_changes = fields.Text(
        help="Changes made inside the running container, outside the image and the declared "
        "mounts (e.g. a symlink added by hand). They are lost when the container is recreated.",
    )
    software_version_id = fields.Many2one(
        "software.version",
        compute="_compute_software_version_id",
        store=True,
        readonly=False,
    )

    @api.depends("docker_image_id.version_id")
    def _compute_software_version_id(self):
        for equipment in self:
            image_version = equipment.docker_image_id.version_id
            if image_version:
                equipment.software_version_id = image_version
            else:
                equipment.software_version_id = equipment.software_version_id

    @api.depends("docker_image_id.version_id")
    def _compute_software_product_id(self):
        # The product of an image version is taken from the image, without reading
        # software_version_id: when the product is computed first, reading it computes the
        # version, whose constraint is then checked against a product not yet assigned.
        with_image_version = self.filtered(lambda equipment: equipment.docker_image_id.version_id)
        for equipment in with_image_version:
            equipment.software_product_id = equipment.docker_image_id.version_id.product_id
        super(MaintenanceEquipment, self - with_image_version)._compute_software_product_id()

    @api.depends(
        "docker_image_id.parent_id",
        "docker_image_id.component_ids",
        "mount_ids.component_ids.overrides_id",
    )
    def _compute_effective_component_ids(self):
        for equipment in self:
            by_key = {}
            if equipment.docker_image_id:
                for image in equipment.docker_image_id._image_chain():
                    for component in image.component_ids:
                        by_key[component._effective_key()] = component
            for component in equipment.mount_ids.component_ids:
                if component.overrides_id:
                    by_key.pop(component.overrides_id._effective_key(), None)
                by_key[("mount", component.id)] = component
            equipment.effective_component_ids = [
                Command.set([component.id for component in by_key.values()])
            ]
