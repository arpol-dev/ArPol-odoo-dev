import json
import posixpath
import re

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.osv import expression
from odoo.tools import SQL

from . import discovery_tools as tools

SCHEMA_VERSION = 1
MODULE_STATES = ("installed", "to_upgrade", "to_remove")
# models without active field: what vanished from the server is deleted, not archived
DELETED_WHEN_MISSING = ("docker.mount", "docker.component")
# set when the equipment is created (or while empty), then left to the user
CREATION_ONLY = ("deployment_method_id", "install_type", "equipment_kind")
INHERITED_FLAGS = {"physical_host_id": "physical_host_forced", "customer_id": "customer_forced"}
METHODS = {
    "manual": "maintenance_sw_base.deployment_method_manual",
    "myc": "maintenance_sw_base.deployment_method_myc",
    "cloudron": "maintenance_sw_base.deployment_method_cloudron",
}


def ref(key):
    """Value of a field pointing to the record of another operation of the plan."""
    return {"ref": key}


class PlanState:
    """What _plan builds while reading a discovery: the operations and the reading context."""

    def __init__(self, data, host, customer, matches):
        self.data = data
        self.host = host
        self.customer = customer
        self.matches = {key: int(rid) for key, rid in (matches or {}).items() if rid}
        self.mid, self.hostname, self.root_key = tools.machine_ids(data)
        self.date = (data.get("collected_at") or "")[:10] or fields.Date.today().isoformat()
        self.ops = []
        self.by_key = {}
        self.stack_key = self.cloudron_key = None
        self.zerok_services = set()
        # which sections ran fine: only their objects may be marked missing
        self.platforms_ok = self.docker_ok = self.pve_guests_ok = self.cloudron_apps_ok = False
        self.odoo_ok = False
        self.seen_equipment = set()
        self.seen_hosts = set()
        self.cloudron_app_containers = set()
        self.image_components = {}  # image key -> [(path, component key)]
        self.core_components = {}  # image key -> component key of the Odoo server
        self.container_components = {}  # container key -> [(path, component key)]
        self.container_images = {}  # container key -> image key
        self.repo_upstreams = {}  # repository key -> upstream URLs seen, in order


