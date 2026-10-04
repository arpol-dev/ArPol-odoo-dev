from odoo import fields, models


class DockerComponent(models.Model):
    _name = "docker.component"
    _description = "Docker Component"

    image_id = fields.Many2one("docker.image", ondelete="cascade", index=True)
    mount_id = fields.Many2one("docker.mount", ondelete="cascade", index=True)
    repository_id = fields.Many2one("git.repository", required=True, ondelete="restrict")
