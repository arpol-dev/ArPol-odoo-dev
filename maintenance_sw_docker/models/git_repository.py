from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class GitRepository(models.Model):
    _name = "git.repository"
    _description = "Git Repository"
    _order = "name"

    name = fields.Char(required=True, help="e.g. OCA/server-ux")
    url = fields.Char("URL", required=True, help="The URL actually used, mirror included.")
    host = fields.Selection(
        [("github", "GitHub"), ("gitlab", "GitLab"), ("other", "Other")],
        compute="_compute_host",
        store=True,
        readonly=False,
    )
    upstream_id = fields.Many2one(
        "git.repository",
        string="Upstream",
        ondelete="set null",
        help="Official origin of a fork or of a mirror.",
    )
    component_ids = fields.One2many("docker.component", "repository_id", string="Components")
    note = fields.Html()

    _sql_constraints = [
        ("url_uniq", "unique(url)", "A repository with this URL already exists."),
    ]

    @api.depends("url")
    def _compute_host(self):
        for repository in self:
            url = (repository.url or "").lower()
            if "github.com" in url:
                repository.host = "github"
            elif "gitlab" in url:
                repository.host = "gitlab"
            else:
                repository.host = "other"

    @api.constrains("upstream_id")
    def _check_upstream_cycle(self):
        if self._has_cycle("upstream_id"):
            raise ValidationError(_("A repository cannot be its own upstream."))
