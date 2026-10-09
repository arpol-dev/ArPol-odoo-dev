import base64
import binascii

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from ..models import discovery_tools as tools
from ..models.discovery_importer import DELETED_WHEN_MISSING

CONTAINER_INSTALL_TYPES = ("docker_container", "compose_stack")
ACTION_ORDER = ("create", "update", "unchanged", "missing")


class DiscoveryImportWizard(models.TransientModel):
    """Preview of a discovery file, then import: one file per run."""

    _name = "maintenance.discovery.import.wizard"
    _description = "Discovery Import Wizard"

    state = fields.Selection(
        [("upload", "File"), ("preview", "Preview"), ("done", "Done")],
        default="upload", required=True,
    )
    discovery_file = fields.Binary(string="Discovery File", attachment=False)
    filename = fields.Char()
    host_id = fields.Many2one("maintenance.host", string="Physical Host")
    customer_id = fields.Many2one("res.partner", string="Customer")
    line_ids = fields.One2many("maintenance.discovery.import.line", "wizard_id", string="Lines")
    root_equipment_id = fields.Many2one("maintenance.equipment", string="Operating System",
                                        readonly=True)
    summary = fields.Char(compute="_compute_summary")

    @api.depends("line_ids.action")
    def _compute_summary(self):
        labels = dict(self.env["maintenance.discovery.import.line"]._fields["action"]
                      ._description_selection(self.env))
        for wizard in self:
            counts = {action: 0 for action in ACTION_ORDER}
            for line in wizard.line_ids:
                counts[line.action] += 1
            wizard.summary = ", ".join(
                f"{counts[action]} {labels[action]}" for action in ACTION_ORDER if counts[action]
            )

    # ------------------------------------------------------------------ helpers
    def _check_manager(self):
        if not self.env.user.has_group("maintenance.group_equipment_manager"):
            raise AccessError(self.env._("Only equipment managers can import a discovery."))

    def _raw(self):
        self.ensure_one()
        if not self.discovery_file:
            raise UserError(self.env._("Choose the discovery file produced by discover.sh."))
        try:
            return base64.b64decode(self.discovery_file)
        except (binascii.Error, ValueError) as error:
            raise UserError(self.env._("The file cannot be read.")) from error

    def _matches(self):
        """{discovery key: equipment id} chosen on the lines; refused when unsuitable."""
        matches = {}
        for line in self.line_ids.filtered("match_id"):
            line._check_match()
            matches[line.key] = line.match_id.id
        return matches

    def _plan(self, raw, matches):
        return self.env["maintenance.discovery.importer"]._plan(
            raw, host=self.host_id, customer=self.customer_id, matches=matches
        )

    def _fill_lines(self, ops, root_key, mid):
        Line = self.env["maintenance.discovery.import.line"]
        records = {}
        for op in ops:
            if op["record_id"]:
                records[op["key"]] = self.env[op["model"]].with_context(active_test=False).browse(
                    op["record_id"]
                ).exists()
        container_prefix = f"container:{mid}:"
        values = []
        for sequence, op in enumerate(sorted(ops, key=lambda o: ACTION_ORDER.index(o["action"]))):
            key = op["key"]
            is_root = key == root_key
            is_container = key.startswith(container_prefix)
            record = records.get(key)
            matchable = op["model"] == "maintenance.equipment" and (is_root or is_container)
            match = self.env["maintenance.equipment"]
            if matchable and record and not record.discovery_key:
                match = record
            elif matchable and record and op["action"] != "create":
                # found by its key: nothing to choose
                matchable = False
            values.append({
                "wizard_id": self.id, "sequence": sequence, "key": key, "model": op["model"],
                "model_label": self.env[op["model"]]._description,
                "label": op["label"], "action": op["action"],
                "deleted": op["action"] == "missing" and op["model"] in DELETED_WHEN_MISSING,
                "changes": "\n".join(op["changes"]),
                "matchable": matchable,
                "match_kind": ("os" if is_root else "container") if matchable else False,
                "match_id": match.id or False,
                "record_ref": f"{op['model']},{op['record_id']}" if op["record_id"] else False,
            })
        Line.create(values)

    def _show(self, matches, suggest=False):
        """Rebuild the preview lines from the file and the choices (host, customer, matches)."""
        raw = self._raw()
        Importer = self.env["maintenance.discovery.importer"]
        data = Importer._parse(raw)
        if suggest:
            suggestion = Importer._suggest(data)
            if not self.host_id and suggestion["host_id"]:
                self.host_id = suggestion["host_id"]
            matches = dict(suggestion["matches"], **matches)
        mid, _hostname, root_key = tools.machine_ids(data)
        ops = self._plan(data, matches)
        self.line_ids.unlink()
        self._fill_lines(ops, root_key, mid)
        self.state = "preview"

    def _reopen(self):
        return {
            "type": "ir.actions.act_window", "name": self.env._("Import Discovery"),
            "res_model": self._name, "res_id": self.id, "view_mode": "form", "target": "new",
        }

    # ------------------------------------------------------------------ buttons
    def action_analyse(self):
        self._check_manager()
        self.ensure_one()
        self.line_ids.unlink()
        self._show({}, suggest=True)
        return self._reopen()

    def action_refresh(self):
        """Recompute the preview with the choices made on the lines."""
        self._check_manager()
        self.ensure_one()
        self._show(self._matches())
        return self._reopen()

    def action_back(self):
        self._check_manager()
        self.ensure_one()
        self.line_ids.unlink()
        self.state = "upload"
        return self._reopen()

    def action_apply(self):
        """Import the file again from its plan: the preview is not trusted."""
        self._check_manager()
        self.ensure_one()
        matches = self._matches()
        root = self.env["maintenance.discovery.importer"]._apply(
            self._raw(), host=self.host_id, customer=self.customer_id, matches=matches,
            attachment_name=self.filename or None,
        )
        self.write({"root_equipment_id": root.id, "state": "done"})
        self.line_ids.unlink()
        return self._reopen()

    def action_open_root(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window", "res_model": "maintenance.equipment",
            "res_id": self.root_equipment_id.id, "view_mode": "form", "target": "current",
        }


