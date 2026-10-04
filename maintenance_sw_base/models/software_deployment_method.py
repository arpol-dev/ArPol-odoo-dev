from odoo import api, fields, models


class SoftwareDeploymentMethod(models.Model):
    _name = "software.deployment.method"
    _description = "Software Deployment Method"
    _order = "name"

    name = fields.Char(required=True)
    managed_by_provider = fields.Boolean(
        help="The provider runs and updates the software (SaaS): there is no server of ours "
        "to attach it to, and its updates are not ours to plan.",
    )
    update_procedure = fields.Html(help="How to update software deployed this way, known pitfalls.")
    documentation_url = fields.Char("Documentation URL")
    installation_ids = fields.One2many(
        "maintenance.equipment", "deployment_method_id", string="Installations"
    )
    installation_count = fields.Integer(compute="_compute_installation_count")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "A deployment method with this name already exists."),
    ]

    @api.depends("installation_ids")
    def _compute_installation_count(self):
        for method in self:
            method.installation_count = len(method.installation_ids)
