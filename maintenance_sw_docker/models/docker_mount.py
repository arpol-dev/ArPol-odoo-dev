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
    _rec_names_search = ["source", "destination"]

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
    image_component_ids = fields.Many2many(
        "docker.component",
        compute="_compute_image_component_ids",
        string="Image Components",
        help="Components of the container's image and of the images it is built from: "
        "the only ones a component of this mount can override.",
    )

    @api.depends("source", "destination")
    def _compute_display_name(self):
        for mount in self:
            mount.display_name = f"{mount.source or ''} → {mount.destination or ''}"

    @api.depends(
        "equipment_id.docker_image_id.parent_id",
        "equipment_id.docker_image_id.component_ids",
    )
    def _compute_image_component_ids(self):
        for mount in self:
            image = mount.equipment_id.docker_image_id
            mount.image_component_ids = image._image_chain().component_ids if image else False
