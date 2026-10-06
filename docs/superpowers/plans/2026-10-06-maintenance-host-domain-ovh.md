# Support physique, client, noms de domaine et pont OVH — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter le support physique et le client effectifs (hérités du parent) à chaque équipement, les modèles `maintenance.host` et `maintenance.domain`, et le module pont `maintenance_hosting_ovh` qui les alimente depuis `ovh_api`.

**Architecture:** `maintenance_sw_base` reçoit deux modèles (`maintenance.host`, `maintenance.domain`) et, sur `maintenance.equipment`, deux couples « saisi / effectif » (champs effectifs calculés, stockés, récursifs sur `parent_id`), plus un many2many domaines ↔ logiciels et le calcul « domaines d'un client » sur `res.partner`. `maintenance_sw_docker` n'affiche que le contexte. Le nouveau module `maintenance_hosting_ovh` surcharge `ovh.service._upsert` / `write` pour créer, mettre à jour et archiver supports et domaines.

**Tech Stack:** Odoo 18.0 Community, OCA `maintenance` 18.0, module tiers `ovh_api` 18.0.1.5.0 (`~/ovh_api-18.0.1.5.0/ovh_api`), tests `TransactionCase` dans `odoo:18.0` + `postgres:16` jetables.

**Spec:** `docs/superpowers/specs/2026-10-06-maintenance-host-domain-ovh-design.md` (complète `docs/superpowers/specs/2026-10-04-maintenance-software-inventory-design.md`)

## Global Constraints

- Dépôt : `~/dev/odoo/arpol-dev/ArPol-odoo-dev-18.0`, branche `18.0-maintenance-sw` (ne pas changer de branche, ne jamais pousser).
- Versions inchangées : `18.0.1.0.0` pour `maintenance_sw_base`, `maintenance_sw_docker` ; `maintenance_hosting_ovh` en `18.0.1.0.0`, licence `AGPL-3`, auteur `Armand Polmard`, site `https://arpol.fr`, en-tête de manifeste au style de `maintenance_sw_base/__manifest__.py`.
- `maintenance_sw_base` ne dépend jamais d'`ovh_api` ; seul `maintenance_hosting_ovh` dépend de `maintenance_sw_base` et `ovh_api`.
- Code et libellés en anglais ; français dans `<module>/i18n/fr.po` (+ `.pot`), en-tête `"Plural-Forms: nplurals=2; plural=(n > 1);\n"`, terminologie existante (« Produit logiciel », « Logiciel » pour la nature).
- Droits : lecture `base.group_user`, tout `maintenance.group_equipment_manager` sur les nouveaux modèles ; pas de règle multi-société sur `maintenance.host` / `maintenance.domain`.
- Messages de commit en français, préfixés du module (`maintenance_sw_base : `…), **sans** `Co-Authored-By` ni mention d'outil.
- Aucune action sur le serveur de production `arpol` autre que des lectures ; aucun push ; aucun message de chatter posté volontairement.

## Review Focus

- **Racine changée sur un arbre de 3 niveaux et plus** : le support/client effectif d'un petit-enfant suit (champs récursifs). → test dans la Tâche 2 (`test_parent_change_propagates`).
- **Synchronisation OVH lancée par un opérateur OVH sans droits de gestion de la maintenance** : elle ne doit pas échouer sur la création des supports/domaines. → test dans la Tâche 5 (`test_sync_by_ovh_operator_without_maintenance_rights`).
- **Nom de domaine saisi à la main avec majuscules, espaces ou point final** : il doit être reconnu et rattaché au service OVH du même nom, pas dupliqué. → tests Tâche 1 (normalisation) et Tâche 5 (`test_manual_domain_is_linked_not_duplicated`).
- **Service OVH archivé puis listé de nouveau** : le support/domaine lié est archivé puis désarchivé. → test Tâche 5 (`test_archive_and_restore_follow_service`).
- **Contact d'une entreprise cliente** : il retrouve les domaines de l'entreprise. → test Tâche 2 (`test_domains_through_company_contact`).

---

## Structure des fichiers

```
maintenance_sw_base/
├── models/maintenance_host.py          # NEW maintenance.host (+ logiciels en Tâche 2)
├── models/maintenance_domain.py        # NEW maintenance.domain
├── models/res_partner.py               # NEW domaines d'un client (Tâche 2)
├── models/maintenance_equipment.py     # MOD support/client saisi+effectif, domain_ids, needs_attachment
├── models/__init__.py                  # MOD imports
├── security/ir.model.access.csv        # MOD 4 lignes
├── views/maintenance_host_views.xml    # NEW
├── views/maintenance_domain_views.xml  # NEW
├── views/res_partner_views.xml         # NEW bouton « Noms de domaine »
├── views/maintenance_equipment_views.xml # MOD
├── views/menus.xml                     # MOD 2 menus
├── i18n/maintenance_sw_base.pot, fr.po # MOD
└── tests/test_host_domain.py (T1), test_host_customer.py (T2), test_equipment.py (MOD T2), test_data.py (MOD T3)

maintenance_sw_docker/
├── views/maintenance_equipment_views.xml # MOD contexte support/client
└── tests/test_views.py                   # MOD

maintenance_hosting_ovh/                  # NEW
├── __init__.py, __manifest__.py, hooks.py
├── data/res_partner_data.xml
├── models/__init__.py, maintenance_host.py, maintenance_domain.py, ovh_service.py
├── views/maintenance_host_views.xml, maintenance_domain_views.xml, ovh_service_views.xml
├── i18n/maintenance_hosting_ovh.pot, fr.po
└── tests/__init__.py, test_ovh_link.py
```

Hors dépôt : `~/dev/odoo/arpol-dev/run_sw_odoo.sh` (Tâche 0), `~/arpol-test/seed_hosts_domains.py` et `~/arpol-test/screenshots_hosts.js` (Tâche 6).

---

### Task 0: Le script de test monte `ovh_api`

**Files:**
- Modify: `~/dev/odoo/arpol-dev/run_sw_odoo.sh` (hors dépôt, non commité)