class DiscoveryImportLine(models.TransientModel):
    _name = "maintenance.discovery.import.line"
    _description = "Discovery Import Line"
    _order = "sequence, id"

    wizard_id = fields.Many2one("maintenance.discovery.import.wizard", required=True,
                                ondelete="cascade")
    sequence = fields.Integer()
    key = fields.Char(readonly=True)
    model = fields.Char(readonly=True)
    model_label = fields.Char(string="Type", readonly=True)
    label = fields.Char(string="Name", readonly=True)
    action = fields.Selection(
        [("create", "Create"), ("update", "Update"), ("unchanged", "Unchanged"),
         ("missing", "Missing")],
        readonly=True,
    )
    deleted = fields.Boolean(
        readonly=True, help="Missing from the server and without archive: it will be deleted."
    )
    changes = fields.Text(readonly=True)
    matchable = fields.Boolean(readonly=True)
    match_kind = fields.Selection([("os", "Operating System"), ("container", "Container")],
                                  readonly=True)
    match_id = fields.Many2one(
        "maintenance.equipment", string="Existing Equipment",
        help="Attach this object to an equipment entered by hand instead of creating one.",
    )
    record_ref = fields.Char(readonly=True)

    def _check_match(self):
        self.ensure_one()
        equipment = self.match_id
        if (not self.matchable or equipment.equipment_kind != "software"
                or equipment.discovery_key
                or (self.match_kind == "os" and equipment.install_type != "os")
                or (self.match_kind == "container" and equipment.install_type
                    and equipment.install_type not in CONTAINER_INSTALL_TYPES)):
            raise UserError(self.env._(
                "%(equipment)s cannot be attached to %(label)s: choose a software equipment "
                "entered by hand that no discovery has attached yet (an operating system for "
                "the system, a container or a stack for a container).",
                equipment=equipment.display_name, label=self.label or self.key,
            ))

    def action_open(self):
        self.ensure_one()
        model, res_id = self.record_ref.split(",")
        return {
            "type": "ir.actions.act_window", "res_model": model, "res_id": int(res_id),
            "view_mode": "form", "target": "current",
        }
