from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

COMPONENT_ROLES = [
    ("core", "Core"),
    ("enterprise", "Enterprise"),
    ("oca", "OCA"),
    ("custom", "Custom"),
    ("third_party", "Third Party"),
]


class DockerComponent(models.Model):
    _name = "docker.component"
    _description = "Docker Component"
    _order = "path, id"

    image_id = fields.Many2one("docker.image", string="Image", ondelete="cascade", index=True)
    mount_id = fields.Many2one("docker.mount", string="Mount", ondelete="cascade", index=True)
    repository_id = fields.Many2one(
        "git.repository", string="Repository", required=True, ondelete="restrict"
    )
    path = fields.Char(help="Path inside the container, e.g. /opt/odoo/custom/src/server-ux")
    ref = fields.Char("Branch / Tag")
    commit = fields.Char()
    role = fields.Selection(COMPONENT_ROLES)
    merges = fields.Text(help="Pull requests or branches merged on top of the reference.")
    overrides_id = fields.Many2one(
        "docker.component",
        string="Overrides",
        ondelete="set null",
        domain="[('image_id', '!=', False)]",
        help="Image component this mount component replaces in the running container.",
    )

    @api.depends("repository_id.name", "ref", "commit")
    def _compute_display_name(self):
        for component in self:
            name = component.repository_id.name or ""
            if component.ref:
                name += f"@{component.ref}"
            if component.commit:
                name += f" ({component.commit[:8]})"
            component.display_name = name

    # repository_id is listed so that the check also runs on a create that sets
    # neither image_id nor mount_id (constraints only run for the fields written).
    @api.constrains("image_id", "mount_id", "repository_id")
    def _check_single_owner(self):
        for component in self:
            if bool(component.image_id) == bool(component.mount_id):
                raise ValidationError(
                    _("A component belongs either to an image or to a mount: exactly one of them.")
                )

    @api.constrains("overrides_id", "mount_id")
    def _check_overrides(self):
        for component in self.filtered("overrides_id"):
            if not component.mount_id:
                raise ValidationError(
                    _("Only a component brought by a mount can override another one.")
                )
            if not component.overrides_id.image_id:
                raise ValidationError(
                    _("A mount component can only override a component of an image.")
                )

    def _effective_key(self):
        """Identity of the component in a container: its path, or its repository if no path."""
        self.ensure_one()
        path = (self.path or "").strip()
        if path:
            return ("path", path)
        return ("repository", self.repository_id.id)