class DiscoveryImporter(models.AbstractModel):
    """Turns a discovery file (static/discover.sh) into a plan of operations, then applies it.

    A plan is an ordered list of operations (dict): ``key`` (identity in the plan: discovery key
    of an equipment or host, else built from the identity of the record, e.g.
    ``image:<repository>@<digest>``), ``model``, ``action`` (create, update, unchanged,
    missing), ``record_id`` (existing record, else False), ``label``, ``values`` (written
    values; a value ``{"ref": key}`` stands for the record of an earlier operation), ``changes``
    (readable summary of an update) and ``parent_key``.
    """

    _name = "maintenance.discovery.importer"
    _description = "Server Discovery Importer"

    # ------------------------------------------------------------------ reading
    @api.model
    def _parse(self, raw):
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise UserError(
                self.env._("This is not a discovery file: it is not valid JSON (%s).", error)
            ) from error
        return self._check_data(data)

    @api.model
    def _check_data(self, data):
        if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
            version = data.get("schema_version") if isinstance(data, dict) else None
            raise UserError(self.env._(
                "Unknown discovery file format (schema version %(version)s, this module reads "
                "schema version %(expected)s): run the discover.sh script served by this "
                "database.",
                version=version, expected=SCHEMA_VERSION,
            ))
        if not tools.section(data, "machine"):
            raise UserError(self.env._(
                "The discovery file has no readable machine section: the server cannot be "
                "identified."
            ))
        return data

    @api.model
    def _load(self, data):
        if isinstance(data, (bytes, str)):
            return self._parse(data)
        return self._check_data(data)

    @api.model
    def _as_record(self, model, value):
        if isinstance(value, models.BaseModel):
            return value
        return self.env[model].browse(value or ())

    # ------------------------------------------------------------------ suggestions
    @api.model
    def _suggest(self, data):
        """Physical host and existing equipment (without key) proposed for a discovery."""
        data = self._load(data)
        mid, hostname, root_key = tools.machine_ids(data)
        Equipment = self.env["maintenance.equipment"]
        # archived (missing) records keep their key: they are found by it, not by name
        # (in any company: a key is unique across them)
        Known = Equipment.sudo().with_context(active_test=False)
        matches = {}
        system = self._find_by_key("maintenance.equipment", root_key)
        if not system:
            candidates = Equipment.search([
                ("discovery_key", "=", False), ("install_type", "=", "os"),
                ("name", "ilike", hostname),
            ], order="id")
            system = candidates.filtered(lambda e: e.name.lower() == hostname.lower())[:1]
            system = system or candidates[:1]
            if system:
                matches[root_key] = system.id
        host = system.physical_host_id
        if not host:
            ips = [ip.get("address") for ip in tools.section(data, "machine").get("ips") or []]
            host = self.env["maintenance.host"]._discovery_find_host([ip for ip in ips if ip])
        for container in (tools.section(data, "docker") or {}).get("containers") or []:
            name = container.get("name")
            key = f"container:{mid}:{name}"
            if not name or Known.search_count([("discovery_key", "=", key)]):
                continue
            domain = [
                ("discovery_key", "=", False), "|", ("name", "=", name),
                ("container_name", "=", name),
            ]
            if system:
                # a container name is often the same on every server: only in this tree
                candidates = Equipment.search(domain + [("id", "child_of", system.id)], limit=1)
            else:
                candidates = Equipment.search(domain, limit=2)
                candidates = candidates if len(candidates) == 1 else Equipment
            if candidates:
                matches[key] = candidates.id
        return {"host_id": host[:1].id or False, "matches": matches}

    # ------------------------------------------------------------------ plan
    @api.model
    def _plan(self, data, host=None, customer=None, matches=None):
        """Operations to apply for a discovery, in order; nothing is written."""
        data = self._load(data)
        state = PlanState(
            data,
            self._as_record("maintenance.host", host),
            self._as_record("res.partner", customer),
            matches,
        )
        self._check_matches(state)
        self._check_hostname(state)
        self._plan_os(state)
        self._plan_platforms(state)
        self._plan_containers(state)
        self._plan_cloudron_apps(state)
        self._plan_odoo(state)
        self._plan_missing(state)
        self._plan_upstreams(state)
        self._plan_order(state)
        return state.ops

    def _check_matches(self, state):
        """One existing equipment cannot stand for two discovered objects."""
        keys_by_id = {}
        for key, record_id in state.matches.items():
            keys_by_id.setdefault(record_id, []).append(key)
        for record_id, keys in keys_by_id.items():
            if len(keys) > 1:
                record = self.env["maintenance.equipment"].sudo().browse(record_id)
                raise UserError(self.env._(
                    "%(record)s is chosen for several discovered objects (%(keys)s): choose it "
                    "for one of them only.",
                    record=record.display_name, keys=", ".join(sorted(keys)),
                ))

    @api.model
    def _hostname_conflict(self, data):
        """(root, host name recorded on it) when the root found by the key of the discovery
        was discovered under another host name, else (empty, False)."""
        _mid, hostname, root_key = tools.machine_ids(data)
        root = self.env["maintenance.equipment"].sudo().with_context(active_test=False).search(
            [("discovery_key", "=", root_key)], limit=1
        )
        known = root.discovery_hostname
        if known and known.lower() != hostname.lower():
            return root, known
        return root.browse(), False

    def _check_hostname(self, state):
        """Another server with the same identity (cloned VM sharing a machine-id): its tree
        would be updated and its containers archived. Refused unless the root is explicitly
        attached (matches: the same server, renamed)."""
        root, known = self._hostname_conflict(state.data)
        if known and state.matches.get(state.root_key) != root.id:
            raise UserError(self.env._(
                "This file comes from server %(new)s, but its identity (%(key)s) was already "
                "discovered on server %(old)s: two servers sharing a machine-id (a cloned "
                "virtual machine) would be merged, and the containers of %(old)s archived. "
                "If %(new)s is %(old)s renamed, confirm it in the import wizard (Same Server, "
                "Renamed).",
                new=state.hostname, old=known, key=state.root_key,
            ))

    def _plan_op(self, state, key, model, record, values, create_values=None, label=None,
                 parent_key=None):
        """Plan the record `key`: created with create_values + values, else updated with the
        values that differ. A key already planned is planned once."""
        if key in state.by_key:
            return state.by_key[key]
        if record:
            changes, to_write = self._plan_diff(state, record, values)
            action = "update" if to_write else "unchanged"
            label = record.display_name
        else:
            action, to_write, changes = "create", {**(create_values or {}), **values}, []
        op = {
            "key": key, "model": model, "action": action, "record_id": record.id or False,
            "label": label or key, "values": to_write, "changes": changes,
            "parent_key": parent_key,
        }
        state.ops.append(op)
        state.by_key[key] = op
        return op

    def _plan_missing_op(self, state, key, record, values, parent_key=None):
        op = {
            "key": key, "model": record._name, "action": "missing", "record_id": record.id,
            "label": record.display_name, "values": values,
            "changes": [
                self.env._("Absent from the discovery: deleted")
                if record._name in DELETED_WHEN_MISSING
                else self.env._("Absent from the discovery: archived")
            ],
            "parent_key": parent_key,
        }
        state.ops.append(op)
        state.by_key[key] = op
        return op

    def _plan_diff(self, state, record, values):
        """(changes, values to write): the values that differ from the record."""
        changes, to_write = [], {}
        for fname, new in values.items():
            field = record._fields[fname]
            old = record[fname]
            if field.type == "many2one":
                new_id = self._plan_ref_id(state, new)
                if new_id is not None and (old.id or False) == (new_id or False):
                    continue
                old_text, new_text = old.display_name, self._plan_ref_label(state, field, new)
            elif field.type == "datetime":
                new_value = fields.Datetime.to_datetime(new) if new else False
                if (old or False) == (new_value or False):
                    continue
                old_text, new_text = old and fields.Datetime.to_string(old), new
            elif field.type == "boolean":
                if bool(old) == bool(new):
                    continue
                old_text, new_text = str(bool(old)), str(bool(new))
            elif field.type == "selection":
                if (old or False) == (new or False):
                    continue
                labels = dict(field._description_selection(self.env))
                old_text, new_text = labels.get(old, old), labels.get(new, new)
            else:
                if (old or False) == (new or False):
                    continue
                old_text, new_text = old, new
            to_write[fname] = new
            changes.append("%s: %s → %s" % (
                field._description_string(self.env), self._short(old_text), self._short(new_text)
            ))
        return changes, to_write

    @staticmethod
    def _short(text):
        text = str(text or "∅").replace("\n", " ")
        return text if len(text) <= 80 else text[:77] + "..."

    def _plan_ref_id(self, state, value):
        """Id of a planned value; None when it is a record still to create."""
        if isinstance(value, dict):
            return state.by_key[value["ref"]]["record_id"] or None
        return value or False

    def _plan_ref_label(self, state, field, value):
        if isinstance(value, dict):
            return state.by_key[value["ref"]]["label"]
        return self.env[field.comodel_name].browse(value or ()).display_name

    def _method(self, name):
        return self.env.ref(METHODS[name]).id

    def _plan_version(self, state, product_name, version_name):
        """Catalog product and version, created when missing; a reference to the version."""
        if not product_name or not version_name:
            return None
        product = self.env["software.product"].with_context(active_test=False).search(
            [("name", "=", product_name)], limit=1
        )
        product_key = f"product:{product_name}"
        self._plan_op(state, product_key, "software.product", product, {},
                      {"name": product_name}, label=product_name)
        version = self.env["software.version"]
        if product:
            version = version.search(
                [("product_id", "=", product.id), ("name", "=", version_name)], limit=1
            )
        version_key = f"version:{product_name}:{version_name}"
        self._plan_op(state, version_key, "software.version", version, {}, {
            "product_id": ref(product_key), "name": version_name,
            "sequence": tools.version_sequence(version_name),
        }, label=f"{product_name} {version_name}", parent_key=product_key)
        return ref(version_key)

    def _find_by_key(self, model, key):
        """Record of a discovery key, in any company (the key is unique across them). One the
        user cannot write (another company not selected...) is refused by name: creating it
        again would break the unique key."""
        found = self.env[model].sudo().with_context(active_test=False).search(
            [("discovery_key", "=", key)], limit=1
        )
        record = self.env[model].with_context(active_test=False).browse(found.id)
        if found:
            try:
                record.check_access("write")
            except AccessError as error:
                raise UserError(self.env._(
                    "%(record)s (%(key)s) was already discovered, but you cannot modify it: "
                    "select its company, or ask a user who can.",
                    record=found.display_name, key=key,
                )) from error
        return record

    def _find_equipment(self, state, key):
        Equipment = self.env["maintenance.equipment"].with_context(active_test=False)
        record = self._find_by_key("maintenance.equipment", key)
        if not record and state.matches.get(key):
            record = Equipment.browse(state.matches[key]).exists()
            if record.discovery_key:
                # already known under another key: not the same object
                record = Equipment
        return record

    def _plan_equipment(self, state, key, values, name, parent_key=None, record=None):
        """An equipment of the tree: its name and parent are only set when it is created, its
        kind, install type and deployment method then or while empty."""
        if record is None:
            record = self._find_equipment(state, key)
        values = dict(
            values, discovery_key=key, equipment_kind="software", active=True,
            missing_since_discovery=False,
        )
        if record:
            values = {
                fname: value for fname, value in values.items()
                if fname not in CREATION_ONLY or not record[fname]
            }
        create_values = {"name": name}
        if parent_key:
            create_values["parent_id"] = ref(parent_key)
        state.seen_equipment.add(key)
        return self._plan_op(state, key, "maintenance.equipment", record, values, create_values,
                             label=name, parent_key=parent_key)

    # ------------------------------------------------------------------ levels
    def _plan_os(self, state):
        """The root: the operating system, attached to the chosen host and customer."""
        os_data = tools.section(state.data, "os") or {}
        product = tools.OS_PRODUCTS.get((os_data.get("id") or "").lower())
        values = {
            "install_type": "os", "deployment_method_id": self._method("manual"),
            "discovery_hostname": state.hostname,
        }
        version = self._plan_version(state, product, os_data.get("version_id"))
        if version:
            values["software_version_id"] = version
        elif os_data.get("pretty_name"):
            values["version_note"] = os_data["pretty_name"]
        record = self._find_equipment(state, state.root_key)
        for fname, value in (("physical_host_id", state.host), ("customer_id", state.customer)):
            flag = INHERITED_FLAGS[fname]
            # the value it inherits from its parent (e.g. proposed back by the wizard) is no
            # reason to force it
            if not value or (record and not record[flag] and record.parent_id[fname] == value):
                continue
            values.update({fname: value.id, flag: True})
        name = f"{product or os_data.get('pretty_name') or 'Server'} ({state.hostname})"
        self._plan_equipment(state, state.root_key, values, name, record=record)

    def _plan_platforms(self, state):
        """Under the OS: Proxmox VE (and its guests), the 0k stack, the Cloudron instance."""
        platforms = tools.section(state.data, "platforms")
        if platforms is None:
            return
        state.platforms_ok = True
        mid, hostname = state.mid, state.hostname
        pve = platforms.get("proxmox")
        if pve:
            values = {"install_type": "package", "deployment_method_id": self._method("manual")}
            version = self._plan_version(state, "Proxmox VE", pve.get("version"))
            if version:
                values["software_version_id"] = version
            self._plan_equipment(state, f"pve:{mid}", values, f"Proxmox VE ({hostname})",
                                 state.root_key)
            self._plan_pve_guests(state)
        zerok = platforms.get("zerok")
        if zerok:
            path = zerok.get("path") or "/opt/apps/myc-deploy"
            state.stack_key = f"stack:{mid}:{path}"
            services = (tools.section(state.data, "zerok") or {}).get("services") or []
            state.zerok_services = {service.get("name") for service in services}
            self._plan_equipment(state, state.stack_key, {
                "install_type": "compose_stack", "deployment_method_id": self._method("myc"),
                "install_path": path,
            }, f"0k stack ({hostname})", state.root_key)
        cloudron = platforms.get("cloudron")
        if cloudron:
            state.cloudron_key = f"cloudron:{mid}"
            values = {
                "install_type": "package", "deployment_method_id": self._method("cloudron"),
                "install_path": "/home/yellowtent",
            }
            version = self._plan_version(state, "Cloudron", cloudron.get("version"))
            if version:
                values["software_version_id"] = version
            self._plan_equipment(state, state.cloudron_key, values, f"Cloudron ({hostname})",
                                 state.root_key)

    def _plan_pve_guests(self, state):
        """One virtual machine host per VM / LXC, on the hardware of the Proxmox host."""
        proxmox = tools.section(state.data, "proxmox")
        if proxmox is None:
            return
        state.pve_guests_ok = True
        root_op = state.by_key[state.root_key]
        support = state.host or self.env["maintenance.equipment"].browse(
            root_op["record_id"] or ()
        ).physical_host_id
        for guest in proxmox.get("guests") or []:
            vmid = guest.get("vmid")
            if not vmid:
                continue
            key = f"pve-guest:{state.mid}:{vmid}"
            values = {"discovery_key": key, "host_type": "vm", "active": True}
            if support.equipment_id:
                values["equipment_id"] = support.equipment_id.id
            state.seen_hosts.add(key)
            name = guest.get("name") or f"VM {vmid}"
            self._plan_op(state, key, "maintenance.host", self._find_by_key("maintenance.host", key),
                          values, {"name": name}, label=name, parent_key=f"pve:{state.mid}")

    def _plan_containers(self, state):
        """One equipment per running container, with its image, mounts and components."""
        docker = tools.section(state.data, "docker")
        if docker is None:
            return
        state.docker_ok = True
        odoo = tools.section(state.data, "odoo")
        state.odoo_ok = odoo is not None
        odoo = odoo or {}
        instances = {i.get("container"): i for i in odoo.get("instances") or []}
        for container in docker.get("containers") or []:
            if container.get("name"):
                self._plan_container(state, container, instances.get(container["name"]))

    def _plan_container(self, state, container, instance):
        name = container["name"]
        inspect = container.get("inspect") or {}
        labels = tools.labels_of(inspect)
        key = f"container:{state.mid}:{name}"
        if state.cloudron_key and (labels.get("isCloudronManaged") == "true"
                                   or labels.get("appId")):
            parent_key, method = state.cloudron_key, "cloudron"
            if labels.get("appId"):
                state.cloudron_app_containers.add(labels["appId"])
        elif state.stack_key and self._is_zerok_container(state, name, labels):
            parent_key, method = state.stack_key, "myc"
        else:
            parent_key, method = state.root_key, "manual"
        image_key = state.container_images[key] = self._plan_image(state, container, instance)
        record = self._find_equipment(state, key)
        values = {
            "install_type": "docker_container", "deployment_method_id": self._method(method),
            "container_name": name,
        }
        if image_key:
            values["docker_image_id"] = ref(image_key)
        runtime_changes = self._runtime_changes(state, record, instance)
        if runtime_changes is not None:
            values["runtime_changes"] = runtime_changes
        self._plan_equipment(state, key, values, name, parent_key, record=record)
        self._plan_mounts(state, key, record, inspect, instance or {}, image_key)

    def _is_zerok_container(self, state, name, labels):
        service = labels.get("com.docker.compose.service")
        return (
            labels.get("com.docker.compose.project") == "myc"
            or name.startswith("myc_")
            or bool(service and service in state.zerok_services)
        )

    def _runtime_changes(self, state, record, instance):
        """runtime_changes with a block for the links not mentioned yet; None: unchanged."""
        current = record.runtime_changes or "" if record else ""
        lines = [
            f"{link['link']} -> {link.get('target') or '?'}"
            for link in (instance or {}).get("runtime_links") or []
            if link.get("link") and not re.search(
                r"(?<![^\s(\[\"'])" + re.escape(link["link"]) + r"(?=[\s.,;:)\]\"']|$)", current
            )
        ]
        if not lines:
            return None
        block = self.env._("Discovery of %s:", state.date) + "\n" + "\n".join(lines)
        return f"{current}\n\n{block}" if current else block

    def _plan_image(self, state, container, instance):
        """docker.image by (repository, digest): a new digest is a new image."""
        inspect = container.get("inspect") or {}
        image = container.get("image_inspect") or {}
        image_ref = (inspect.get("Config") or {}).get("Image") or ""
        if not image_ref or image_ref.startswith("sha256:"):
            image_ref = (image.get("RepoTags") or [""])[0]
        registry, repository, tag = tools.split_image_ref(image_ref)
        digest = False
        repo_digests = image.get("RepoDigests") or []
        for item in repo_digests:
            if tools.split_image_ref(item)[:2] == (registry, repository):
                digest = item.split("@", 1)[1]
                break
        else:
            if repo_digests:
                registry, repository, _tag = tools.split_image_ref(repo_digests[0])
                digest = repo_digests[0].split("@", 1)[1]
        # a local build has no registry digest: its image id stands for it
        digest = digest or image.get("Id") or inspect.get("Image") or False
        if not repository:
            return None
        key = f"image:{repository}@{digest or ''}"
        record = self.env["docker.image"].search(
            [("repository", "=", repository), ("digest", "=", digest)], limit=1
        )
        values = {"registry": registry, "tag": tag or False}
        build_date = tools.parse_docker_datetime(image.get("Created"))
        if build_date:
            values["build_date"] = fields.Datetime.to_string(build_date)
        version = self._image_version(state, repository, tag, image, instance)
        if version:
            values["version_id"] = version
        label = f"{repository}:{tag}" if tag else repository
        self._plan_op(state, key, "docker.image", record, values,
                      {"repository": repository, "digest": digest}, label=label)
        if instance:
            self._plan_image_components(state, key, record, instance, inspect)
        return key

    def _image_version(self, state, repository, tag, image, instance):
        if instance:
            return self._plan_version(state, "Odoo", tools.odoo_series(instance.get("version")))
        if "postgres" in repository.rsplit("/", 1)[-1]:
            env = (image.get("Config") or {}).get("Env")
            major = tools.env_value(env, "PG_MAJOR") or (tag or "").split(".")[0].split("-")[0]
            if major.isdigit():
                return self._plan_version(state, "PostgreSQL", major)
        return None

    def _image_repos(self, instance):
        """Repositories of the image: repos.yaml (structured by the script), else git dirs."""
        git = {repo.get("path"): repo for repo in instance.get("repos") or [] if repo.get("path")}
        items = []
        for item in (instance.get("repos_spec") or {}).get("items") or []:
            remotes = item.get("remotes") or {}
            target = item.get("target") or {}
            remote, ref_name = target.get("remote"), target.get("ref")
            if not target:
                # no target: git-aggregator uses the remote of the first merge
                merges = item.get("merges") or []
                remote = merges[0].split()[0] if merges and merges[0].split() else None
                if remote not in remotes and len(remotes) == 1:
                    remote = next(iter(remotes))
            found = git.get(item.get("path")) or {}
            items.append({
                "name": item.get("name"), "path": item.get("path"),
                "url": remotes.get(remote) or found.get("url"),
                "upstream": (item.get("upstreams") or {}).get(remote),
                "ref": ref_name or found.get("branch"), "commit": found.get("commit"),
                "merges": "\n".join(item.get("merges") or []),
            })
        if not items:
            items = [{
                "name": posixpath.basename(repo["path"].rstrip("/")), "path": repo["path"],
                "url": repo.get("url"), "upstream": None, "ref": repo.get("branch"),
                "commit": repo.get("commit"), "merges": False,
            } for repo in git.values()]
        return items

    def _plan_image_components(self, state, image_key, image_record, instance, inspect):
        if image_key in state.image_components:
            return
        binds = [m.get("Destination") for m in inspect.get("Mounts") or [] if m.get("Destination")]
        existing = {c.path: c for c in image_record.component_ids} if image_record else {}
        components = state.image_components[image_key] = []
        for item in self._image_repos(instance):
            path, url = item["path"], item["url"]
            # a repository in a mount belongs to the mount, not to the image
            if not path or not url or any(tools.is_under(path, dest) for dest in binds):
                continue
            repo_key = self._plan_repository(state, url, item["upstream"])
            key = f"component:{image_key}:{path}"
            role = tools.component_role(item["name"], url, item["upstream"])
            self._plan_op(state, key, "docker.component",
                          existing.get(path, self.env["docker.component"]), {
                              "repository_id": ref(repo_key), "ref": item["ref"] or False,
                              "commit": item["commit"] or False, "merges": item["merges"] or False,
                          }, {
                              "image_id": ref(image_key), "path": path, "role": role,
                          }, label=f"{tools.repository_name(url)} — {path}", parent_key=image_key)
            components.append((path, key))
            if role == "core":
                state.core_components.setdefault(image_key, key)

    def _plan_repository(self, state, url, upstream=None):
        """git.repository by URL, without the masked credentials (the script writes
        https://***@host/...) and whatever the case: the credential-free URL is the identity.
        The upstream is only noted here: a repository listed several times (several Odoo
        instances) may come with upstreams spelled differently, settled by _plan_upstreams."""
        url = tools.clean_url(url)
        key = f"repo:{tools.url_identity(url)}"
        if upstream:
            upstream = tools.clean_url(upstream)
            if tools.url_identity(upstream) != tools.url_identity(url):
                state.repo_upstreams.setdefault(key, []).append(upstream)
        if key not in state.by_key:
            record = self._find_repository(url)
            name = tools.repository_name(url)
            self._plan_op(state, key, "git.repository", record, {},
                          {"name": name, "url": url}, label=name)
        return key

    def _find_repository(self, url):
        identity = tools.url_identity(url)
        candidates = self.env["git.repository"].search(
            [("url", "=ilike", tools.like_escape(url.rstrip("/")) + "%")], order="id"
        )
        return candidates.filtered(lambda r: tools.url_identity(r.url) == identity)[:1]

    def _plan_upstreams(self, state):
        """The upstream of each repository seen with one. Several spellings in one discovery:
        the current upstream when it is one of them, else the first in URL order: the same
        file always plans the same value, never a change back and forth. An upstream that
        would close a cycle (A upstream of B, B of A) is not planned: the first link planned
        (in the order of the file) is kept, and found again at the next import."""
        planned = {}
        for key, upstreams in state.repo_upstreams.items():
            identities = {tools.url_identity(url): url for url in upstreams}
            op = state.by_key[key]
            record = self.env["git.repository"].browse(op["record_id"] or ())
            if record.upstream_id and tools.url_identity(record.upstream_id.url) in identities:
                # kept as is; listed all the same (the preview shows every repository seen)
                planned[key] = self._plan_repository(state, record.upstream_id.url)
                continue
            upstream_key = self._plan_repository(state, identities[min(identities)])
            if self._upstream_reaches(state, planned, upstream_key, key):
                continue
            planned[key] = upstream_key
            values = {"upstream_id": ref(upstream_key)}
            if op["action"] == "create":
                op["values"].update(values)
                continue
            changes, to_write = self._plan_diff(state, record, values)
            if to_write:
                op["values"].update(to_write)
                op["changes"] += changes
                op["action"] = "update"

    def _upstream_reaches(self, state, planned, start_key, target_key):
        """The upstream chain from repository start_key (planned upstreams, else the recorded
        ones) reaches target_key."""
        key, record, seen = start_key, None, set()
        while key not in seen:
            if key == target_key:
                return True
            seen.add(key)
            if key in planned:
                key, record = planned[key], None
                continue
            if record is None:
                op = state.by_key.get(key)
                record = self.env["git.repository"].browse(op and op["record_id"] or ())
            record = record.upstream_id
            if not record:
                return False
            key = f"repo:{tools.url_identity(record.url)}"
        return False

    def _plan_order(self, state):
        """Every operation after the ones it refers to (a record is created before it is
        pointed to), otherwise in the planned order (depth-first, each operation visited
        once: it always ends). A reference closing a cycle cannot be honoured: dropped."""
        ordered, done, visiting = [], set(), set()

        def visit(op):
            stack = [(op, iter(list(op["values"].items())))]
            visiting.add(op["key"])
            while stack:
                current, refs = stack[-1]
                for fname, value in refs:
                    if not isinstance(value, dict) or value["ref"] in done:
                        continue
                    if value["ref"] in visiting:
                        del current["values"][fname]
                        continue
                    target = state.by_key[value["ref"]]
                    visiting.add(target["key"])
                    stack.append((target, iter(list(target["values"].items()))))
                    break
                else:
                    stack.pop()
                    visiting.discard(current["key"])
                    done.add(current["key"])
                    ordered.append(current)

        for op in list(state.ops):
            if op["key"] not in done:
                visit(op)
        state.ops[:] = ordered

    def _plan_mounts(self, state, container_key, container_record, inspect, instance, image_key):
        """docker.mount by (container, destination), and the git checkouts they bring."""
        addons_path = [path.rstrip("/") for path in instance.get("addons_path") or []]
        mount_repos = [repo for repo in instance.get("mount_repos") or [] if repo.get("path")]
        existing = {m.destination: m for m in container_record.mount_ids} if container_record else {}
        Mount = self.env["docker.mount"]
        mounts = []
        for mount in inspect.get("Mounts") or []:
            dest = mount.get("Destination")
            if not dest:
                continue
            mount_type = "volume" if mount.get("Type") == "volume" else "bind"
            source = (mount_type == "volume" and mount.get("Name")) or mount.get("Source") or dest
            key = f"mount:{container_key}:{dest}"
            record = existing.get(dest, Mount)
            self._plan_op(state, key, "docker.mount", record, {
                "discovered": True, "mount_type": mount_type, "source": source,
                "mode": "rw" if mount.get("RW", True) else "ro",
                "usage": tools.mount_usage(dest, [r["path"] for r in mount_repos], addons_path),
            }, {"equipment_id": ref(container_key), "destination": dest},
                label=f"{source} → {dest}", parent_key=container_key)
            mounts.append((dest, key, record))
        image_components = state.image_components.get(image_key) or []
        by_folder = {posixpath.basename(path.rstrip("/")): key for path, key in image_components}
        components = list(image_components)
        for repo in mount_repos:
            path, url = repo["path"], repo.get("url")
            owners = [m for m in mounts if tools.is_under(path, m[0])]
            if not owners or not url:
                continue
            _dest, mount_key, mount_record = max(owners, key=lambda m: len(m[0]))
            folder = posixpath.basename(path.rstrip("/"))
            # in the addons_path instead of the image's repository of the same folder name
            overrides = by_folder.get(folder) if path.rstrip("/") in addons_path else None
            key = f"component:{mount_key}:{path}"
            record = mount_record.component_ids.filtered(lambda c: c.path == path)[:1]
            self._plan_op(state, key, "docker.component", record, {
                "discovered": True, "repository_id": ref(self._plan_repository(state, url)),
                "ref": repo.get("branch") or False, "commit": repo.get("commit") or False,
                "overrides_id": ref(overrides) if overrides else False,
            }, {
                "mount_id": ref(mount_key), "path": path,
                "role": tools.component_role(folder, url),
            }, label=f"{tools.repository_name(url)} — {path}", parent_key=mount_key)
            components.append((path, key))
        state.container_components[container_key] = components
        self._plan_vanished_mounts(state, container_key, existing, mounts, inspect, instance)

    def _plan_vanished(self, state, key, record, parent_key):
        """A mount or component absent from the discovery: deleted when a discovery made it
        (discovered), else entered by hand: kept, listed as unchanged."""
        if record.discovered:
            self._plan_missing_op(state, key, record, {}, parent_key=parent_key)
            return
        op = self._plan_op(state, key, record._name, record, {}, parent_key=parent_key)
        op["changes"] = [self.env._("Entered by hand, absent from the discovery: kept")]

    def _plan_vanished_mounts(self, state, container_key, existing, mounts, inspect, instance):
        """Mounts gone from the container, and checkouts gone from a mount: deleted (a stale
        mount component would still override an image component) when a discovery made them.
        Only when the list that would hold them is known to be complete: the container's
        Mounts (present, even empty), and the checkouts of a mount whose source the script
        could read (mount_repos_status ok) in the Odoo instance of the container."""
        if "Mounts" in inspect:
            kept = {dest for dest, _key, _record in mounts}
            for dest, record in existing.items():
                if dest not in kept:
                    self._plan_vanished(state, f"mount:{container_key}:{dest}", record,
                                        container_key)
        if not (state.odoo_ok and instance):
            return
        read = {
            status.get("destination") for status in instance.get("mount_repos_status") or []
            if status.get("status") == "ok"
        }
        # listed without being readable (no url): present, kept as is
        listed = {repo.get("path") for repo in instance.get("mount_repos") or []}
        for dest, mount_key, record in mounts:
            if dest not in read:
                continue
            for component in record.component_ids:
                key = f"component:{mount_key}:{component.path}"
                if key not in state.by_key and component.path not in listed:
                    self._plan_vanished(state, key, component, mount_key)

    def _plan_cloudron_apps(self, state):
        """Cloudron applications without a visible container: one software equipment each."""
        cloudron = tools.section(state.data, "cloudron")
        # without the containers, an app with a container could not be told apart
        if not state.cloudron_key or cloudron is None or not state.docker_ok:
            return
        state.cloudron_apps_ok = True
        for app in cloudron.get("apps") or []:
            app_id = app.get("id")
            if not app_id or app_id in state.cloudron_app_containers:
                continue
            name = app.get("name") or app_id
            if app.get("domain"):
                name = f"{name} ({app['domain']})"
            self._plan_equipment(state, f"cloudron-app:{state.mid}:{app_id}", {
                "install_type": "package", "deployment_method_id": self._method("cloudron"),
                "version_note": app.get("version") or False,
            }, name, state.cloudron_key)

    def _plan_odoo(self, state):
        """Odoo databases of each Odoo container, and their modules with their component."""
        odoo = tools.section(state.data, "odoo")
        if odoo is None or not state.docker_ok:
            return
        Database = self.env["maintenance.odoo.database"].with_context(active_test=False)
        for instance in odoo.get("instances") or []:
            key = f"container:{state.mid}:{instance.get('container')}"
            databases = instance.get("databases") or {}
            if key not in state.by_key or databases.get("status") != "ok":
                continue
            container_id = state.by_key[key]["record_id"]
            existing = {}
            if container_id:
                existing = {d.name: d for d in Database.search([("equipment_id", "=", container_id)])}
            core_key = state.core_components.get(state.container_images.get(key))
            resolve = self._module_resolver(state, key, instance, core_key)
            seen = set()
            for database in databases.get("items") or []:
                name = database.get("name")
                if not name:
                    continue
                seen.add(name)
                if database.get("status") == "error":
                    # not read (psql failed): neither created nor archived, modules untouched
                    continue
                db_key = f"db:{key}:{name}"
                record = existing.get(name, Database)
                self._plan_op(state, db_key, "maintenance.odoo.database", record,
                              {"active": True}, {"equipment_id": ref(key), "name": name},
                              label=name, parent_key=key)
                self._plan_modules(state, db_key, record, database.get("modules") or [], resolve)
            for name, record in existing.items():
                if name not in seen and record.active:
                    self._plan_missing_op(state, f"db:{key}:{name}", record, {"active": False},
                                          parent_key=key)

    def _plan_modules(self, state, db_key, db_record, modules, resolve):
        Module = self.env["maintenance.odoo.module"].with_context(active_test=False)
        existing = {}
        if db_record:
            existing = {m.name: m for m in Module.search([("database_id", "=", db_record.id)])}
        seen = set()
        for module in modules:
            name = module.get("name")
            if not name:
                continue
            seen.add(name)
            component = resolve(name)
            module_state = module.get("state")
            self._plan_op(state, f"module:{db_key}:{name}", "maintenance.odoo.module",
                          existing.get(name, Module), {
                              "installed_version": module.get("version") or False,
                              "state": module_state if module_state in MODULE_STATES else "installed",
                              "component_id": ref(component) if component else False,
                              "active": True,
                          }, {"database_id": ref(db_key), "name": name}, label=name,
                          parent_key=db_key)
        for name, record in existing.items():
            if name not in seen and record.active:
                self._plan_missing_op(state, f"module:{db_key}:{name}", record, {"active": False},
                                      parent_key=db_key)

    def _module_resolver(self, state, container_key, instance, core_key=None):
        """module name -> key of the component providing it: the first addons_path directory
        holding the module, followed through its link (/opt/odoo/auto/addons/<module> ->
        /opt/odoo/custom/src/<repository>/<module>), inside the component of longest path.
        base (and the test_* modules) are in the server's own odoo/addons, which Odoo adds by
        itself: they come from the core component (the server repository)."""
        components = state.container_components.get(container_key) or []
        addons = {d: set(mods or []) for d, mods in (instance.get("addons") or {}).items()}
        links = {
            link["link"]: link.get("target")
            for link in instance.get("addons_links") or instance.get("runtime_links") or []
            if link.get("link")
        }

        def resolve(module):
            for directory in instance.get("addons_path") or []:
                if module in addons.get(directory, ()):
                    path = f"{directory.rstrip('/')}/{module}"
                    real = links.get(path) or path
                    owners = [(p, k) for p, k in components if tools.is_under(real, p)]
                    return max(owners, key=lambda pk: len(pk[0]))[1] if owners else None
            if module == "base" or module.startswith("test_"):
                return core_key
            return None

        return resolve

    def _plan_missing(self, state):
        """Objects of this server known from a previous discovery and absent from this one,
        when the section that lists them ran fine."""
        mid = state.mid
        prefixes, exact = [], []
        if state.docker_ok:
            prefixes.append(f"container:{mid}:")
        if state.cloudron_apps_ok:
            prefixes.append(f"cloudron-app:{mid}:")
        if state.platforms_ok:
            prefixes.append(f"stack:{mid}:")
            exact += [f"pve:{mid}", f"cloudron:{mid}"]
        domains = [[("discovery_key", "=like", prefix + "%")] for prefix in prefixes]
        domains.append([("discovery_key", "in", exact)])
        for record in self.env["maintenance.equipment"].search(expression.OR(domains), order="id"):
            key = record.discovery_key
            if key in state.seen_equipment:
                continue
            if key in exact or any(key.startswith(prefix) for prefix in prefixes):
                self._plan_missing_op(state, key, record,
                                      {"active": False, "missing_since_discovery": True},
                                      parent_key=record.parent_id.discovery_key or None)
        if state.pve_guests_ok:
            prefix = f"pve-guest:{mid}:"
            for host in self.env["maintenance.host"].search(
                [("discovery_key", "=like", prefix + "%")], order="id"
            ):
                if host.discovery_key.startswith(prefix) and host.discovery_key not in state.seen_hosts:
                    self._plan_missing_op(state, host.discovery_key, host, {"active": False},
                                          parent_key=f"pve:{mid}")

    # ------------------------------------------------------------------ apply
    @api.model
    def _apply(self, data, host=None, customer=None, matches=None, attachment_name=None):
        """Apply the plan of a discovery in the current transaction; return the root (OS)."""
        raw = data if isinstance(data, (bytes, str)) else None
        data = self._load(data)
        ops = self._plan(data, host=host, customer=customer, matches=matches)
        ids = {}
        for op in ops:
            ids[op["key"]] = self._apply_op(op, ids)
        _mid, hostname, root_key = tools.machine_ids(data)
        root = self.env["maintenance.equipment"].browse(ids[root_key])
        self._apply_last_discovery(data, ops, ids)
        if raw is None:
            raw = json.dumps(data, indent=1, ensure_ascii=False)
        if isinstance(raw, str):
            raw = raw.encode()
        date = (data.get("collected_at") or "")[:10] or fields.Date.today().isoformat()
        # the attachment of the manager-only field discovery_file (protected by the field's
        # groups), replaced; written directly: an import that changes nothing leaves the root
        # untouched
        Attachment = self.env["ir.attachment"]
        Attachment.search([
            ("res_model", "=", root._name), ("res_id", "=", root.id),
            ("res_field", "=", "discovery_file"),
        ]).unlink()
        Attachment.create({
            "name": attachment_name or f"discovery-{hostname}-{date}.json",
            "raw": raw,
            "mimetype": "application/json",
            "res_model": root._name,
            "res_id": root.id,
            "res_field": "discovery_file",
        })
        root.invalidate_recordset(["discovery_file", "discovery_file_name"])
        return root

    def _apply_op(self, op, ids):
        """Run one operation; return the id of its record."""
        if op["action"] == "unchanged":
            return op["record_id"]
        values = {
            fname: ids[value["ref"]] if isinstance(value, dict) else value
            for fname, value in op["values"].items()
        }
        Model = self.env[op["model"]].with_context(active_test=False)
        if op["action"] == "create":
            return Model.create(values).id
        if op["action"] == "missing" and op["model"] in DELETED_WHEN_MISSING:
            # a mount deleted with its components: they are gone too
            Model.browse(op["record_id"]).exists().unlink()
            return False
        Model.browse(op["record_id"]).write(values)
        return op["record_id"]

    def _apply_last_discovery(self, data, ops, ids):
        """last_discovery of everything seen. Written in SQL: a discovery that finds nothing new
        changes no record (write_date and tracking untouched)."""
        when = tools.parse_docker_datetime(data.get("collected_at")) or fields.Datetime.now()
        for model in ("maintenance.equipment", "maintenance.odoo.database"):
            record_ids = tuple(
                ids[op["key"]] for op in ops if op["model"] == model and op["action"] != "missing"
            )
            if not record_ids:
                continue
            Model = self.env[model]
            Model.flush_model(["last_discovery"])
            self.env.cr.execute(SQL(
                "UPDATE %s SET last_discovery = %s WHERE id IN %s",
                SQL.identifier(Model._table), when, record_ids,
            ))
            Model.invalidate_model(["last_discovery"])
