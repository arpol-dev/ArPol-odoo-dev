from odoo import fields, models

DISCOVERED_HELP = (
    "Created or updated by a server discovery: deleted when a later discovery no longer finds "
    "it. What is entered by hand is never deleted by a discovery."
)


class DockerMount(models.Model):
    _inherit = "docker.mount"

    discovered = fields.Boolean(copy=False, help=DISCOVERED_HELP)


class DockerComponent(models.Model):
    _inherit = "docker.component"

    discovered = fields.Boolean(copy=False, help=DISCOVERED_HELP)
