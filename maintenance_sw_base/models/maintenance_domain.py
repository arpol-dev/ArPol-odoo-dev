from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MaintenanceDomain(models.Model):
    _name = "maintenance.domain"
    _description = "Domain Name"
    _order = "name"

    name = fields.Char(required=True, help="Registered domain, e.g. example.fr (no subdomain).")
    registrar_id = fields.Many2one("res.partner", string="Registrar")
    expiration_date = fields.Date()
    auto_renew = fields.Boolean("Automatic Renewal")
    partner_id = fields.Many2one(
        "res.partner",
        string="Owner",
        help="Customer who owns the domain, even when no equipment serves it.",
    )
    equipment_ids = fields.Many2many(
        "maintenance.equipment",
        "maintenance_domain_equipment_rel",
        "domain_id",
        "equipment_id",
        string="Served By",
        domain="[('equipment_kind', '=', 'software')]",
    )
    note = fields.Html()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "This domain name already exists."),
    ]

    @api.model
    def _normalize_name(self, name):
        return (name or "").strip().lower().rstrip(".").strip()

    @api.model
    def _normalize_vals(self, vals):
        if "name" in vals:
            vals = dict(vals, name=self._normalize_name(vals["name"]))
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._normalize_vals(vals) for vals in vals_list])

    def write(self, vals):
        return super().write(self._normalize_vals(vals))

    @api.constrains("name")
    def _check_name(self):
        for domain in self:
            if not domain.name or any(char.isspace() for char in domain.name):
                raise ValidationError(
                    _("%(name)r is not a valid domain name.", name=domain.name or "")
                )