**Interfaces:**
- Produces: `run_sw_odoo.sh test|export|lang maintenance_hosting_ovh` fonctionne (le module `ovh_api` est dans l'`addons_path`).

- [ ] **Step 1: Ajouter le montage et le chemin**

Dans `odoo_run()`, ajouter `-v "$HOME/ovh_api-18.0.1.5.0":/mnt/ovh:ro` aux montages et `/mnt/ovh` à `--addons-path`, juste après `/mnt/oca-maintenance` :

```bash
odoo_run() {
  docker run --rm --network $NET -e HOST=$PG -e USER=odoo -e PASSWORD=odoo \
    -v "$REPO":/mnt/arpol:ro -v "$OCA":/mnt/oca-maintenance:ro -v "$HOME/ovh_api-18.0.1.5.0":/mnt/ovh:ro \
    -v "$OUT":/mnt/out \
    odoo:18.0 odoo \
    --addons-path=/mnt/arpol,/mnt/oca-maintenance,/mnt/ovh,/usr/lib/python3/dist-packages/odoo/addons \
    -d $DB --without-demo=all --stop-after-init "$@" >>"$LOG" 2>&1
}
```

- [ ] **Step 2: Vérifier**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `0 failed, 0 error(s) of 26 tests`, `RESULT: OK`.

---

### Task 1: Modèles `maintenance.host` et `maintenance.domain` (`maintenance_sw_base`)

**Files:**
- Create: `maintenance_sw_base/models/maintenance_host.py`, `maintenance_sw_base/models/maintenance_domain.py`
- Modify: `maintenance_sw_base/models/__init__.py`, `maintenance_sw_base/security/ir.model.access.csv`
- Test: `maintenance_sw_base/tests/test_host_domain.py`, `maintenance_sw_base/tests/__init__.py`

**Interfaces:**
- Produces:
  - `maintenance.host` : `name` (requis), `host_type` (`physical`/`vps`/`vm`/`shared_hosting`/`other`, défaut `other`), `provider_id` (`res.partner`), `equipment_id` (`maintenance.equipment`, matériel), `location`, `note`, `active` ; `_rec_names_search = ["name", "provider_id.name"]` ; constante `HOST_TYPES`.
  - `maintenance.domain` : `name` (requis, normalisé, unique), `registrar_id`, `expiration_date`, `auto_renew`, `partner_id`, `equipment_ids` (Many2many `maintenance.equipment`, table `maintenance_domain_equipment_rel`, colonnes `domain_id` / `equipment_id`), `note`, `active` ; `_normalize_name(name) -> str` (méthode `@api.model`).

- [ ] **Step 1: Écrire les tests**

`maintenance_sw_base/tests/__init__.py` — ajouter :

```python
from . import test_host_domain
```

`maintenance_sw_base/tests/test_host_domain.py` :

```python
from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from odoo.tools import mute_logger


class TestHostDomain(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Host = cls.env["maintenance.host"]
        cls.Domain = cls.env["maintenance.domain"]
        cls.alwaysdata = cls.env["res.partner"].create({"name": "Alwaysdata", "is_company": True})

    def test_host_defaults(self):
        host = self.Host.create({"name": "Tardis"})
        self.assertEqual(host.host_type, "other")
        self.assertTrue(host.active)

    def test_host_name_search_by_provider(self):
        host = self.Host.create({"name": "web-1", "provider_id": self.alwaysdata.id})
        self.assertIn(host.id, [row[0] for row in self.Host.name_search("Alwaysdata")])
        self.assertFalse(self.Host.name_search("zzz-no-such-host"))

    def test_domain_name_normalized(self):
        domain = self.Domain.create({"name": "  Example.FR. "})
        self.assertEqual(domain.name, "example.fr")
        domain.write({"name": "Other.Example.fr."})
        self.assertEqual(domain.name, "other.example.fr")

    def test_domain_name_unique_after_normalization(self):
        self.Domain.create({"name": "example.fr"})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self.Domain.create({"name": "EXAMPLE.fr."})

    def test_domain_name_cannot_be_blank(self):
        with self.assertRaises(ValidationError):
            self.Domain.create({"name": " . "})

    def test_domain_name_cannot_contain_space(self):
        with self.assertRaises(ValidationError):
            self.Domain.create({"name": "exa mple.fr"})
```

- [ ] **Step 2: Lancer pour voir l'échec**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `RESULT: FAILED` (`KeyError: 'maintenance.host'`).

- [ ] **Step 3: Implémenter**

`maintenance_sw_base/models/maintenance_host.py` :

```python
from odoo import fields, models

HOST_TYPES = [
    ("physical", "Physical Server"),
    ("vps", "VPS"),
    ("vm", "Virtual Machine"),
    ("shared_hosting", "Shared Hosting"),
    ("other", "Other"),
]


class MaintenanceHost(models.Model):
    _name = "maintenance.host"
    _description = "Physical Host"
    _order = "name"
    _rec_names_search = ["name", "provider_id.name"]

    name = fields.Char(required=True)
    host_type = fields.Selection(HOST_TYPES, string="Type", required=True, default="other")
    provider_id = fields.Many2one(
        "res.partner",
        string="Provider",
        help="Hosting company (OVHcloud, Alwaysdata...). Empty for a machine of your own.",
    )
    equipment_id = fields.Many2one(
        "maintenance.equipment",
        string="Hardware Equipment",
        domain="[('equipment_kind', '=', 'hardware')]",
        ondelete="set null",
        help="The hardware equipment, when you maintain the machine yourself.",
    )
    location = fields.Char()
    note = fields.Html()
    active = fields.Boolean(default=True)
```

`maintenance_sw_base/models/maintenance_domain.py` :

```python
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
```

`maintenance_sw_base/models/__init__.py` — ajouter à la fin :

```python
from . import maintenance_host
from . import maintenance_domain
```

`maintenance_sw_base/security/ir.model.access.csv` — ajouter :

```csv
access_maintenance_host_user,maintenance.host.user,model_maintenance_host,base.group_user,1,0,0,0
access_maintenance_host_manager,maintenance.host.manager,model_maintenance_host,maintenance.group_equipment_manager,1,1,1,1
access_maintenance_domain_user,maintenance.domain.user,model_maintenance_domain,base.group_user,1,0,0,0
access_maintenance_domain_manager,maintenance.domain.manager,model_maintenance_domain,maintenance.group_equipment_manager,1,1,1,1
```

- [ ] **Step 4: Lancer les tests**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `0 failed, 0 error(s) of 32 tests`, `RESULT: OK`.

- [ ] **Step 5: Commit**

```bash
git add maintenance_sw_base
git commit -m "maintenance_sw_base : supports physiques et noms de domaine"
```

---

### Task 2: Support et client effectifs, domaines d'un client (`maintenance_sw_base`)

**Files:**
- Modify: `maintenance_sw_base/models/maintenance_equipment.py`, `maintenance_sw_base/models/maintenance_host.py`, `maintenance_sw_base/models/__init__.py`, `maintenance_sw_base/tests/test_equipment.py`, `maintenance_sw_base/tests/__init__.py`
- Create: `maintenance_sw_base/models/res_partner.py`
- Test: `maintenance_sw_base/tests/test_host_customer.py`

**Interfaces:**
- Consumes: `maintenance.host`, `maintenance.domain` (Tâche 1) ; `parent_id` (OCA).
- Produces:
  - `maintenance.equipment` : `host_id` (saisi), `physical_host_id` (effectif, stocké, récursif, indexé), `customer_id` (saisi), `effective_customer_id` (effectif, stocké, récursif, indexé), `domain_ids` (Many2many, même table que `maintenance.domain.equipment_ids`) ; `needs_attachment` = logiciel sans `physical_host_id` et méthode non `managed_by_provider`.
  - `maintenance.host` : `software_ids` (O2m sur `physical_host_id`), `software_count`, `action_view_software()`.
  - `res.partner` : `maintenance_domain_ids` (M2m calculé, non stocké), `maintenance_domain_count`, `action_view_maintenance_domains()` ; champs réservés au groupe `maintenance.group_equipment_manager`.

- [ ] **Step 1: Écrire les nouveaux tests**

`maintenance_sw_base/tests/__init__.py` — ajouter `from . import test_host_customer`.

`maintenance_sw_base/tests/test_host_customer.py` :

```python
from odoo.tests import TransactionCase


class TestHostCustomer(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Equipment = cls.env["maintenance.equipment"]
        Host = cls.env["maintenance.host"]
        Partner = cls.env["res.partner"]
        cls.h1 = Host.create({"name": "vps-1"})
        cls.h2 = Host.create({"name": "vps-2"})
        cls.c1 = Partner.create({"name": "Customer One", "is_company": True})
        cls.c1_contact = Partner.create({"name": "Jane", "parent_id": cls.c1.id})
        cls.c2 = Partner.create({"name": "Customer Two", "is_company": True})
        cls.os = cls.Equipment.create({
            "name": "Debian", "equipment_kind": "software",
            "host_id": cls.h1.id, "customer_id": cls.c1.id,
        })
        cls.stack = cls.Equipment.create(
            {"name": "Stack", "equipment_kind": "software", "parent_id": cls.os.id}
        )
        cls.container = cls.Equipment.create(
            {"name": "Container", "equipment_kind": "software", "parent_id": cls.stack.id}
        )

    def test_children_inherit_host_and_customer(self):
        self.assertEqual(self.container.physical_host_id, self.h1)
        self.assertEqual(self.container.effective_customer_id, self.c1)
        self.assertFalse(self.container.host_id)
        self.assertFalse(self.container.customer_id)

    def test_forced_value_on_child_survives_parent_change(self):
        self.stack.write({"host_id": self.h2.id, "customer_id": self.c2.id})
        h3 = self.env["maintenance.host"].create({"name": "vps-3"})
        self.os.write({"host_id": h3.id, "customer_id": self.c1_contact.id})
        self.assertEqual(self.container.physical_host_id, self.h2)
        self.assertEqual(self.container.effective_customer_id, self.c2)

    def test_parent_change_propagates(self):
        self.os.write({"host_id": self.h2.id, "customer_id": self.c2.id})
        self.assertEqual(self.container.physical_host_id, self.h2)
        self.assertEqual(self.container.effective_customer_id, self.c2)

    def test_reparenting_changes_inherited_values(self):
        other = self.Equipment.create(
            {"name": "Ubuntu", "equipment_kind": "software", "host_id": self.h2.id}
        )
        self.container.parent_id = other
        self.assertEqual(self.container.physical_host_id, self.h2)
        self.assertFalse(self.container.effective_customer_id)

    def test_clearing_forced_value_falls_back_to_parent(self):
        self.stack.host_id = self.h2
        self.stack.host_id = False
        self.assertEqual(self.container.physical_host_id, self.h1)

    def test_needs_attachment_inherited_host(self):
        self.assertFalse(self.container.needs_attachment)
        self.os.host_id = False
        self.assertTrue(self.container.needs_attachment)

    def test_needs_attachment_parent_without_host(self):
        hardware = self.Equipment.create({"name": "Box"})
        software = self.Equipment.create(
            {"name": "App", "equipment_kind": "software", "parent_id": hardware.id}
        )
        self.assertTrue(software.needs_attachment)

    def test_owner_domains(self):
        domain = self.env["maintenance.domain"].create({"name": "one.fr", "partner_id": self.c1.id})
        self.assertIn(domain, self.c1.maintenance_domain_ids)
        self.assertNotIn(domain, self.c2.maintenance_domain_ids)

    def test_domains_through_equipment(self):
        domain = self.env["maintenance.domain"].create(
            {"name": "served.fr", "equipment_ids": [(4, self.container.id)]}
        )
        self.assertIn(domain, self.c1.maintenance_domain_ids)
        self.assertEqual(self.c1.maintenance_domain_count, 1)
        self.assertNotIn(domain, self.c2.maintenance_domain_ids)

    def test_domains_through_company_contact(self):
        owned = self.env["maintenance.domain"].create({"name": "owned.fr", "partner_id": self.c1.id})
        served = self.env["maintenance.domain"].create(
            {"name": "served.fr", "equipment_ids": [(4, self.container.id)]}
        )
        self.assertEqual(self.c1_contact.maintenance_domain_ids, owned | served)
        action = self.c1_contact.action_view_maintenance_domains()
        self.assertEqual(self.env["maintenance.domain"].search(action["domain"]), owned | served)

    def test_equipment_domain_ids_reverse(self):
        domain = self.env["maintenance.domain"].create({"name": "rev.fr"})
        self.container.domain_ids = [(4, domain.id)]
        self.assertEqual(domain.equipment_ids, self.container)

    def test_host_software_count(self):
        self.env.invalidate_all()
        self.assertEqual(self.h1.software_count, 3)
        action = self.h1.action_view_software()
        self.assertEqual(self.Equipment.search(action["domain"]), self.os | self.stack | self.container)
```

- [ ] **Step 2: Adapter deux tests existants à la nouvelle règle**

Dans `maintenance_sw_base/tests/test_equipment.py` :
- dans `setUpClass`, ajouter après `cls.vps = ...` :

```python
        cls.host = cls.env["maintenance.host"].create({"name": "vps-host-test"})
```

- remplacer `test_software_with_parent_does_not_need_attachment` par :

```python
    def test_software_with_host_does_not_need_attachment(self):
        software = self._software(host_id=self.host.id, deployment_method_id=self.method_0k.id)
        self.assertFalse(software.needs_attachment)
```

- remplacer `test_needs_attachment_recomputed_when_parent_set` par :

```python
    def test_needs_attachment_recomputed_when_host_set(self):
        software = self._software(deployment_method_id=self.method_0k.id)
        software.host_id = self.host
        self.assertFalse(software.needs_attachment)
```

- [ ] **Step 3: Lancer pour voir l'échec**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `RESULT: FAILED` (champ `host_id` inexistant).

- [ ] **Step 4: Implémenter**

Dans `maintenance_sw_base/models/maintenance_equipment.py`, ajouter les champs après `install_path` et remplacer `needs_attachment` et son calcul :

```python
    host_id = fields.Many2one(
        "maintenance.host",
        string="Set Physical Host",
        ondelete="restrict",
        tracking=True,
        help="Physical host of this equipment, when it is not the one of its parent.",
    )
    physical_host_id = fields.Many2one(
        "maintenance.host",
        string="Physical Host",
        compute="_compute_physical_host_id",
        store=True,
        recursive=True,
        index=True,
        help="The set physical host, or else the one of the parent equipment.",
    )
    customer_id = fields.Many2one(
        "res.partner",
        string="Set Customer",
        tracking=True,
        help="Customer of this equipment, when it is not the one of its parent.",
    )
    effective_customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
        compute="_compute_effective_customer_id",
        store=True,
        recursive=True,
        index=True,
        help="The set customer, or else the one of the parent equipment.",
    )
    domain_ids = fields.Many2many(
        "maintenance.domain",
        "maintenance_domain_equipment_rel",
        "equipment_id",
        "domain_id",
        string="Domain Names",
    )
    needs_attachment = fields.Boolean(
        "To Attach",
        compute="_compute_needs_attachment",
        store=True,
        help="Software with no physical host (set on it or on a parent) whose deployment "
        "method is not managed by the provider.",
    )

    @api.depends("host_id", "parent_id.physical_host_id")
    def _compute_physical_host_id(self):
        for equipment in self:
            equipment.physical_host_id = equipment.host_id or equipment.parent_id.physical_host_id

    @api.depends("customer_id", "parent_id.effective_customer_id")
    def _compute_effective_customer_id(self):
        for equipment in self:
            equipment.effective_customer_id = (
                equipment.customer_id or equipment.parent_id.effective_customer_id
            )

    @api.depends(
        "equipment_kind", "physical_host_id", "deployment_method_id.managed_by_provider"
    )
    def _compute_needs_attachment(self):
        for equipment in self:
            equipment.needs_attachment = (
                equipment.equipment_kind == "software"
                and not equipment.physical_host_id
                and not equipment.deployment_method_id.managed_by_provider
            )
```

(Supprimer l'ancienne définition de `needs_attachment` et l'ancien `_compute_needs_attachment` fondé sur `parent_id`.)

Dans `maintenance_sw_base/models/maintenance_host.py`, ajouter `api` et `_` aux imports (`from odoo import _, api, fields, models`) et, dans la classe :

```python
    software_ids = fields.One2many(
        "maintenance.equipment", "physical_host_id", string="Software"
    )
    software_count = fields.Integer(compute="_compute_software_count")

    @api.depends("software_ids")
    def _compute_software_count(self):
        for host in self:
            host.software_count = len(host.software_ids)

    def action_view_software(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Software"),
            "res_model": "maintenance.equipment",
            "view_mode": "list,form",
            "domain": [("physical_host_id", "=", self.id)],
            "context": {"default_equipment_kind": "software", "default_host_id": self.id},
        }
```

`maintenance_sw_base/models/res_partner.py` :

```python
from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    maintenance_domain_ids = fields.Many2many(
        "maintenance.domain",
        compute="_compute_maintenance_domain_ids",
        string="Domain Names",
        groups="maintenance.group_equipment_manager",
    )
    maintenance_domain_count = fields.Integer(
        compute="_compute_maintenance_domain_ids",
        groups="maintenance.group_equipment_manager",
    )

    def _maintenance_domain_domain(self):
        """Domains owned by the commercial partner, or served by its equipment."""
        self.ensure_one()
        commercial_id = self.commercial_partner_id._origin.id
        if not commercial_id:
            return [("id", "=", False)]
        return [
            "|",
            ("partner_id.commercial_partner_id", "=", commercial_id),
            ("equipment_ids.effective_customer_id.commercial_partner_id", "=", commercial_id),
        ]

    def _compute_maintenance_domain_ids(self):
        Domain = self.env["maintenance.domain"]
        for partner in self:
            domains = Domain.search(partner._maintenance_domain_domain())
            partner.maintenance_domain_ids = domains
            partner.maintenance_domain_count = len(domains)

    def action_view_maintenance_domains(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Domain Names"),
            "res_model": "maintenance.domain",
            "view_mode": "list,form",
            "domain": self._maintenance_domain_domain(),
            "context": {"default_partner_id": self.commercial_partner_id.id},
        }
```

`maintenance_sw_base/models/__init__.py` — ajouter `from . import res_partner`.

- [ ] **Step 5: Lancer les tests**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `0 failed, 0 error(s) of 44 tests`, `RESULT: OK`.

- [ ] **Step 6: Vérifier que le module Docker passe toujours**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_docker`
Expected: `0 failed, 0 error(s) of 50 tests`, `RESULT: OK`.

- [ ] **Step 7: Commit**

```bash
git add maintenance_sw_base
git commit -m "maintenance_sw_base : support physique et client hérités du parent, domaines d'un client"
```

---

### Task 3: Vues, menus et traduction (`maintenance_sw_base`)

**Files:**
- Create: `maintenance_sw_base/views/maintenance_host_views.xml`, `maintenance_sw_base/views/maintenance_domain_views.xml`, `maintenance_sw_base/views/res_partner_views.xml`
- Modify: `maintenance_sw_base/views/maintenance_equipment_views.xml`, `maintenance_sw_base/views/menus.xml`, `maintenance_sw_base/__manifest__.py` (`data`), `maintenance_sw_base/i18n/maintenance_sw_base.pot`, `maintenance_sw_base/i18n/fr.po`
- Test: `maintenance_sw_base/tests/test_data.py`

**Interfaces:**
- Consumes: champs des Tâches 1–2 ; `base.view_partner_form` (`div[@name='button_box']`).
- Produces: actions `maintenance_sw_base.maintenance_host_action`, `maintenance_sw_base.maintenance_domain_action` ; menus `menu_maintenance_host`, `menu_maintenance_domain` ; vues `maintenance_host_view_form`, `maintenance_domain_view_form` (étendues par la Tâche 5).

- [ ] **Step 1: Écrire les tests**

Ajouter à `maintenance_sw_base/tests/test_data.py`, dans la classe existante :

```python
    def test_equipment_form_shows_host_customer_domains(self):
        arch = self.env["maintenance.equipment"].get_view(view_type="form")["arch"]
        for field in ("physical_host_id", "host_id", "effective_customer_id", "customer_id", "domain_ids"):
            self.assertIn(f'name="{field}"', arch)

    def test_host_and_domain_menus(self):
        parent = self.env.ref("maintenance_sw_base.menu_sw_config")
        self.assertEqual(self.env.ref("maintenance_sw_base.menu_maintenance_host").parent_id, parent)
        self.assertEqual(self.env.ref("maintenance_sw_base.menu_maintenance_domain").parent_id, parent)
```

- [ ] **Step 2: Lancer pour voir l'échec**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `RESULT: FAILED`.

- [ ] **Step 3: Vues des supports physiques**

`maintenance_sw_base/views/maintenance_host_views.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="maintenance_host_view_list" model="ir.ui.view">
        <field name="name">maintenance.host.list</field>
        <field name="model">maintenance.host</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="host_type"/>
                <field name="provider_id"/>
                <field name="equipment_id" optional="hide"/>
                <field name="location" optional="hide"/>
                <field name="software_count"/>
            </list>
        </field>
    </record>

    <record id="maintenance_host_view_form" model="ir.ui.view">
        <field name="name">maintenance.host.form</field>
        <field name="model">maintenance.host</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <div class="oe_button_box" name="button_box">
                        <button name="action_view_software" type="object"
                                class="oe_stat_button" icon="fa-cubes">
                            <field name="software_count" widget="statinfo" string="Software"/>
                        </button>
                    </div>
                    <widget name="web_ribbon" title="Archived" bg_color="text-bg-danger" invisible="active"/>
                    <div class="oe_title">
                        <h1><field name="name" placeholder="e.g. vps-1234 (OVH)"/></h1>
                    </div>
                    <group>
                        <group name="main">
                            <field name="host_type"/>
                            <field name="provider_id"/>
                            <field name="active" invisible="1"/>
                        </group>
                        <group name="location">
                            <field name="equipment_id"/>
                            <field name="location"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Notes" name="notes">
                            <field name="note"/>
                        </page>
                    </notebook>
                </sheet>
            </form>
        </field>
    </record>

    <record id="maintenance_host_view_search" model="ir.ui.view">
        <field name="name">maintenance.host.search</field>
        <field name="model">maintenance.host</field>
        <field name="arch" type="xml">
            <search>
                <field name="name"/>
                <field name="provider_id"/>
                <filter string="Archived" name="inactive" domain="[('active', '=', False)]"/>
                <group expand="0" string="Group By">
                    <filter string="Provider" name="group_provider" context="{'group_by': 'provider_id'}"/>
                    <filter string="Type" name="group_type" context="{'group_by': 'host_type'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="maintenance_host_action" model="ir.actions.act_window">
        <field name="name">Physical Hosts</field>
        <field name="res_model">maintenance.host</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 4: Vues des noms de domaine**

`maintenance_sw_base/views/maintenance_domain_views.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="maintenance_domain_view_list" model="ir.ui.view">
        <field name="name">maintenance.domain.list</field>
        <field name="model">maintenance.domain</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="partner_id"/>
                <field name="registrar_id"/>
                <field name="expiration_date"/>
                <field name="auto_renew"/>
                <field name="equipment_ids" widget="many2many_tags" optional="show"/>
            </list>
        </field>
    </record>

    <record id="maintenance_domain_view_form" model="ir.ui.view">
        <field name="name">maintenance.domain.form</field>
        <field name="model">maintenance.domain</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <widget name="web_ribbon" title="Archived" bg_color="text-bg-danger" invisible="active"/>
                    <div class="oe_title">
                        <h1><field name="name" placeholder="e.g. example.fr"/></h1>
                    </div>
                    <group>
                        <group name="owner">
                            <field name="partner_id"/>
                            <field name="registrar_id"/>
                            <field name="active" invisible="1"/>
                        </group>
                        <group name="renewal">
                            <field name="expiration_date"/>
                            <field name="auto_renew"/>
                        </group>
                    </group>
                    <group>
                        <field name="equipment_ids" widget="many2many_tags"/>
                    </group>
                    <notebook>
                        <page string="Notes" name="notes">
                            <field name="note"/>
                        </page>
                    </notebook>
                </sheet>
            </form>
        </field>
    </record>

    <record id="maintenance_domain_view_search" model="ir.ui.view">
        <field name="name">maintenance.domain.search</field>
        <field name="model">maintenance.domain</field>
        <field name="arch" type="xml">
            <search>
                <field name="name"/>
                <field name="partner_id"/>
                <field name="registrar_id"/>
                <field name="equipment_ids"/>
                <filter string="Archived" name="inactive" domain="[('active', '=', False)]"/>
                <group expand="0" string="Group By">
                    <filter string="Owner" name="group_owner" context="{'group_by': 'partner_id'}"/>
                    <filter string="Registrar" name="group_registrar" context="{'group_by': 'registrar_id'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="maintenance_domain_action" model="ir.actions.act_window">
        <field name="name">Domain Names</field>
        <field name="res_model">maintenance.domain</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 5: Bouton sur la fiche contact**

`maintenance_sw_base/views/res_partner_views.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_partner_form" model="ir.ui.view">
        <field name="name">res.partner.form.maintenance.domain</field>
        <field name="model">res.partner</field>
        <field name="inherit_id" ref="base.view_partner_form"/>
        <field name="arch" type="xml">
            <div name="button_box" position="inside">
                <button name="action_view_maintenance_domains" type="object"
                        class="oe_stat_button" icon="fa-globe"
                        groups="maintenance.group_equipment_manager">
                    <field name="maintenance_domain_count" widget="statinfo" string="Domain Names"/>
                </button>
            </div>
        </field>
    </record>
</odoo>
```

- [ ] **Step 6: Formulaire, liste et recherche des équipements**

Dans `maintenance_sw_base/views/maintenance_equipment_views.xml` :

- remplacer le texte de l'alerte par :

```xml
                <div class="alert alert-warning" role="alert" invisible="not needs_attachment">
                    This software has no physical host: set it on this software or on one of its
                    parents, or use a deployment method managed by the provider.
                </div>
```

- remplacer `<field name="equipment_kind" widget="radio" options="{'horizontal': true}"/>` (dans le bloc `category_id position="after"`) par :

```xml
                <field name="equipment_kind" widget="radio" options="{'horizontal': true}"/>
                <field name="effective_customer_id"/>
                <field name="customer_id" placeholder="Inherited from the parent"/>
```

- remplacer **toute** la page `software` (de `<page string="Software" name="software" ...>` à son `</page>`) par :

```xml
                <page string="Software" name="software" invisible="equipment_kind != 'software'">
                    <group>
                        <group>
                            <field name="install_type"/>
                            <field name="deployment_method_id"/>
                            <field name="install_path"/>
                        </group>
                        <group>
                            <field name="software_product_id"/>
                            <field name="software_version_id"/>
                            <field name="version_note"/>
                            <field name="physical_host_id"/>
                            <field name="host_id" placeholder="Inherited from the parent"/>
                            <field name="needs_attachment" invisible="1"/>
                        </group>
                    </group>
                    <group>
                        <field name="domain_ids" widget="many2many_tags"/>
                    </group>
                </page>
```

- dans la liste (`hr_equipment_view_tree`), ajouter après `deployment_method_id` :

```xml
                <field name="physical_host_id" optional="show"/>
                <field name="effective_customer_id" optional="show"/>
```

- dans la recherche, ajouter après `<field name="software_version_id"/>` (bloc `category_id position="after"`) :

```xml
                <field name="physical_host_id"/>
                <field name="effective_customer_id"/>
                <field name="domain_ids"/>
```

  et après le filtre `group_install_type` :

```xml
                <filter string="Physical Host" name="group_physical_host" context="{'group_by': 'physical_host_id'}"/>
                <filter string="Customer" name="group_customer" context="{'group_by': 'effective_customer_id'}"/>
```

- [ ] **Step 7: Menus et manifeste**

Ajouter à `maintenance_sw_base/views/menus.xml` :

```xml
    <menuitem id="menu_maintenance_host" action="maintenance_host_action"
              parent="menu_sw_config" sequence="35"/>
    <menuitem id="menu_maintenance_domain" action="maintenance_domain_action"
              parent="menu_sw_config" sequence="36"/>
```

Dans `maintenance_sw_base/__manifest__.py`, la clé `data` devient :

```python
    "data": [
        "security/ir.model.access.csv",
        "data/software_deployment_method_data.xml",
        "views/software_product_views.xml",
        "views/software_version_views.xml",
        "views/software_deployment_method_views.xml",
        "views/maintenance_host_views.xml",
        "views/maintenance_domain_views.xml",
        "views/maintenance_equipment_views.xml",
        "views/res_partner_views.xml",
        "views/menus.xml",
    ],
```

- [ ] **Step 8: Lancer les tests**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `0 failed, 0 error(s) of 46 tests`, `RESULT: OK`.

- [ ] **Step 9: Traduction**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh export maintenance_sw_base`, vérifier que le `.pot` est réécrit, puis reporter dans `fr.po` **chaque** nouveau msgid (msgids identiques au `.pot`, 0 msgstr vide), en gardant les traductions existantes. Glossaire :

| Anglais | Français |
|---|---|
| Physical Host(s) / Set Physical Host | Support(s) physique(s) / Support physique forcé |
| Physical Server / VPS / Virtual Machine / Shared Hosting / Other | Serveur physique / VPS / Machine virtuelle / Hébergement mutualisé / Autre |
| Provider / Hardware Equipment / Location | Hébergeur / Équipement matériel / Emplacement |
| Domain Name(s) / Registrar / Owner / Served By | Nom(s) de domaine / Registrar / Propriétaire / Servi par |
| Automatic Renewal / Expiration Date | Renouvellement automatique / Date d'expiration |
| Customer / Set Customer | Client / Client forcé |
| Inherited from the parent | Hérité du parent |
| Software (bouton, action, champ `software_ids`) | Logiciels |

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh lang maintenance_sw_base` puis vérifier dans `/tmp/swtest-maintenance_sw_base.log` la ligne de chargement de `maintenance_sw_base/i18n/fr.po`.
Expected: `RESULT: OK`.

- [ ] **Step 10: Commit**

```bash
git add maintenance_sw_base
git commit -m "maintenance_sw_base : vues des supports physiques, des noms de domaine et des clients, traduction"
```

---

### Task 4: Contexte dans l'onglet Docker (`maintenance_sw_docker`)

**Files:**
- Modify: `maintenance_sw_docker/views/maintenance_equipment_views.xml`
- Test: `maintenance_sw_docker/tests/test_views.py`

**Interfaces:**
- Consumes: `physical_host_id`, `effective_customer_id` (Tâche 2).

- [ ] **Step 1: Écrire le test**

Ajouter à la classe de `maintenance_sw_docker/tests/test_views.py` (et `from lxml import etree` en tête du fichier) :

```python
    def test_docker_page_shows_host_and_customer(self):
        arch = etree.fromstring(self.env["maintenance.equipment"].get_view(view_type="form")["arch"])
        page = arch.xpath("//page[@name='docker']")[0]
        for field in ("physical_host_id", "effective_customer_id"):
            nodes = page.xpath(f".//field[@name='{field}']")
            self.assertTrue(nodes, field)
            self.assertEqual(nodes[0].get("readonly"), "1")
```

- [ ] **Step 2: Lancer pour voir l'échec**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_docker`
Expected: `RESULT: FAILED` (1 failed).

- [ ] **Step 3: Implémenter**

Dans la page `docker`, après le `<group>` qui contient `docker_image_id` / `container_name`, remplacer ce groupe par :

```xml
                    <group>
                        <group>
                            <field name="docker_image_id"/>
                            <field name="container_name"/>
                        </group>
                        <group>
                            <field name="physical_host_id" readonly="1"/>
                            <field name="effective_customer_id" readonly="1"/>
                        </group>
                    </group>
```

- [ ] **Step 4: Lancer les tests**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_docker`
Expected: `0 failed, 0 error(s) of 51 tests`, `RESULT: OK`.

- [ ] **Step 5: Commit**

```bash
git add maintenance_sw_docker
git commit -m "maintenance_sw_docker : support physique et client effectifs dans l'onglet Docker"
```

---

### Task 5: Module pont `maintenance_hosting_ovh`

**Files:**
- Create: `maintenance_hosting_ovh/__init__.py`, `__manifest__.py`, `hooks.py`, `data/res_partner_data.xml`, `models/__init__.py`, `models/maintenance_host.py`, `models/maintenance_domain.py`, `models/ovh_service.py`, `views/maintenance_host_views.xml`, `views/maintenance_domain_views.xml`, `views/ovh_service_views.xml`, `i18n/maintenance_hosting_ovh.pot`, `i18n/fr.po`, `tests/__init__.py`, `tests/test_ovh_link.py`

**Interfaces:**
- Consumes: `maintenance.host`, `maintenance.domain` (`_normalize_name`), vues `maintenance_sw_base.maintenance_host_view_form` / `maintenance_domain_view_form` (groupes `name="main"` et `name="renewal"`) ; `ovh.service._upsert(account, kind, service_name, payload) -> (service, is_new)`, `ovh.service.write`, champs `kind`, `service_name`, `display_name_ovh`, `expiration_date`, `renew_automatic`, `contact_admin`, `active` ; `res.partner.ovh_nic_handle` ; vue `ovh_api.ovh_service_view_form` (`div[@name='button_box']`) ; groupe `ovh_api.group_ovh_user`, `ovh_api.group_ovh_operator`.
- Produces: `maintenance.host.ovh_service_id`, `maintenance.host.ovh_expiration_date`, `maintenance.domain.ovh_service_id`, `maintenance.domain.is_ovh_managed` ; `ovh.service._sync_maintenance_link()`, `maintenance_host_ids`, `maintenance_domain_ids` ; partenaire `maintenance_hosting_ovh.partner_ovhcloud` ; `post_init_hook(env)`.

- [ ] **Step 1: Écrire les tests**

`maintenance_hosting_ovh/tests/__init__.py` :

```python
from . import test_ovh_link
```

`maintenance_hosting_ovh/tests/test_ovh_link.py` :

```python
from odoo.tests import TransactionCase, new_test_user

from odoo.addons.maintenance_hosting_ovh.hooks import post_init_hook


def payload(name, expiration="2027-06-09", automatic=True, admin="pa1413842-ovh"):
    return {
        "detail": {"displayName": name},
        "serviceInfos": {
            "status": "ok",
            "expiration": expiration,
            "renew": {"automatic": automatic},
            "contactAdmin": admin,
        },
    }


class TestOvhLink(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Service = cls.env["ovh.service"]
        cls.Host = cls.env["maintenance.host"].with_context(active_test=False)
        cls.Domain = cls.env["maintenance.domain"].with_context(active_test=False)
        cls.account = cls.env["ovh.account"].create(
            {"name": "OVH test", "application_key": "k", "application_secret": "s"}
        )
        cls.ovhcloud = cls.env.ref("maintenance_hosting_ovh.partner_ovhcloud")

    def _sync(self, kind, name, **kwargs):
        service, _is_new = self.Service._upsert(self.account, kind, name, payload(name, **kwargs))
        return service

    def test_vps_creates_host_once(self):
        service = self._sync("vps", "vps-d4d16c17.vps.ovh.net")
        self._sync("vps", "vps-d4d16c17.vps.ovh.net")
        host = self.Host.search([("ovh_service_id", "=", service.id)])
        self.assertEqual(len(host), 1)
        self.assertEqual(host.host_type, "vps")
        self.assertEqual(host.provider_id, self.ovhcloud)
        self.assertEqual(host.name, "vps-d4d16c17.vps.ovh.net")
        self.assertEqual(service.maintenance_host_ids, host)

    def test_dedicated_and_hosting_types(self):
        dedicated = self._sync("dedicated", "ns3148992.ip-51-91-6.eu")
        hosting = self._sync("hosting", "example.com")
        self.assertEqual(self.Host.search([("ovh_service_id", "=", dedicated.id)]).host_type, "physical")
        self.assertEqual(self.Host.search([("ovh_service_id", "=", hosting.id)]).host_type, "shared_hosting")

    def test_domain_created_with_expiration(self):
        service = self._sync("domain", "Example.FR", expiration="2027-06-09", automatic=True)
        domain = self.Domain.search([("ovh_service_id", "=", service.id)])
        self.assertEqual(domain.name, "example.fr")
        self.assertEqual(str(domain.expiration_date), "2027-06-09")
        self.assertTrue(domain.auto_renew)
        self.assertEqual(domain.registrar_id, self.ovhcloud)
        self.assertTrue(domain.is_ovh_managed)

    def test_domain_values_refreshed_on_resync(self):
        service = self._sync("domain", "example.fr", expiration="2027-06-09", automatic=True)
        self._sync("domain", "example.fr", expiration="2028-06-09", automatic=False)
        domain = self.Domain.search([("ovh_service_id", "=", service.id)])
        self.assertEqual(str(domain.expiration_date), "2028-06-09")
        self.assertFalse(domain.auto_renew)

    def test_manual_domain_is_linked_not_duplicated(self):
        alwaysdata = self.env["res.partner"].create({"name": "Registrar X", "is_company": True})
        manual = self.Domain.create({"name": " Example.fr. ", "registrar_id": alwaysdata.id})
        service = self._sync("domain", "example.fr")
        self.assertEqual(self.Domain.search([("name", "=", "example.fr")]), manual)
        self.assertEqual(manual.ovh_service_id, service)
        self.assertEqual(manual.registrar_id, alwaysdata, "an existing registrar is kept")

    def test_owner_guessed_from_nic_handle(self):
        company = self.env["res.partner"].create({"name": "Client SA", "is_company": True})
        self.env["res.partner"].create(
            {"name": "Boss", "parent_id": company.id, "ovh_nic_handle": "ab12345-ovh"}
        )
        service = self._sync("domain", "client.fr", admin="AB12345-ovh")
        self.assertEqual(self.Domain.search([("ovh_service_id", "=", service.id)]).partner_id, company)

    def test_owner_not_overwritten(self):
        owner = self.env["res.partner"].create({"name": "Owner", "is_company": True})
        self.env["res.partner"].create({"name": "Other", "ovh_nic_handle": "cd67890-ovh"})
        manual = self.Domain.create({"name": "kept.fr", "partner_id": owner.id})
        self._sync("domain", "kept.fr", admin="cd67890-ovh")
        self.assertEqual(manual.partner_id, owner)

    def test_other_kinds_create_nothing(self):
        hosts, domains = self.Host.search_count([]), self.Domain.search_count([])
        self._sync("email_mxplan", "mxplan-test-1")
        self._sync("telephony_account", "pa1413842-ovh-1")
        self.assertEqual(self.Host.search_count([]), hosts)
        self.assertEqual(self.Domain.search_count([]), domains)

    def test_archive_and_restore_follow_service(self):
        vps = self._sync("vps", "vps-1.vps.ovh.net")
        dom = self._sync("domain", "gone.fr")
        (vps | dom).write({"state": "terminated", "active": False})
        host = self.Host.search([("ovh_service_id", "=", vps.id)])
        domain = self.Domain.search([("ovh_service_id", "=", dom.id)])
        self.assertFalse(host.active)
        self.assertFalse(domain.active)
        self._sync("vps", "vps-1.vps.ovh.net")
        self._sync("domain", "gone.fr")
        self.assertTrue(host.active)
        self.assertTrue(domain.active)

    def test_post_init_hook_links_existing_services(self):
        service = self.Service.create({
            "account_id": self.account.id, "kind": "vps", "service_name": "vps-old.vps.ovh.net",
        })
        archived = self.Service.create({
            "account_id": self.account.id, "kind": "domain", "service_name": "old.fr", "active": False,
        })
        post_init_hook(self.env)
        self.assertTrue(self.Host.search([("ovh_service_id", "=", service.id)]))
        domain = self.Domain.search([("ovh_service_id", "=", archived.id)])
        self.assertTrue(domain)
        self.assertFalse(domain.active)

    def test_sync_by_ovh_operator_without_maintenance_rights(self):
        operator = new_test_user(
            self.env, login="ovh-operator", groups="base.group_user,ovh_api.group_ovh_operator"
        )
        self.assertFalse(operator.has_group("maintenance.group_equipment_manager"))
        Service = self.Service.with_user(operator)
        service, _is_new = Service._upsert(
            self.account.with_user(operator), "domain", "operator.fr", payload("operator.fr")
        )
        self.assertTrue(self.Domain.search([("ovh_service_id", "=", service.id)]))
```

- [ ] **Step 2: Squelette du module et échec attendu**

`maintenance_hosting_ovh/__init__.py` :

```python
from . import models
from .hooks import post_init_hook
```

`maintenance_hosting_ovh/__manifest__.py` :

```python
# maintenance_hosting_ovh/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Maintenance - OVHcloud Hosting",
    "version": "18.0.1.0.0",
    "summary": "Physical hosts and domain names from the OVHcloud services synchronized by ovh_api",
    "description": """
Maintenance - OVHcloud Hosting
==============================

Bridges ovh_api and the maintenance software inventory: each synchronized OVH VPS, dedicated
server or web hosting becomes a physical host, each OVH domain a domain name (expiration and
renewal kept up to date). Services that disappear from OVH archive their host or domain.
""",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "category": "Manufacturing/Maintenance",
    "depends": ["maintenance_sw_base", "ovh_api"],
    "data": [
        "data/res_partner_data.xml",
        "views/maintenance_host_views.xml",
        "views/maintenance_domain_views.xml",
        "views/ovh_service_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "license": "AGPL-3",
    "installable": True,
    "application": False,
}
```

`maintenance_hosting_ovh/hooks.py` :

```python
def post_init_hook(env):
    """Link the OVH services synchronized before the module was installed."""
    env["ovh.service"].with_context(active_test=False).search([])._sync_maintenance_link()
```

`maintenance_hosting_ovh/models/__init__.py` :

```python
from . import maintenance_host
from . import maintenance_domain
from . import ovh_service
```

Créer des fichiers modèles et vues vides valides n'a pas d'intérêt : écrire directement le Step 3, puis lancer les tests une première fois **avant** d'écrire `models/ovh_service.py` (créer ce fichier avec seulement l'import et une classe vide `_inherit = "ovh.service"`) pour constater l'échec.

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_hosting_ovh`
Expected: `RESULT: FAILED` (pas d'objet lié, `maintenance_host_ids` inexistant).

- [ ] **Step 3: Implémenter**

`maintenance_hosting_ovh/data/res_partner_data.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="partner_ovhcloud" model="res.partner">
        <field name="name">OVHcloud</field>
        <field name="is_company" eval="True"/>
        <field name="website">https://www.ovhcloud.com</field>
    </record>
</odoo>
```

`maintenance_hosting_ovh/models/maintenance_host.py` :

```python
from odoo import fields, models


class MaintenanceHost(models.Model):
    _inherit = "maintenance.host"

    ovh_service_id = fields.Many2one(
        "ovh.service",
        string="OVH Service",
        ondelete="set null",
        index=True,
        groups="ovh_api.group_ovh_user",
    )
    ovh_expiration_date = fields.Date(
        related="ovh_service_id.expiration_date",
        string="OVH Expiration",
        groups="ovh_api.group_ovh_user",
    )

    _sql_constraints = [
        (
            "ovh_service_uniq",
            "unique(ovh_service_id)",
            "This OVH service is already linked to a physical host.",
        ),
    ]
```

`maintenance_hosting_ovh/models/maintenance_domain.py` :

```python
from odoo import api, fields, models


class MaintenanceDomain(models.Model):
    _inherit = "maintenance.domain"

    ovh_service_id = fields.Many2one(
        "ovh.service",
        string="OVH Service",
        ondelete="set null",
        index=True,
        groups="ovh_api.group_ovh_user",
    )
    is_ovh_managed = fields.Boolean(
        "Managed at OVH",
        compute="_compute_is_ovh_managed",
        store=True,
        help="Expiration and renewal come from OVH and are rewritten at each synchronization.",
    )

    _sql_constraints = [
        (
            "ovh_service_uniq",
            "unique(ovh_service_id)",
            "This OVH service is already linked to a domain name.",
        ),
    ]

    @api.depends("ovh_service_id")
    def _compute_is_ovh_managed(self):
        for domain in self.sudo():
            domain.is_ovh_managed = bool(domain.ovh_service_id)
```

`maintenance_hosting_ovh/models/ovh_service.py` :

```python
from odoo import _, fields, models

# OVH families that are a machine (or a shared hosting) software can run on.
HOST_TYPES = {
    "dedicated": "physical",
    "vps": "vps",
    "hosting": "shared_hosting",
}


class OvhService(models.Model):
    _inherit = "ovh.service"

    maintenance_host_ids = fields.One2many(
        "maintenance.host", "ovh_service_id", string="Physical Hosts"
    )
    maintenance_domain_ids = fields.One2many(
        "maintenance.domain", "ovh_service_id", string="Domain Names"
    )
    maintenance_link_count = fields.Integer(compute="_compute_maintenance_link_count")

    def _compute_maintenance_link_count(self):
        for service in self:
            service.maintenance_link_count = len(service.maintenance_host_ids) + len(
                service.maintenance_domain_ids
            )

    def _upsert(self, account, kind, service_name, payload):
        service, is_new = super()._upsert(account, kind, service_name, payload)
        service._sync_maintenance_link()
        return service, is_new

    def write(self, vals):
        res = super().write(vals)
        if "active" in vals:
            self._sync_maintenance_active()
        return res

    # The links are a consequence of the synchronization, which an OVH operator
    # may run without any right on the maintenance inventory: they are written
    # as superuser.
    def _sync_maintenance_link(self):
        ovhcloud = self.env.ref("maintenance_hosting_ovh.partner_ovhcloud")
        for service in self.sudo():
            if service.kind in HOST_TYPES:
                service._sync_maintenance_host(ovhcloud)
            elif service.kind == "domain":
                service._sync_maintenance_domain(ovhcloud)

    def _sync_maintenance_host(self, ovhcloud):
        self.ensure_one()
        Host = self.env["maintenance.host"].sudo().with_context(active_test=False)
        host = Host.search([("ovh_service_id", "=", self.id)], limit=1)
        if host:
            if host.active != self.active:
                host.active = self.active
            return host
        return Host.create({
            "name": self.display_name_ovh or self.service_name,
            "host_type": HOST_TYPES[self.kind],
            "provider_id": ovhcloud.id,
            "ovh_service_id": self.id,
            "active": self.active,
        })

    def _sync_maintenance_domain(self, ovhcloud):
        self.ensure_one()
        Domain = self.env["maintenance.domain"].sudo().with_context(active_test=False)
        domain = Domain.search([("ovh_service_id", "=", self.id)], limit=1)
        if not domain:
            # A domain typed by hand before the sync is the same domain: link it.
            domain = Domain.search(
                [("name", "=", Domain._normalize_name(self.service_name)),
                 ("ovh_service_id", "=", False)],
                limit=1,
            )
        values = {
            "expiration_date": self.expiration_date,
            "auto_renew": self.renew_automatic,
            "active": self.active,
        }
        if domain:
            values["ovh_service_id"] = self.id
            if not domain.registrar_id:
                values["registrar_id"] = ovhcloud.id
            domain.write(values)
        else:
            domain = Domain.create(dict(
                values, name=self.service_name, registrar_id=ovhcloud.id, ovh_service_id=self.id,
            ))
        if not domain.partner_id:
            owner = self._maintenance_owner()
            if owner:
                domain.partner_id = owner
        return domain

    def _maintenance_owner(self):
        """The customer whose OVH account is the administrative contact, if known."""
        self.ensure_one()
        nic = (self.contact_admin or "").strip().lower()
        if not nic:
            return self.env["res.partner"]
        partner = self.env["res.partner"].sudo().search([("ovh_nic_handle", "=", nic)], limit=1)
        return partner.commercial_partner_id

    def _sync_maintenance_active(self):
        for model in ("maintenance.host", "maintenance.domain"):
            records = self.env[model].sudo().with_context(active_test=False).search(
                [("ovh_service_id", "in", self.ids)]
            )
            for record in records:
                if record.active != record.ovh_service_id.active:
                    record.active = record.ovh_service_id.active

    def action_view_maintenance_links(self):
        self.ensure_one()
        if self.maintenance_host_ids:
            records, model = self.maintenance_host_ids, "maintenance.host"
        else:
            records, model = self.maintenance_domain_ids, "maintenance.domain"
        return {
            "type": "ir.actions.act_window",
            "name": _("Maintenance"),
            "res_model": model,
            "view_mode": "form",
            "res_id": records[:1].id,
        }
```

`maintenance_hosting_ovh/views/maintenance_host_views.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="maintenance_host_view_form" model="ir.ui.view">
        <field name="name">maintenance.host.form.ovh</field>
        <field name="model">maintenance.host</field>
        <field name="inherit_id" ref="maintenance_sw_base.maintenance_host_view_form"/>
        <field name="arch" type="xml">
            <group name="main" position="inside">
                <field name="ovh_service_id" groups="ovh_api.group_ovh_user"/>
                <field name="ovh_expiration_date" groups="ovh_api.group_ovh_user"/>
            </group>
        </field>
    </record>
</odoo>
```

`maintenance_hosting_ovh/views/maintenance_domain_views.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="maintenance_domain_view_form" model="ir.ui.view">
        <field name="name">maintenance.domain.form.ovh</field>
        <field name="model">maintenance.domain</field>
        <field name="inherit_id" ref="maintenance_sw_base.maintenance_domain_view_form"/>
        <field name="arch" type="xml">
            <group name="renewal" position="inside">
                <field name="is_ovh_managed"/>
                <field name="ovh_service_id" groups="ovh_api.group_ovh_user"/>
            </group>
            <field name="expiration_date" position="attributes">
                <attribute name="readonly">is_ovh_managed</attribute>
            </field>
            <field name="auto_renew" position="attributes">
                <attribute name="readonly">is_ovh_managed</attribute>
            </field>
        </field>
    </record>
</odoo>
```

`maintenance_hosting_ovh/views/ovh_service_views.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="ovh_service_view_form" model="ir.ui.view">
        <field name="name">ovh.service.form.maintenance</field>
        <field name="model">ovh.service</field>
        <field name="inherit_id" ref="ovh_api.ovh_service_view_form"/>
        <field name="arch" type="xml">
            <div name="button_box" position="inside">
                <button name="action_view_maintenance_links" type="object"
                        class="oe_stat_button" icon="fa-wrench"
                        invisible="not maintenance_link_count">
                    <field name="maintenance_link_count" widget="statinfo" string="Maintenance"/>
                </button>
            </div>
        </field>
    </record>
</odoo>
```

- [ ] **Step 4: Lancer les tests**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_hosting_ovh`
Expected: `0 failed, 0 error(s) of 11 tests`, `RESULT: OK`. Vérifier aussi : `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base` → 46/46.

- [ ] **Step 5: Traduction**

`run_sw_odoo.sh export maintenance_hosting_ovh` puis `fr.po` (même en-tête que `maintenance_sw_base/i18n/fr.po`, ligne `# 	* maintenance_hosting_ovh`, 0 msgstr vide). Glossaire : OVH Service → Service OVH ; OVH Expiration → Expiration OVH ; Managed at OVH → Géré chez OVH ; Maintenance → Maintenance ; Physical Hosts → Supports physiques ; Domain Names → Noms de domaine ; les messages de contrainte en français. `run_sw_odoo.sh lang maintenance_hosting_ovh` → `RESULT: OK`, ligne de chargement du `fr.po` présente dans le log.

- [ ] **Step 6: Commit**

```bash
git add maintenance_hosting_ovh
git commit -m "maintenance_hosting_ovh : supports physiques et noms de domaine alimentés par la synchronisation OVH"
```

---

### Task 6: Validation sur la copie neutralisée d'arpol.fr

**Files (hors dépôt, non commités):**
- Create: `~/arpol-test/seed_hosts_domains.py`, `~/arpol-test/screenshots_hosts.js`

**Interfaces:**
- Consumes: modules des Tâches 1–5 ; instance http://100.78.13.93:8070 (base `arpol_test`, conteneurs `arpol-test-odoo` / `arpol-test-pg`, worktree monté en lecture seule sur `/opt/odoo/auto/dev/ArPol-odoo-dev`, `ovh_api` sur `/opt/odoo/auto/dev/ovh_connector`) ; données saisies par `~/arpol-test/seed_arpol_server.py` : équipements « VPS arpol.fr » (matériel) → « Debian (arpol.fr) » → « Stack 0k myc-deploy » → « myc_odoo-v18_1 ».
- Produces: captures `~/arpol-test/hosts-*.png`, sortie de vérification.

**Attention :** `parent_id` du module OCA est `ondelete="cascade"` : supprimer « VPS arpol.fr » sans avoir d'abord détaché « Debian (arpol.fr) » supprimerait tout l'arbre. Toujours détacher avant de supprimer.

- [ ] **Step 1: Recharger le code et installer le pont**

```bash
docker restart arpol-test-odoo && sleep 30
```

puis, en XML-RPC (mot de passe `armand@arpol.fr` depuis Vaultwarden, item « ArPol.fr Odoo database ») : `ir.module.module.update_list`, `button_immediate_upgrade` sur `maintenance_sw_base` et `maintenance_sw_docker`, puis `button_immediate_install` sur `maintenance_hosting_ovh`. Vérifier les trois états `installed` et l'absence d'ERROR (hors « Some modules are not loaded ») dans `docker logs --since 10m arpol-test-odoo`.

- [ ] **Step 2: Script de reprise des données**

`~/arpol-test/seed_hosts_domains.py` (JSON-RPC, car la réponse brute OVH contient des `null` que XML-RPC ne transmet pas) :

```python
#!/usr/bin/env python3
"""Re-root the arpol.fr tree on its OVH physical host, set customers and domains (arpol_test)."""
import json
import os
import socket
import urllib.request

URL, DB, LOGIN = "http://100.78.13.93:8070/jsonrpc", "arpol_test", "armand@arpol.fr"
PASSWORD = os.environ["ODOO_PW"]


def rpc(service, method, *args):
    body = {"jsonrpc": "2.0", "method": "call", "params": {"service": service, "method": method, "args": args}}
    request = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    answer = json.loads(urllib.request.urlopen(request).read())
    if "error" in answer:
        raise SystemExit(answer["error"]["data"]["message"])
    return answer["result"]


UID = rpc("common", "login", DB, LOGIN, PASSWORD)


def call(model, method, *args, **kwargs):
    return rpc("object", "execute_kw", DB, UID, PASSWORD, model, method, list(args), kwargs)


def one(model, domain):
    ids = call(model, "search", domain, limit=1)
    if not ids:
        raise SystemExit(f"not found: {model} {domain}")
    return ids[0]


ip = socket.gethostbyname("arpol.fr")
vps = [s for s in call("ovh.service", "search_read", [("kind", "=", "vps")],
                       fields=["service_name", "raw_payload"])
       if ip in ((s["raw_payload"] or {}).get("ips") or [])]
if len(vps) != 1:
    raise SystemExit(f"expected one VPS with {ip}, got {[s['service_name'] for s in vps]}")
host = one("maintenance.host", [("ovh_service_id", "=", vps[0]["id"])])

debian = one("maintenance.equipment", [("name", "=", "Debian (arpol.fr)")])
stack = one("maintenance.equipment", [("name", "=", "Stack 0k myc-deploy")])
container = one("maintenance.equipment", [("name", "=", "myc_odoo-v18_1")])

# Detach first: parent_id is ondelete=cascade, deleting the parent would delete the tree.
call("maintenance.equipment", "write", [debian], {"parent_id": False, "host_id": host})
old_vps = call("maintenance.equipment", "search", [("name", "=", "VPS arpol.fr")])
if old_vps:
    children = call("maintenance.equipment", "search", [("parent_id", "in", old_vps)])
    if children:
        raise SystemExit(f"VPS arpol.fr still has children {children}, not deleting")
    call("maintenance.equipment", "unlink", old_vps)

company_partner = call("res.users", "read", [UID], fields=["company_id"])[0]["company_id"][0]
arpol = call("res.company", "read", [company_partner], fields=["partner_id"])[0]["partner_id"][0]
call("maintenance.equipment", "write", [stack], {"customer_id": arpol})

domain = one("maintenance.domain", [("name", "=", "arpol.fr")])
call("maintenance.equipment", "write", [container], {"domain_ids": [(4, domain)]})

row = call("maintenance.equipment", "read", [container],
           fields=["complete_name", "physical_host_id", "effective_customer_id", "needs_attachment", "domain_ids"])[0]
print("container:", row)
print("hosts:", call("maintenance.host", "search_count", []),
      "domains:", call("maintenance.domain", "search_count", []),
      "to attach:", call("maintenance.equipment", "search_count", [("needs_attachment", "=", True)]))
print("ArPol domains:", call("res.partner", "read", [arpol], fields=["maintenance_domain_ids"])[0])
print("host id:", host, "container id:", container, "arpol partner id:", arpol)
```

Run: `ODOO_PW=... python3 ~/arpol-test/seed_hosts_domains.py`
Expected : support effectif du conteneur = « arpol.fr » (VPS `vps-d4d16c17`), client effectif = partenaire de la société ArPol, `needs_attachment` faux, `domain_ids` contient arpol.fr ; `hosts: 12`, `domains: 16` (moins les éventuels archivés), `to attach: 0` ; les domaines ArPol contiennent arpol.fr.

- [ ] **Step 3: Contrôle visuel (Playwright)**

`~/arpol-test/screenshots_hosts.js` — même squelette de connexion que `~/arpol-test/screenshots.js` (lancé avec `NODE_PATH=$HOME/tools/playwright/node_modules`), captures pleine page de :
1. le conteneur (`/odoo/action-maintenance.hr_equipment_action/<container id>`), onglet « Logiciel » → `hosts-container-software.png`, onglet « Docker » → `hosts-container-docker.png` ;
2. le support (`/odoo/action-maintenance_sw_base.maintenance_host_action/<host id>`) → `hosts-host.png` ;
3. la liste des noms de domaine (`/odoo/action-maintenance_sw_base.maintenance_domain_action`) → `hosts-domains.png` ;
4. la fiche contact ArPol (`/odoo/contacts/<arpol partner id>`) → `hosts-partner.png`.

Expected : `no JS error` ; regarder chaque capture (outil Read) : client et support effectifs visibles, bouton « Logiciels » du support (≥ 3), domaines OVH listés avec registrar OVHcloud, bouton « Noms de domaine » sur la fiche ArPol.

- [ ] **Step 4: Compte rendu**

Rapport (hors dépôt) : sorties des Steps 1–3, captures décrites, écarts. Pas de commit, pas de push, conteneurs laissés en marche.
