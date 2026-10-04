from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DockerImage(models.Model):
    _name = "docker.image"
    _description = "Docker Image"
    _order = "repository, build_date desc, id desc"

    registry = fields.Char(default="docker.io")
    repository = fields.Char(required=True, help="e.g. tecnativa/odoo")
    tag = fields.Char()
    digest = fields.Char(help="sha256:... — one record per digest: a tag moves, a digest does not.")
    build_date = fields.Datetime()
    parent_id = fields.Many2one(
        "docker.image", string="Base Image", ondelete="restrict", index=True,
        help="The image this one is built FROM.",
    )
    product_id = fields.Many2one(
        "software.product",
        string="Software",
        ondelete="restrict",
        compute="_compute_product_id",
        store=True,
        readonly=False,
    )
    version_id = fields.Many2one(
        "software.version",
        string="Version",
        ondelete="restrict",
        domain="[('product_id', '=?', product_id)]",
    )
    component_ids = fields.One2many("docker.component", "image_id", string="Components")
    container_ids = fields.One2many("maintenance.equipment", "docker_image_id", string="Containers")
    container_count = fields.Integer(compute="_compute_container_count")
    duplicate_warning = fields.Char(compute="_compute_duplicate_warning")
    note = fields.Html()

    _sql_constraints = [
        (
            "repository_digest_uniq",
            "unique(repository, digest)",
            "An image with this digest is already recorded for this repository.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._normalize_digest(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._normalize_digest(vals))

    @api.model
    def _normalize_digest(self, vals):
        """A blank digest is no digest: '' would collide in the unique constraint."""
        if "digest" in vals:
            vals = dict(vals, digest=(vals["digest"] or "").strip() or False)
        return vals

    @api.depends("repository", "tag", "digest")
    def _compute_display_name(self):
        for image in self:
            name = image.repository or ""
            if image.tag:
                name += f":{image.tag}"
            if image.digest:
                name += f" ({image.digest.split(':')[-1][:12]})"
            image.display_name = name

    @api.depends("version_id")
    def _compute_product_id(self):
        for image in self:
            if image.version_id:
                image.product_id = image.version_id.product_id
            else:
                image.product_id = image.product_id

    @api.depends("container_ids")
    def _compute_container_count(self):
        for image in self:
            image.container_count = len(image.container_ids)

    @api.depends("repository", "tag", "digest")
    def _compute_duplicate_warning(self):
        for image in self:
            warning = False
            if image.repository and not image.digest:
                domain = [
                    ("repository", "=", image.repository),
                    ("tag", "=", image.tag or False),
                    ("digest", "=", False),
                ]
                if image._origin.id:
                    domain.append(("id", "!=", image._origin.id))
                if self.search_count(domain):
                    warning = _(
                        "Another image %(repository)s:%(tag)s has no digest either: "
                        "it may be the same image recorded twice.",
                        repository=image.repository,
                        tag=image.tag or "",
                    )
            image.duplicate_warning = warning

    @api.constrains("parent_id")
    def _check_parent_cycle(self):
        if self._has_cycle("parent_id"):
            raise ValidationError(_("An image cannot be built from itself."))

    @api.constrains("product_id", "version_id")
    def _check_version_product(self):
        for image in self:
            if image.version_id and image.version_id.product_id != image.product_id:
                raise ValidationError(
                    _(
                        "Version %(version)s does not belong to %(product)s.",
                        version=image.version_id.display_name,
                        product=image.product_id.display_name or _("no software"),
                    )
                )

    def _image_chain(self):
        """This image and the images it is built from, the most distant ancestor first."""
        self.ensure_one()
        chain = self.browse()
        image = self
        while image and image not in chain:
            chain = image | chain
            image = image.parent_id
        return chain

    def action_view_containers(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Containers"),
            "res_model": "maintenance.equipment",
            "view_mode": "list,form",
            "domain": [("docker_image_id", "=", self.id)],
            "context": {
                "default_equipment_kind": "software",
                "default_install_type": "docker_container",
                "default_docker_image_id": self.id,
            },
        }
