# Inventaire logiciel dans la Maintenance — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter à Odoo 18 deux modules, `maintenance_sw_base` (logiciels comme équipements de maintenance, catalogue produits/versions/méthodes de déploiement) et `maintenance_sw_docker` (images Docker, montages, composants git, composants effectifs d'un conteneur).

**Architecture:** Un logiciel est un `maintenance.equipment` (`equipment_kind = software`) rattaché par le `parent_id` de l'OCA `maintenance_equipment_hierarchy`. Trois catalogues partagés (`software.product`, `software.version`, `software.deployment.method`) dans le module de base ; le module Docker ajoute `git.repository`, `docker.image`, `docker.mount`, `docker.component` et calcule sur l'équipement les composants effectifs (chaîne d'images puis montages).

**Tech Stack:** Odoo 18.0 Community (ORM Python, vues XML), OCA `maintenance` 18.0, tests `odoo.tests.TransactionCase`, exécution dans l'image Docker `odoo:18.0` + `postgres:16` jetable.

**Spec:** `docs/superpowers/specs/2026-10-04-maintenance-software-inventory-design.md`

## Global Constraints

- Dépôt : `~/dev/odoo/arpol-dev/ArPol-odoo-dev-18.0` (worktree, branche `18.0`), modules à la racine.
- Version des modules : `18.0.1.0.0` ; licence `AGPL-3` ; auteur `Armand Polmard` ; site `https://arpol.fr`.
- En-tête des `__manifest__.py` : même style que `ai_agent_session/__manifest__.py` (commentaire chemin + `@author: Armand Polmard (contact@arpol.fr)` + licence).
- Dépendances : `maintenance_sw_base` → `maintenance`, `maintenance_equipment_hierarchy` ; `maintenance_sw_docker` → `maintenance_sw_base`. Aucune dépendance Python externe.
- Code et libellés en anglais ; traduction française dans `<module>/i18n/fr.po` (+ `<module>.pot`).
- Droits : lecture pour `base.group_user`, tout pour `maintenance.group_equipment_manager` sur chaque nouveau modèle.
- Menus sous **Maintenance > Configuration > Software** (`maintenance.menu_maintenance_configuration`).
- Messages de commit en français, préfixés du nom du module (style du dépôt), **sans** ligne `Co-Authored-By` ni mention d'outil.
- Ne **pas** pousser sur `origin` ni installer sur arpol.fr dans ce plan : la dernière tâche valide sur une copie neutralisée locale ; push et déploiement sont des demandes distinctes d'Armand.

## Review Focus

- **Digest vide ou blanc** sur une image : traité comme « pas de digest » (`False`), deux images sans digest ne se heurtent pas à l'unicité (`repository`, `digest`). → test dans la Tâche 4.
- **Plusieurs versions « dernière » du même produit** créées en lot ou cochées ensemble : il en reste exactement une, la dernière du lot. → test dans la Tâche 1.
- **Version « dernière » déplacée vers un autre produit** : elle décoche la « dernière » du produit cible. → test dans la Tâche 1.
- **Composants sans `path`** : résolus par dépôt plutôt que tous fusionnés sous une clé vide. → test dans la Tâche 6.
- **Montage qui remplace un composant d'image parente déjà remplacé par l'image fille** (même `path`) : le remplacement se fait par clé, pas d'entrée en double. → test dans la Tâche 6.

---

## Structure des fichiers

```
maintenance_sw_base/
├── __init__.py
├── __manifest__.py
├── data/software_deployment_method_data.xml      # 5 méthodes livrées (noupdate)
├── i18n/maintenance_sw_base.pot, fr.po
├── models/
│   ├── __init__.py
│   ├── software_product.py                       # software.product
│   ├── software_version.py                       # software.version (+ is_latest exclusif)
│   ├── software_deployment_method.py             # software.deployment.method
│   └── maintenance_equipment.py                  # champs logiciel + needs_attachment
├── security/ir.model.access.csv
├── tests/
│   ├── __init__.py
│   ├── test_catalog.py
│   └── test_equipment.py
└── views/
    ├── software_product_views.xml
    ├── software_version_views.xml
    ├── software_deployment_method_views.xml
    ├── maintenance_equipment_views.xml
    └── menus.xml

maintenance_sw_docker/
├── __init__.py
├── __manifest__.py
├── i18n/maintenance_sw_docker.pot, fr.po
├── models/
│   ├── __init__.py
│   ├── git_repository.py                         # git.repository
│   ├── docker_image.py                           # docker.image (+ _image_chain)
│   ├── docker_mount.py                           # docker.mount
│   ├── docker_component.py                       # docker.component (+ _effective_key)
│   └── maintenance_equipment.py                  # image, montages, composants effectifs, version issue de l'image
├── security/ir.model.access.csv
├── tests/
│   ├── __init__.py
│   ├── test_image.py
│   ├── test_component.py
│   └── test_equipment.py
└── views/
    ├── git_repository_views.xml
    ├── docker_image_views.xml
    ├── docker_mount_views.xml
    ├── maintenance_equipment_views.xml
    └── menus.xml
```

Hors dépôt (outillage local, non commité) :
- `~/dev/odoo/arpol-dev/run_sw_odoo.sh` — lance une instance jetable pour tester / exporter / charger le français.
- `~/arpol-test/` — copie neutralisée d'arpol.fr pour la validation (Tâche 8).

---

### Task 0: Outil de test local

**Files:**
- Create: `~/dev/odoo/arpol-dev/run_sw_odoo.sh` (hors dépôt)

**Interfaces:**
- Produces: `run_sw_odoo.sh test <module>` (installe et lance `--test-tags /<module>`), `run_sw_odoo.sh export <module>` (écrit `<module>/i18n/<module>.pot`), `run_sw_odoo.sh lang <module>` (installe avec `fr_FR` chargé). Dernière ligne : `RESULT: OK` ou `RESULT: FAILED (see /tmp/swtest-<module>.log)`, code retour 0/1.

Prérequis déjà en place sur arpol-brain : images `odoo:18.0` et `postgres:16`, worktree OCA `~/dev/odoo/OCA/maintenance/18.0`.

- [ ] **Step 1: Écrire le script**

```bash
#!/usr/bin/env bash
# Disposable Odoo 18 runner for the maintenance_sw_* modules.
#   run_sw_odoo.sh test   <module>   install <module> and run its tests
#   run_sw_odoo.sh export <module>   write <module>/i18n/<module>.pot
#   run_sw_odoo.sh lang   <module>   install <module> with fr_FR loaded (validates fr.po)
set -euo pipefail
MODE=$1
MODULE=$2
REPO=$HOME/dev/odoo/arpol-dev/ArPol-odoo-dev-18.0
OCA=$HOME/dev/odoo/OCA/maintenance/18.0
OUT=/tmp/swtest-out
NET=swtest
PG=swtest-pg
DB=swtest
LOG=/tmp/swtest-$MODULE.log
mkdir -p "$OUT" && chmod 777 "$OUT"
: > "$LOG"

docker network inspect $NET >/dev/null 2>&1 || docker network create $NET >/dev/null
docker rm -f $PG >/dev/null 2>&1 || true
docker run -d --rm --name $PG --network $NET \
  -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres postgres:16 >/dev/null
trap 'docker stop $PG >/dev/null 2>&1 || true' EXIT
until docker exec $PG pg_isready -U odoo -h localhost >/dev/null 2>&1; do sleep 1; done

odoo_run() {
  docker run --rm --network $NET -e HOST=$PG -e USER=odoo -e PASSWORD=odoo \
    -v "$REPO":/mnt/arpol:ro -v "$OCA":/mnt/oca-maintenance:ro -v "$OUT":/mnt/out \
    odoo:18.0 odoo \
    --addons-path=/mnt/arpol,/mnt/oca-maintenance,/usr/lib/python3/dist-packages/odoo/addons \
    -d $DB --without-demo=all --stop-after-init "$@" >>"$LOG" 2>&1
}

case $MODE in
  test)
    odoo_run -i "$MODULE" --test-enable --test-tags "/$MODULE" || true
    ;;
  export)
    odoo_run -i "$MODULE" || true
    odoo_run --i18n-export=/mnt/out/$MODULE.pot --modules=$MODULE || true
    mkdir -p "$REPO/$MODULE/i18n"
    cp "$OUT/$MODULE.pot" "$REPO/$MODULE/i18n/$MODULE.pot"
    ;;
  lang)
    odoo_run -i "$MODULE" --load-language=fr_FR || true
    ;;
  *)
    echo "unknown mode $MODE" >&2; exit 2
    ;;
esac

grep -E "odoo\.tests\.result|FAIL:|ERROR:|Traceback" "$LOG" | head -40 || true
if grep -qE "^[0-9-]+ [0-9:,]+ [0-9]+ (ERROR|CRITICAL) " "$LOG"; then
  echo "RESULT: FAILED (see $LOG)"
  exit 1
fi
# An unknown module is only a warning for Odoo ("invalid module names, ignored"): make sure
# tests actually ran.
if [ "$MODE" = test ] && ! grep -qE "odoo\.tests\.result: .* of [1-9][0-9]* tests" "$LOG"; then
  echo "RESULT: FAILED (no test ran, see $LOG)"
  exit 1
fi
echo "RESULT: OK"
```

- [ ] **Step 2: Le rendre exécutable et vérifier qu'il marche sur un module connu**

Run: `chmod +x ~/dev/odoo/arpol-dev/run_sw_odoo.sh && ~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_equipment_hierarchy`
Expected: une ligne `odoo.tests.result: 0 failed, 0 error(s) of N tests` puis `RESULT: OK`.

(Pas de commit : script hors dépôt.)

---

### Task 1: Catalogue logiciel (`maintenance_sw_base`, modèles produits / versions / méthodes)

**Files:**
- Create: `maintenance_sw_base/__init__.py`, `maintenance_sw_base/__manifest__.py`
- Create: `maintenance_sw_base/models/__init__.py`, `software_product.py`, `software_version.py`, `software_deployment_method.py`
- Create: `maintenance_sw_base/security/ir.model.access.csv`
- Test: `maintenance_sw_base/tests/__init__.py`, `maintenance_sw_base/tests/test_catalog.py`

**Interfaces:**
- Produces:
  - `software.product` : `name` (Char, requis, unique), `vendor`, `website`, `changelog_url`, `version_ids` (O2m), `installation_ids` / `installation_count`, `note`, `active`, `action_view_installations()`.
  - `software.version` : `product_id` (requis), `name` (requis, unique par produit), `release_date`, `end_of_support_date`, `channel` (`stable`/`lts`/`saas`/`other`), `is_latest` (exclusif par produit), `sequence` (plus grand = plus récent), `installation_ids` / `installation_count`, `note`, `display_name` = « Produit Version », `action_view_installations()`.
  - `software.deployment.method` : `name` (requis, unique), `managed_by_provider`, `update_procedure` (Html), `documentation_url`, `active`, `installation_ids` / `installation_count`.
  - Les champs `installation_ids` pointent vers `maintenance.equipment` (`software_product_id`, `software_version_id`, `deployment_method_id`) définis en Tâche 2 : dans cette tâche, le manifeste charge déjà le fichier `models/maintenance_equipment.py` minimal créé ici (voir Step 3).

- [ ] **Step 1: Écrire les tests du catalogue**

`maintenance_sw_base/tests/__init__.py` :

```python
from . import test_catalog
```

`maintenance_sw_base/tests/test_catalog.py` :

```python
from psycopg2 import IntegrityError

from odoo.tests import TransactionCase
from odoo.tools import mute_logger


class TestSoftwareCatalog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Version = cls.env["software.version"]
        cls.debian = cls.env["software.product"].create({"name": "Debian"})
        cls.odoo = cls.env["software.product"].create({"name": "Odoo"})

    def _version(self, product, name, **values):
        return self.Version.create({"product_id": product.id, "name": name, **values})

    def test_version_display_name(self):
        self.assertEqual(self._version(self.debian, "12").display_name, "Debian 12")

    def test_version_name_unique_per_product(self):
        self._version(self.debian, "12")
        self._version(self.odoo, "12")  # same name, other product: allowed
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self._version(self.debian, "12")

    def test_product_name_unique(self):
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self.env["software.product"].create({"name": "Debian"})

    def test_deployment_method_name_unique(self):
        Method = self.env["software.deployment.method"]
        Method.create({"name": "Cloudron test"})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            Method.create({"name": "Cloudron test"})

    def test_is_latest_single_per_product(self):
        v11 = self._version(self.debian, "11", is_latest=True)
        v12 = self._version(self.debian, "12", is_latest=True)
        o18 = self._version(self.odoo, "18.0", is_latest=True)
        self.assertFalse(v11.is_latest)
        self.assertTrue(v12.is_latest)
        self.assertTrue(o18.is_latest, "another product is not affected")
        v11.is_latest = True
        self.assertFalse(v12.is_latest)

    def test_is_latest_batch_create_keeps_last(self):
        versions = self.Version.create([
            {"product_id": self.debian.id, "name": "11", "is_latest": True},
            {"product_id": self.debian.id, "name": "12", "is_latest": True},
        ])
        self.assertEqual(versions.filtered("is_latest").mapped("name"), ["12"])

    def test_is_latest_batch_write_keeps_last(self):
        v11 = self._version(self.debian, "11")
        v12 = self._version(self.debian, "12")
        (v11 | v12).write({"is_latest": True})
        self.assertEqual((v11 | v12).filtered("is_latest"), v12)

    def test_is_latest_moved_to_other_product(self):
        o18 = self._version(self.odoo, "18.0", is_latest=True)
        moved = self._version(self.debian, "19.0", is_latest=True)
        moved.product_id = self.odoo
        self.assertTrue(moved.is_latest)
        self.assertFalse(o18.is_latest)

    def test_versions_ordered_most_recent_first(self):
        old = self._version(self.debian, "9", sequence=9)
        new = self._version(self.debian, "12", sequence=12)
        self.env.invalidate_all()  # read the one2many from the database, in _order
        self.assertEqual(self.debian.version_ids, new | old)
        self.assertEqual(self.debian.version_ids[0], new)
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `RESULT: FAILED` (module introuvable / pas de manifeste).

- [ ] **Step 3: Écrire le module minimal**

`maintenance_sw_base/__init__.py` :

```python
from . import models
```

`maintenance_sw_base/__manifest__.py` :

```python
# maintenance_sw_base/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Maintenance - Software Inventory",
    "version": "18.0.1.0.0",
    "summary": "Track installed software (OS, platforms, applications) as maintenance equipment",
    "description": """
Maintenance - Software Inventory
================================

A piece of software is a maintenance equipment (kind "Software"), attached to the hardware or
software that hosts it through the equipment hierarchy. A shared catalog of software products,
versions and deployment methods (0k, Cloudron, Odoo Online...) describes what is installed and
how it is updated.
""",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "category": "Manufacturing/Maintenance",
    "depends": ["maintenance", "maintenance_equipment_hierarchy"],
    "data": [
        "security/ir.model.access.csv",
    ],
    "license": "AGPL-3",
    "installable": True,
    "application": False,
}
```

`maintenance_sw_base/models/__init__.py` :

```python
from . import software_product
from . import software_version
from . import software_deployment_method
from . import maintenance_equipment
```

`maintenance_sw_base/models/software_product.py` :

```python
from odoo import _, api, fields, models


class SoftwareProduct(models.Model):
    _name = "software.product"
    _description = "Software Product"
    _order = "name"

    name = fields.Char(required=True)
    vendor = fields.Char()
    website = fields.Char()
    changelog_url = fields.Char("Changelog URL")
    version_ids = fields.One2many("software.version", "product_id", string="Versions")
    installation_ids = fields.One2many(
        "maintenance.equipment", "software_product_id", string="Installations"
    )
    installation_count = fields.Integer(compute="_compute_installation_count")
    note = fields.Html()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("name_uniq", "unique(name)", "A software product with this name already exists."),
    ]

    @api.depends("installation_ids")
    def _compute_installation_count(self):
        for product in self:
            product.installation_count = len(product.installation_ids)

    def action_view_installations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Installations"),
            "res_model": "maintenance.equipment",
            "view_mode": "list,form",
            "domain": [("software_product_id", "=", self.id)],
            "context": {
                "default_equipment_kind": "software",
                "default_software_product_id": self.id,
            },
        }
```

`maintenance_sw_base/models/software_version.py` :

```python
from odoo import _, api, fields, models

CHANNELS = [
    ("stable", "Stable"),
    ("lts", "LTS"),
    ("saas", "SaaS"),
    ("other", "Other"),
]


class SoftwareVersion(models.Model):
    _name = "software.version"
    _description = "Software Version"
    _order = "product_id, sequence desc, id desc"
    _rec_names_search = ["name", "product_id.name"]

    product_id = fields.Many2one(
        "software.product", required=True, ondelete="cascade", index=True
    )
    name = fields.Char(required=True)
    release_date = fields.Date()
    end_of_support_date = fields.Date("End of Support")
    channel = fields.Selection(CHANNELS, default="stable")
    is_latest = fields.Boolean(
        "Latest", help="Latest known version of the product. Only one version per product."
    )
    sequence = fields.Integer(
        default=10,
        help="Orders the versions of a product: the higher, the more recent. "
        "Version names do not sort reliably as text (9 comes after 12).",
    )
    installation_ids = fields.One2many(
        "maintenance.equipment", "software_version_id", string="Installations"
    )
    installation_count = fields.Integer(compute="_compute_installation_count")
    note = fields.Html()

    _sql_constraints = [
        (
            "product_name_uniq",
            "unique(product_id, name)",
            "This version already exists for this software.",
        ),
    ]

    @api.depends("product_id.name", "name")
    def _compute_display_name(self):
        for version in self:
            if version.product_id:
                version.display_name = f"{version.product_id.name} {version.name or ''}".strip()
            else:
                version.display_name = version.name

    @api.depends("installation_ids")
    def _compute_installation_count(self):
        for version in self:
            version.installation_count = len(version.installation_ids)

    @api.model_create_multi
    def create(self, vals_list):
        versions = super().create(vals_list)
        versions.filtered("is_latest")._unset_other_latest()
        return versions

    def write(self, vals):
        res = super().write(vals)
        if vals.get("is_latest") or "product_id" in vals:
            self.filtered("is_latest")._unset_other_latest()
        return res

    def _unset_other_latest(self):
        """Keep a single latest version per product: the last one of self wins."""
        winners = {}
        for version in self:
            winners[version.product_id.id] = version
        for product_id, version in winners.items():
            self.search([
                ("product_id", "=", product_id),
                ("is_latest", "=", True),
                ("id", "!=", version.id),
            ]).write({"is_latest": False})

    def action_view_installations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Installations"),
            "res_model": "maintenance.equipment",
            "view_mode": "list,form",
            "domain": [("software_version_id", "=", self.id)],
            "context": {
                "default_equipment_kind": "software",
                "default_software_version_id": self.id,
            },
        }
```

`maintenance_sw_base/models/software_deployment_method.py` :

```python
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
```

`maintenance_sw_base/models/maintenance_equipment.py` (minimal, complété en Tâche 2 — nécessaire ici car les `One2many` du catalogue pointent vers ces champs) :

```python
from odoo import fields, models


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    deployment_method_id = fields.Many2one(
        "software.deployment.method", ondelete="restrict", tracking=True
    )
    software_product_id = fields.Many2one(
        "software.product", string="Software", ondelete="restrict", tracking=True
    )
    software_version_id = fields.Many2one(
        "software.version", string="Version", ondelete="restrict", tracking=True
    )
```

`maintenance_sw_base/security/ir.model.access.csv` :

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_software_product_user,software.product.user,model_software_product,base.group_user,1,0,0,0
access_software_product_manager,software.product.manager,model_software_product,maintenance.group_equipment_manager,1,1,1,1
access_software_version_user,software.version.user,model_software_version,base.group_user,1,0,0,0
access_software_version_manager,software.version.manager,model_software_version,maintenance.group_equipment_manager,1,1,1,1
access_software_deployment_method_user,software.deployment.method.user,model_software_deployment_method,base.group_user,1,0,0,0
access_software_deployment_method_manager,software.deployment.method.manager,model_software_deployment_method,maintenance.group_equipment_manager,1,1,1,1
```

- [ ] **Step 4: Lancer les tests**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `odoo.tests.result: 0 failed, 0 error(s) of 9 tests` puis `RESULT: OK`.

- [ ] **Step 5: Commit**

```bash
cd ~/dev/odoo/arpol-dev/ArPol-odoo-dev-18.0
git add maintenance_sw_base
git commit -m "maintenance_sw_base : catalogue logiciel (produits, versions, méthodes de déploiement)"
```

---

### Task 2: Logiciel comme équipement (`maintenance_sw_base`, extension de `maintenance.equipment`)

**Files:**
- Modify: `maintenance_sw_base/models/maintenance_equipment.py` (remplacé entièrement)
- Test: `maintenance_sw_base/tests/test_equipment.py`, `maintenance_sw_base/tests/__init__.py`

**Interfaces:**
- Consumes: `software.product`, `software.version`, `software.deployment.method` (Tâche 1) ; `parent_id` de `maintenance_equipment_hierarchy`.
- Produces sur `maintenance.equipment` : `equipment_kind` (`hardware`/`software`, requis, défaut `hardware`), `install_type` (`os`, `package`, `docker_container`, `compose_stack`, `git_checkout`, `saas`, `manual`), `deployment_method_id`, `software_product_id` (calculé depuis la version, stocké, modifiable), `software_version_id`, `version_note`, `install_path`, `needs_attachment` (calculé, stocké) ; constante `INSTALL_TYPES` dans `odoo.addons.maintenance_sw_base.models.maintenance_equipment`. La Tâche 6 redéfinit `software_version_id` en champ calculé.

- [ ] **Step 1: Écrire les tests**

`maintenance_sw_base/tests/__init__.py` :

```python
from . import test_catalog
from . import test_equipment
```

`maintenance_sw_base/tests/test_equipment.py` :

```python
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestSoftwareEquipment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Equipment = cls.env["maintenance.equipment"]
        Method = cls.env["software.deployment.method"]
        cls.method_0k = Method.create({"name": "0k test"})
        cls.method_saas = Method.create({"name": "SaaS test", "managed_by_provider": True})
        cls.debian = cls.env["software.product"].create({"name": "Debian test"})
        cls.odoo = cls.env["software.product"].create({"name": "Odoo test"})
        cls.debian12 = cls.env["software.version"].create(
            {"product_id": cls.debian.id, "name": "12"}
        )
        cls.vps = cls.Equipment.create({"name": "vps-test"})

    def _software(self, **values):
        return self.Equipment.create({"name": "sw", "equipment_kind": "software", **values})

    def test_default_kind_is_hardware(self):
        self.assertEqual(self.vps.equipment_kind, "hardware")
        self.assertFalse(self.vps.needs_attachment)

    def test_software_without_parent_needs_attachment(self):
        self.assertTrue(self._software(deployment_method_id=self.method_0k.id).needs_attachment)

    def test_software_without_method_needs_attachment(self):
        self.assertTrue(self._software().needs_attachment)

    def test_software_with_parent_does_not_need_attachment(self):
        software = self._software(parent_id=self.vps.id, deployment_method_id=self.method_0k.id)
        self.assertFalse(software.needs_attachment)

    def test_saas_without_parent_does_not_need_attachment(self):
        software = self._software(install_type="saas", deployment_method_id=self.method_saas.id)
        self.assertFalse(software.needs_attachment)

    def test_needs_attachment_recomputed_when_parent_set(self):
        software = self._software(deployment_method_id=self.method_0k.id)
        software.parent_id = self.vps
        self.assertFalse(software.needs_attachment)

    def test_needs_attachment_follows_method_flag(self):
        software = self._software(deployment_method_id=self.method_0k.id)
        self.method_0k.managed_by_provider = True
        self.assertFalse(software.needs_attachment)

    def test_needs_attachment_filter(self):
        software = self._software()
        self.assertIn(software, self.Equipment.search([("needs_attachment", "=", True)]))
        self.assertNotIn(self.vps, self.Equipment.search([("needs_attachment", "=", True)]))

    def test_version_sets_product(self):
        software = self._software(software_version_id=self.debian12.id)
        self.assertEqual(software.software_product_id, self.debian)

    def test_product_without_version_is_kept(self):
        software = self._software(software_product_id=self.odoo.id)
        self.assertEqual(software.software_product_id, self.odoo)
        self.assertFalse(software.software_version_id)

    def test_version_of_other_product_rejected(self):
        software = self._software(software_version_id=self.debian12.id)
        with self.assertRaises(ValidationError):
            software.software_product_id = self.odoo

    def test_mismatch_on_create_rejected(self):
        with self.assertRaises(ValidationError):
            self._software(
                software_product_id=self.odoo.id, software_version_id=self.debian12.id
            )

    def test_catalog_installation_counts(self):
        software = self._software(
            software_version_id=self.debian12.id, deployment_method_id=self.method_0k.id
        )
        self.env.invalidate_all()  # counts are non-stored computes over one2many caches
        self.assertEqual(self.debian.installation_count, 1)
        self.assertEqual(self.debian12.installation_count, 1)
        self.assertEqual(self.method_0k.installation_count, 1)
        action = self.debian12.action_view_installations()
        self.assertEqual(self.Equipment.search(action["domain"]), software)
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `RESULT: FAILED` (champ `equipment_kind` inexistant, etc.).

- [ ] **Step 3: Implémenter**

`maintenance_sw_base/models/maintenance_equipment.py` :

```python
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

INSTALL_TYPES = [
    ("os", "Operating System"),
    ("package", "Package"),
    ("docker_container", "Docker Container"),
    ("compose_stack", "Compose Stack"),
    ("git_checkout", "Git Checkout"),
    ("saas", "SaaS"),
    ("manual", "Manual"),
]


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    equipment_kind = fields.Selection(
        [("hardware", "Hardware"), ("software", "Software")],
        string="Kind",
        required=True,
        default="hardware",
        tracking=True,
    )
    install_type = fields.Selection(INSTALL_TYPES, tracking=True)
    deployment_method_id = fields.Many2one(
        "software.deployment.method", ondelete="restrict", tracking=True
    )
    software_product_id = fields.Many2one(
        "software.product",
        string="Software",
        ondelete="restrict",
        compute="_compute_software_product_id",
        store=True,
        readonly=False,
        tracking=True,
    )
    software_version_id = fields.Many2one(
        "software.version",
        string="Version",
        ondelete="restrict",
        domain="[('product_id', '=?', software_product_id)]",
        tracking=True,
    )
    version_note = fields.Char(help="Free-form version, when it is not in the catalog.")
    install_path = fields.Char(help="Where it is installed, e.g. /opt/apps/myc-deploy.")
    needs_attachment = fields.Boolean(
        "To Attach",
        compute="_compute_needs_attachment",
        store=True,
        help="Software with no parent equipment whose deployment method is not managed by "
        "the provider: the server it runs on is missing.",
    )

    @api.depends("software_version_id")
    def _compute_software_product_id(self):
        for equipment in self:
            if equipment.software_version_id:
                equipment.software_product_id = equipment.software_version_id.product_id
            else:
                equipment.software_product_id = equipment.software_product_id

    @api.depends("equipment_kind", "parent_id", "deployment_method_id.managed_by_provider")
    def _compute_needs_attachment(self):
        for equipment in self:
            equipment.needs_attachment = (
                equipment.equipment_kind == "software"
                and not equipment.parent_id
                and not equipment.deployment_method_id.managed_by_provider
            )

    @api.onchange("software_product_id")
    def _onchange_software_product_id(self):
        version = self.software_version_id
        if version and version.product_id != self.software_product_id:
            self.software_version_id = False

    @api.constrains("software_product_id", "software_version_id")
    def _check_software_version_product(self):
        for equipment in self:
            version = equipment.software_version_id
            if version and version.product_id != equipment.software_product_id:
                raise ValidationError(
                    _(
                        "Version %(version)s does not belong to %(product)s.",
                        version=version.display_name,
                        product=equipment.software_product_id.display_name or _("no software"),
                    )
                )
```

- [ ] **Step 4: Lancer les tests**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `0 failed, 0 error(s) of 22 tests`, `RESULT: OK`.

- [ ] **Step 5: Commit**

```bash
git add maintenance_sw_base
git commit -m "maintenance_sw_base : nature logiciel/matériel, type d'installation, version et contrôle « à rattacher » sur les équipements"
```

---

### Task 3: Interface, données et traduction (`maintenance_sw_base`)

**Files:**
- Create: `maintenance_sw_base/views/software_product_views.xml`, `software_version_views.xml`, `software_deployment_method_views.xml`, `maintenance_equipment_views.xml`, `menus.xml`
- Create: `maintenance_sw_base/data/software_deployment_method_data.xml`
- Create: `maintenance_sw_base/i18n/maintenance_sw_base.pot`, `maintenance_sw_base/i18n/fr.po`
- Modify: `maintenance_sw_base/__manifest__.py` (clé `data`)
- Test: `maintenance_sw_base/tests/test_data.py`, `maintenance_sw_base/tests/__init__.py`

**Interfaces:**
- Consumes: modèles et champs des Tâches 1–2 ; vues natives `maintenance.hr_equipment_view_form` / `_tree` / `_search` ; menu `maintenance.menu_maintenance_configuration`.
- Produces: XML ids `maintenance_sw_base.menu_sw_config` (menu parent réutilisé par la Tâche 7), `maintenance_sw_base.software_product_action`, `software_version_action`, `software_deployment_method_action`, et les méthodes `deployment_method_myc`, `deployment_method_cloudron`, `deployment_method_odoo_online`, `deployment_method_odoo_sh`, `deployment_method_manual`.

- [ ] **Step 1: Écrire le test des données livrées**

`maintenance_sw_base/tests/test_data.py` :

```python
from odoo.tests import TransactionCase


class TestShippedData(TransactionCase):
    def test_deployment_methods(self):
        ref = self.env.ref
        self.assertTrue(ref("maintenance_sw_base.deployment_method_odoo_online").managed_by_provider)
        self.assertTrue(ref("maintenance_sw_base.deployment_method_odoo_sh").managed_by_provider)
        for xmlid in ("myc", "cloudron", "manual"):
            method = ref(f"maintenance_sw_base.deployment_method_{xmlid}")
            self.assertFalse(method.managed_by_provider)

    def test_equipment_form_has_software_page(self):
        arch = self.env["maintenance.equipment"].get_view(view_type="form")["arch"]
        self.assertIn('name="software"', arch)
        self.assertIn('name="equipment_kind"', arch)
```

Ajouter à `maintenance_sw_base/tests/__init__.py` la ligne `from . import test_data`.

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `RESULT: FAILED` (`ValueError: External ID not found ... deployment_method_odoo_online`).

- [ ] **Step 3: Données livrées**

`maintenance_sw_base/data/software_deployment_method_data.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo noupdate="1">
    <record id="deployment_method_myc" model="software.deployment.method">
        <field name="name">0k / myc (compose)</field>
        <field name="update_procedure"><![CDATA[<p>Rebuild or pull the image, then <code>compose down &amp;&amp; compose --debug up</code> on the whole stack. Never run <code>compose up</code> on a single service in production: it can remove orphan containers.</p>]]></field>
    </record>
    <record id="deployment_method_cloudron" model="software.deployment.method">
        <field name="name">Cloudron</field>
        <field name="update_procedure"><![CDATA[<p>Updated from the Cloudron dashboard (or automatically, depending on the app settings). Check the app backup before a major update.</p>]]></field>
    </record>
    <record id="deployment_method_odoo_online" model="software.deployment.method">
        <field name="name">Odoo Online</field>
        <field name="managed_by_provider" eval="True"/>
    </record>
    <record id="deployment_method_odoo_sh" model="software.deployment.method">
        <field name="name">Odoo.sh</field>
        <field name="managed_by_provider" eval="True"/>
    </record>
    <record id="deployment_method_manual" model="software.deployment.method">
        <field name="name">Manual</field>
    </record>
</odoo>
```

- [ ] **Step 4: Vues du catalogue**

`maintenance_sw_base/views/software_product_views.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="software_product_view_list" model="ir.ui.view">
        <field name="name">software.product.list</field>
        <field name="model">software.product</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="vendor"/>
                <field name="installation_count"/>
            </list>
        </field>
    </record>

    <record id="software_product_view_form" model="ir.ui.view">
        <field name="name">software.product.form</field>
        <field name="model">software.product</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <div class="oe_button_box" name="button_box">
                        <button name="action_view_installations" type="object"
                                class="oe_stat_button" icon="fa-server">
                            <field name="installation_count" widget="statinfo" string="Installations"/>
                        </button>
                    </div>
                    <widget name="web_ribbon" title="Archived" bg_color="text-bg-danger" invisible="active"/>
                    <div class="oe_title">
                        <h1><field name="name" placeholder="e.g. Debian"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="vendor"/>
                            <field name="active" invisible="1"/>
                        </group>
                        <group>
                            <field name="website" widget="url"/>
                            <field name="changelog_url" widget="url"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Versions" name="versions">
                            <field name="version_ids">
                                <list editable="bottom">
                                    <field name="name"/>
                                    <field name="channel"/>
                                    <field name="release_date"/>
                                    <field name="end_of_support_date"/>
                                    <field name="is_latest"/>
                                    <field name="sequence"/>
                                    <field name="installation_count"/>
                                </list>
                            </field>
                        </page>
                        <page string="Notes" name="notes">
                            <field name="note"/>
                        </page>
                    </notebook>
                </sheet>
            </form>
        </field>
    </record>

    <record id="software_product_view_search" model="ir.ui.view">
        <field name="name">software.product.search</field>
        <field name="model">software.product</field>
        <field name="arch" type="xml">
            <search>
                <field name="name"/>
                <field name="vendor"/>
                <filter string="Archived" name="inactive" domain="[('active', '=', False)]"/>
            </search>
        </field>
    </record>

    <record id="software_product_action" model="ir.actions.act_window">
        <field name="name">Software Products</field>
        <field name="res_model">software.product</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

`maintenance_sw_base/views/software_version_views.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="software_version_view_list" model="ir.ui.view">
        <field name="name">software.version.list</field>
        <field name="model">software.version</field>
        <field name="arch" type="xml">
            <list>
                <field name="product_id"/>
                <field name="name"/>
                <field name="channel"/>
                <field name="release_date"/>
                <field name="end_of_support_date"/>
                <field name="is_latest"/>
                <field name="installation_count"/>
            </list>
        </field>
    </record>

    <record id="software_version_view_form" model="ir.ui.view">
        <field name="name">software.version.form</field>
        <field name="model">software.version</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <div class="oe_button_box" name="button_box">
                        <button name="action_view_installations" type="object"
                                class="oe_stat_button" icon="fa-server">
                            <field name="installation_count" widget="statinfo" string="Installations"/>
                        </button>
                    </div>
                    <group>
                        <group>
                            <field name="product_id"/>
                            <field name="name"/>
                            <field name="channel"/>
                            <field name="is_latest"/>
                        </group>
                        <group>
                            <field name="release_date"/>
                            <field name="end_of_support_date"/>
                            <field name="sequence"/>
                        </group>
                    </group>
                    <field name="note" placeholder="Release notes, upgrade warnings..."/>
                </sheet>
            </form>
        </field>
    </record>

    <record id="software_version_view_search" model="ir.ui.view">
        <field name="name">software.version.search</field>
        <field name="model">software.version</field>
        <field name="arch" type="xml">
            <search>
                <field name="name"/>
                <field name="product_id"/>
                <filter string="Latest" name="latest" domain="[('is_latest', '=', True)]"/>
                <filter string="End of Support Reached" name="end_of_support"
                        domain="[('end_of_support_date', '&lt;', context_today().strftime('%Y-%m-%d'))]"/>
                <group expand="0" string="Group By">
                    <filter string="Software" name="group_product" context="{'group_by': 'product_id'}"/>
                    <filter string="Channel" name="group_channel" context="{'group_by': 'channel'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="software_version_action" model="ir.actions.act_window">
        <field name="name">Software Versions</field>
        <field name="res_model">software.version</field>
        <field name="view_mode">list,form</field>
        <field name="context">{'search_default_group_product': 1}</field>
    </record>
</odoo>
```

`maintenance_sw_base/views/software_deployment_method_views.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="software_deployment_method_view_list" model="ir.ui.view">
        <field name="name">software.deployment.method.list</field>
        <field name="model">software.deployment.method</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="managed_by_provider"/>
                <field name="installation_count"/>
            </list>
        </field>
    </record>

    <record id="software_deployment_method_view_form" model="ir.ui.view">
        <field name="name">software.deployment.method.form</field>
        <field name="model">software.deployment.method</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <widget name="web_ribbon" title="Archived" bg_color="text-bg-danger" invisible="active"/>
                    <div class="oe_title">
                        <h1><field name="name" placeholder="e.g. Cloudron"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="managed_by_provider"/>
                            <field name="active" invisible="1"/>
                        </group>
                        <group>
                            <field name="documentation_url" widget="url"/>
                            <field name="installation_count"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Update Procedure" name="update_procedure">
                            <field name="update_procedure"/>
                        </page>
                    </notebook>
                </sheet>
            </form>
        </field>
    </record>

    <record id="software_deployment_method_action" model="ir.actions.act_window">
        <field name="name">Deployment Methods</field>
        <field name="res_model">software.deployment.method</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

- [ ] **Step 5: Vues de l'équipement**

`maintenance_sw_base/views/maintenance_equipment_views.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="hr_equipment_view_form" model="ir.ui.view">
        <field name="name">equipment.form.software</field>
        <field name="model">maintenance.equipment</field>
        <field name="inherit_id" ref="maintenance.hr_equipment_view_form"/>
        <field name="arch" type="xml">
            <xpath expr="//div[@name='button_box']" position="after">
                <div class="alert alert-warning" role="alert" invisible="not needs_attachment">
                    This software is attached to no equipment: set the server it runs on as
                    parent, or a deployment method managed by the provider.
                </div>
            </xpath>
            <field name="category_id" position="after">
                <field name="equipment_kind" widget="radio" options="{'horizontal': true}"/>
            </field>
            <xpath expr="//notebook" position="inside">
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
                            <field name="needs_attachment" invisible="1"/>
                        </group>
                    </group>
                </page>
            </xpath>
        </field>
    </record>

    <record id="hr_equipment_view_tree" model="ir.ui.view">
        <field name="name">equipment.list.software</field>
        <field name="model">maintenance.equipment</field>
        <field name="inherit_id" ref="maintenance.hr_equipment_view_tree"/>
        <field name="arch" type="xml">
            <field name="name" position="after">
                <field name="equipment_kind" optional="show"/>
                <field name="software_version_id" optional="show"/>
                <field name="deployment_method_id" optional="hide"/>
            </field>
        </field>
    </record>

    <record id="hr_equipment_view_search" model="ir.ui.view">
        <field name="name">equipment.search.software</field>
        <field name="model">maintenance.equipment</field>
        <field name="inherit_id" ref="maintenance.hr_equipment_view_search"/>
        <field name="arch" type="xml">
            <xpath expr="//filter[@name='my']" position="before">
                <filter string="Hardware" name="hardware" domain="[('equipment_kind', '=', 'hardware')]"/>
                <filter string="Software" name="software" domain="[('equipment_kind', '=', 'software')]"/>
                <separator/>
                <filter string="To Attach" name="needs_attachment" domain="[('needs_attachment', '=', True)]"/>
                <filter string="Managed by Provider" name="managed_by_provider"
                        domain="[('deployment_method_id.managed_by_provider', '=', True)]"/>
                <separator/>
            </xpath>
            <xpath expr="//filter[@name='vendor']" position="after">
                <filter string="Software" name="group_software" context="{'group_by': 'software_product_id'}"/>
                <filter string="Version" name="group_version" context="{'group_by': 'software_version_id'}"/>
                <filter string="Deployment Method" name="group_deployment_method"
                        context="{'group_by': 'deployment_method_id'}"/>
                <filter string="Install Type" name="group_install_type" context="{'group_by': 'install_type'}"/>
            </xpath>
            <field name="category_id" position="after">
                <field name="software_product_id"/>
                <field name="software_version_id"/>
            </field>
        </field>
    </record>
</odoo>
```

- [ ] **Step 6: Menus et manifeste**

`maintenance_sw_base/views/menus.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem id="menu_sw_config" name="Software"
              parent="maintenance.menu_maintenance_configuration" sequence="50"/>
    <menuitem id="menu_software_product" action="software_product_action"
              parent="menu_sw_config" sequence="10"/>
    <menuitem id="menu_software_version" action="software_version_action"
              parent="menu_sw_config" sequence="20"/>
    <menuitem id="menu_software_deployment_method" action="software_deployment_method_action"
              parent="menu_sw_config" sequence="30"/>
</odoo>
```

Dans `maintenance_sw_base/__manifest__.py`, remplacer la clé `data` par :

```python
    "data": [
        "security/ir.model.access.csv",
        "data/software_deployment_method_data.xml",
        "views/software_product_views.xml",
        "views/software_version_views.xml",
        "views/software_deployment_method_views.xml",
        "views/maintenance_equipment_views.xml",
        "views/menus.xml",
    ],
```

- [ ] **Step 7: Lancer les tests**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `0 failed, 0 error(s) of 24 tests`, `RESULT: OK` (une erreur de vue XML ferait échouer l'installation).

- [ ] **Step 8: Traduction française**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh export maintenance_sw_base`
Expected: `RESULT: OK` et `maintenance_sw_base/i18n/maintenance_sw_base.pot` créé.

Copier le `.pot` en `maintenance_sw_base/i18n/fr.po`, remplacer l'en-tête par :

```
# Translation of Odoo Server.
# This file contains the translation of the following modules:
# 	* maintenance_sw_base
#
msgid ""
msgstr ""
"Project-Id-Version: Odoo Server 18.0\n"
"Report-Msgid-Bugs-To: \n"
"Last-Translator: Armand Polmard\n"
"Language-Team: \n"
"Language: fr\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: \n"
"Plural-Forms: n > 1;\n"
```

puis remplir **chaque** `msgstr` avec ce glossaire (les phrases complètes se traduisent dans le même ton) :

| Anglais | Français |
|---|---|
| Software Inventory | Inventaire logiciel |
| Kind / Hardware / Software | Nature / Matériel / Logiciel |
| Install Type | Type d'installation |
| Operating System / Package / Docker Container / Compose Stack / Git Checkout / SaaS / Manual | Système d'exploitation / Paquet / Conteneur Docker / Stack Compose / Checkout git / SaaS / Manuel |
| Deployment Method(s) | Méthode(s) de déploiement |
| Managed by Provider | Géré par le fournisseur |
| Update Procedure | Procédure de mise à jour |
| Documentation URL / Changelog URL | URL de documentation / URL du changelog |
| Software Product(s) / Software Version(s) | Logiciel(s) / Version(s) logicielle(s) |
| Version / Versions / Version Note | Version / Versions / Version (texte libre) |
| Install Path | Chemin d'installation |
| To Attach | À rattacher |
| Release Date / End of Support / End of Support Reached | Date de sortie / Fin de support / Fin de support atteinte |
| Channel / Stable / LTS / Other | Canal / Stable / LTS / Autre |
| Latest | Dernière version |
| Installations / Vendor / Website / Notes / Archived | Installations / Éditeur / Site web / Notes / Archivé |
| Group By | Regrouper par |

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh lang maintenance_sw_base`
Expected: `RESULT: OK` (un `.po` invalide produit une erreur au chargement).

- [ ] **Step 9: Commit**

```bash
git add maintenance_sw_base
git commit -m "maintenance_sw_base : vues, menus, méthodes de déploiement livrées et traduction française"
```

---

### Task 4: Dépôts git et images Docker (`maintenance_sw_docker`)

**Files:**
- Create: `maintenance_sw_docker/__init__.py`, `__manifest__.py`, `models/__init__.py`, `models/git_repository.py`, `models/docker_image.py`
- Create: `maintenance_sw_docker/models/docker_component.py`, `models/docker_mount.py` (minimaux ici, complétés en Tâche 5), `models/maintenance_equipment.py` (minimal ici, complété en Tâche 6)
- Create: `maintenance_sw_docker/security/ir.model.access.csv`
- Test: `maintenance_sw_docker/tests/__init__.py`, `maintenance_sw_docker/tests/test_image.py`

**Interfaces:**
- Consumes: `software.product`, `software.version` (Tâche 1).
- Produces:
  - `git.repository` : `name`, `url` (unique), `host` (`github`/`gitlab`/`other`, calculé depuis l'URL, modifiable), `upstream_id`, `component_ids`, `note` ; contrainte sans cycle sur `upstream_id`.
  - `docker.image` : `registry`, `repository` (requis), `tag`, `digest` (normalisé : blanc → `False`), `build_date`, `parent_id`, `product_id` (calculé depuis `version_id`, modifiable), `version_id`, `component_ids`, `container_ids` / `container_count`, `duplicate_warning`, `note` ; `display_name` = `repository:tag (12 car. du digest)` ; `_image_chain()` → recordset `docker.image`, ancêtre le plus lointain en premier ; contrainte SQL `unique(repository, digest)` ; contrainte sans cycle sur `parent_id`.
  - `maintenance.equipment.docker_image_id` (Many2one, défini dès cette tâche pour `container_ids`).

- [ ] **Step 1: Écrire les tests**

`maintenance_sw_docker/tests/__init__.py` :

```python
from . import test_image
```

`maintenance_sw_docker/tests/test_image.py` :

```python
from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from odoo.tools import mute_logger

DIGEST = "sha256:f46e1a70b686d85611004e4da6456e71680ab0f22f4ba801de95b54fbd90757e"


class TestDockerImage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Image = cls.env["docker.image"]
        cls.Repository = cls.env["git.repository"]
        cls.odoo = cls.env["software.product"].create({"name": "Odoo test"})
        cls.odoo18 = cls.env["software.version"].create(
            {"product_id": cls.odoo.id, "name": "18.0"}
        )

    def test_display_name(self):
        image = self.Image.create({"repository": "mirror/odoo", "tag": "rc_18.0-ArPol", "digest": DIGEST})
        self.assertEqual(image.display_name, "mirror/odoo:rc_18.0-ArPol (f46e1a70b686)")
        self.assertEqual(self.Image.create({"repository": "postgres"}).display_name, "postgres")

    def test_digest_unique_per_repository(self):
        self.Image.create({"repository": "mirror/odoo", "digest": DIGEST})
        self.Image.create({"repository": "other/odoo", "digest": DIGEST})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self.Image.create({"repository": "mirror/odoo", "digest": DIGEST})

    def test_blank_digest_is_no_digest(self):
        first = self.Image.create({"repository": "mirror/odoo", "tag": "18.0", "digest": ""})
        second = self.Image.create({"repository": "mirror/odoo", "tag": "18.0", "digest": "  "})
        self.assertFalse(first.digest)
        self.assertFalse(second.digest)
        first.write({"digest": " "})
        self.assertFalse(first.digest)

    def test_digest_is_stripped(self):
        image = self.Image.create({"repository": "mirror/odoo", "digest": f" {DIGEST}\n"})
        self.assertEqual(image.digest, DIGEST)

    def test_duplicate_warning_without_digest(self):
        first = self.Image.create({"repository": "mirror/odoo", "tag": "18.0"})
        self.assertFalse(first.duplicate_warning)
        second = self.Image.create({"repository": "mirror/odoo", "tag": "18.0"})
        self.assertTrue(second.duplicate_warning)
        with_digest = self.Image.create({"repository": "mirror/odoo", "tag": "18.0", "digest": DIGEST})
        self.assertFalse(with_digest.duplicate_warning)

    def test_parent_cycle_rejected(self):
        base = self.Image.create({"repository": "tecnativa/doodba"})
        child = self.Image.create({"repository": "mirror/odoo", "parent_id": base.id})
        with self.assertRaises(ValidationError):
            base.parent_id = child

    def test_image_chain_most_distant_first(self):
        grand = self.Image.create({"repository": "python"})
        parent = self.Image.create({"repository": "tecnativa/doodba", "parent_id": grand.id})
        image = self.Image.create({"repository": "mirror/odoo", "parent_id": parent.id})
        self.assertEqual(image._image_chain().ids, [grand.id, parent.id, image.id])

    def test_version_sets_product(self):
        image = self.Image.create({"repository": "mirror/odoo", "version_id": self.odoo18.id})
        self.assertEqual(image.product_id, self.odoo)

    def test_version_of_other_product_rejected(self):
        debian = self.env["software.product"].create({"name": "Debian test"})
        image = self.Image.create({"repository": "mirror/odoo", "version_id": self.odoo18.id})
        with self.assertRaises(ValidationError):
            image.product_id = debian

    def test_repository_host_from_url(self):
        github = self.Repository.create({"name": "OCA/server-ux", "url": "https://github.com/OCA/server-ux.git"})
        mirror = self.Repository.create({"name": "mirror/server-ux", "url": "git.0k.io:/var/git/mirror/server-ux.git"})
        self.assertEqual(github.host, "github")
        self.assertEqual(mirror.host, "other")

    def test_repository_url_unique(self):
        url = "https://github.com/OCA/server-ux.git"
        self.Repository.create({"name": "a", "url": url})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self.Repository.create({"name": "b", "url": url})

    def test_repository_upstream_cycle_rejected(self):
        upstream = self.Repository.create({"name": "OCA/server-ux", "url": "https://github.com/OCA/server-ux.git"})
        mirror = self.Repository.create(
            {"name": "mirror", "url": "git.0k.io:/var/git/mirror/server-ux.git", "upstream_id": upstream.id}
        )
        with self.assertRaises(ValidationError):
            upstream.upstream_id = mirror

    def test_container_count(self):
        image = self.Image.create({"repository": "mirror/odoo"})
        self.env["maintenance.equipment"].create(
            {"name": "myc_odoo-v18_1", "equipment_kind": "software", "docker_image_id": image.id}
        )
        self.env.invalidate_all()
        self.assertEqual(image.container_count, 1)
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_docker`
Expected: `RESULT: FAILED` (module inexistant).

- [ ] **Step 3: Implémenter**

`maintenance_sw_docker/__init__.py` :

```python
from . import models
```

`maintenance_sw_docker/__manifest__.py` :

```python
# maintenance_sw_docker/__manifest__.py
# @author: Armand Polmard (contact@arpol.fr)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Maintenance - Docker Inventory",
    "version": "18.0.1.0.0",
    "summary": "Docker images, mounts and the code repositories they bring, per container",
    "description": """
Maintenance - Docker Inventory
==============================

Describes what really runs in a container: its image (and the images it is built FROM), the
git repositories each image contains, and the mounts that add or override repositories at run
time. The container's effective components are computed from all of them.
""",
    "author": "Armand Polmard",
    "website": "https://arpol.fr",
    "category": "Manufacturing/Maintenance",
    "depends": ["maintenance_sw_base"],
    "data": [
        "security/ir.model.access.csv",
    ],
    "license": "AGPL-3",
    "installable": True,
    "application": False,
}
```

`maintenance_sw_docker/models/__init__.py` :

```python
from . import git_repository
from . import docker_image
from . import docker_mount
from . import docker_component
from . import maintenance_equipment
```

`maintenance_sw_docker/models/git_repository.py` :

```python
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
```

`maintenance_sw_docker/models/docker_image.py` :

```python
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
```

`maintenance_sw_docker/models/docker_mount.py` (minimal, complété en Tâche 5) :

```python
from odoo import fields, models


class DockerMount(models.Model):
    _name = "docker.mount"
    _description = "Docker Mount"

    equipment_id = fields.Many2one(
        "maintenance.equipment", required=True, ondelete="cascade", index=True
    )
```

`maintenance_sw_docker/models/docker_component.py` (minimal, complété en Tâche 5) :

```python
from odoo import fields, models


class DockerComponent(models.Model):
    _name = "docker.component"
    _description = "Docker Component"

    image_id = fields.Many2one("docker.image", ondelete="cascade", index=True)
    mount_id = fields.Many2one("docker.mount", ondelete="cascade", index=True)
    repository_id = fields.Many2one("git.repository", required=True, ondelete="restrict")
```

`maintenance_sw_docker/models/maintenance_equipment.py` (minimal, complété en Tâche 6) :

```python
from odoo import fields, models


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    docker_image_id = fields.Many2one("docker.image", ondelete="restrict", tracking=True)
```

`maintenance_sw_docker/security/ir.model.access.csv` :

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_git_repository_user,git.repository.user,model_git_repository,base.group_user,1,0,0,0
access_git_repository_manager,git.repository.manager,model_git_repository,maintenance.group_equipment_manager,1,1,1,1
access_docker_image_user,docker.image.user,model_docker_image,base.group_user,1,0,0,0
access_docker_image_manager,docker.image.manager,model_docker_image,maintenance.group_equipment_manager,1,1,1,1
access_docker_mount_user,docker.mount.user,model_docker_mount,base.group_user,1,0,0,0
access_docker_mount_manager,docker.mount.manager,model_docker_mount,maintenance.group_equipment_manager,1,1,1,1
access_docker_component_user,docker.component.user,model_docker_component,base.group_user,1,0,0,0
access_docker_component_manager,docker.component.manager,model_docker_component,maintenance.group_equipment_manager,1,1,1,1
```

- [ ] **Step 4: Lancer les tests**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_docker`
Expected: `0 failed, 0 error(s) of 13 tests`, `RESULT: OK`.

- [ ] **Step 5: Commit**

```bash
git add maintenance_sw_docker
git commit -m "maintenance_sw_docker : dépôts git et images Docker (digest, image de base, version)"
```

---

### Task 5: Montages et composants (`maintenance_sw_docker`)

**Files:**
- Modify: `maintenance_sw_docker/models/docker_mount.py`, `maintenance_sw_docker/models/docker_component.py` (remplacés entièrement)
- Test: `maintenance_sw_docker/tests/test_component.py`, `maintenance_sw_docker/tests/__init__.py`

**Interfaces:**
- Consumes: `docker.image`, `git.repository` (Tâche 4).
- Produces:
  - `docker.mount` : `equipment_id` (requis), `mount_type` (`bind`/`volume`), `source` (requis), `destination` (requis), `mode` (`rw`/`ro`), `usage` (`repos`/`data`/`config`/`logs`/`other`), `component_ids` ; `display_name` = `source → destination`.
  - `docker.component` : `image_id`, `mount_id` (exactement un), `repository_id` (requis), `path`, `ref`, `commit`, `role` (`core`/`enterprise`/`oca`/`custom`/`third_party`), `merges`, `overrides_id` (seulement depuis un montage, vers un composant d'image) ; `_effective_key()` → `("path", <path nettoyé>)` ou `("repository", <id>)` si `path` vide.

- [ ] **Step 1: Écrire les tests**

Ajouter `from . import test_component` à `maintenance_sw_docker/tests/__init__.py`.

`maintenance_sw_docker/tests/test_component.py` :

```python
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestDockerComponent(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Component = cls.env["docker.component"]
        cls.repo = cls.env["git.repository"].create(
            {"name": "arpol-dev/ArPol-odoo-dev", "url": "https://github.com/arpol-dev/ArPol-odoo-dev.git"}
        )
        cls.image = cls.env["docker.image"].create({"repository": "mirror/odoo"})
        cls.container = cls.env["maintenance.equipment"].create(
            {"name": "myc_odoo-v18_1", "equipment_kind": "software", "install_type": "docker_container"}
        )
        cls.mount = cls.env["docker.mount"].create({
            "equipment_id": cls.container.id,
            "source": "/srv/datastore/data/odoo-v18/repos-arpol",
            "destination": "/opt/odoo/auto/dev",
            "usage": "repos",
        })

    def test_mount_display_name(self):
        self.assertEqual(
            self.mount.display_name,
            "/srv/datastore/data/odoo-v18/repos-arpol → /opt/odoo/auto/dev",
        )

    def test_component_needs_an_owner(self):
        with self.assertRaises(ValidationError):
            self.Component.create({"repository_id": self.repo.id})

    def test_component_cannot_have_two_owners(self):
        with self.assertRaises(ValidationError):
            self.Component.create(
                {"repository_id": self.repo.id, "image_id": self.image.id, "mount_id": self.mount.id}
            )

    def test_image_component_cannot_override(self):
        target = self.Component.create({"repository_id": self.repo.id, "image_id": self.image.id})
        with self.assertRaises(ValidationError):
            self.Component.create(
                {"repository_id": self.repo.id, "image_id": self.image.id, "overrides_id": target.id}
            )

    def test_mount_component_overrides_only_image_components(self):
        other = self.Component.create({"repository_id": self.repo.id, "mount_id": self.mount.id})
        with self.assertRaises(ValidationError):
            self.Component.create(
                {"repository_id": self.repo.id, "mount_id": self.mount.id, "overrides_id": other.id}
            )

    def test_mount_component_overrides_image_component(self):
        target = self.Component.create({"repository_id": self.repo.id, "image_id": self.image.id})
        override = self.Component.create(
            {"repository_id": self.repo.id, "mount_id": self.mount.id, "overrides_id": target.id}
        )
        self.assertEqual(override.overrides_id, target)

    def test_effective_key(self):
        with_path = self.Component.create(
            {"repository_id": self.repo.id, "image_id": self.image.id, "path": " /opt/odoo/custom/src/x "}
        )
        without_path = self.Component.create({"repository_id": self.repo.id, "image_id": self.image.id})
        self.assertEqual(with_path._effective_key(), ("path", "/opt/odoo/custom/src/x"))
        self.assertEqual(without_path._effective_key(), ("repository", self.repo.id))

    def test_component_display_name(self):
        component = self.Component.create({
            "repository_id": self.repo.id,
            "image_id": self.image.id,
            "ref": "18.0",
            "commit": "4ba2ff313ae43eefd4aa0873bbcff8e37f107727",
        })
        self.assertEqual(component.display_name, "arpol-dev/ArPol-odoo-dev@18.0 (4ba2ff31)")
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_docker`
Expected: `RESULT: FAILED` (champs `source`, `overrides_id`… inexistants).

- [ ] **Step 3: Implémenter**

`maintenance_sw_docker/models/docker_mount.py` :

```python
from odoo import api, fields, models

MOUNT_USAGES = [
    ("repos", "Code Repositories"),
    ("data", "Data"),
    ("config", "Configuration"),
    ("logs", "Logs"),
    ("other", "Other"),
]


class DockerMount(models.Model):
    _name = "docker.mount"
    _description = "Docker Mount"
    _order = "equipment_id, destination, id"

    equipment_id = fields.Many2one(
        "maintenance.equipment", string="Container", required=True, ondelete="cascade", index=True
    )
    mount_type = fields.Selection(
        [("bind", "Bind"), ("volume", "Volume")], string="Type", default="bind", required=True
    )
    source = fields.Char(required=True, help="Host path, or volume name.")
    destination = fields.Char(required=True, help="Path inside the container.")
    mode = fields.Selection(
        [("rw", "Read-write"), ("ro", "Read-only")], default="rw", required=True
    )
    usage = fields.Selection(MOUNT_USAGES, default="other", required=True)
    component_ids = fields.One2many("docker.component", "mount_id", string="Components")

    @api.depends("source", "destination")
    def _compute_display_name(self):
        for mount in self:
            mount.display_name = f"{mount.source or ''} → {mount.destination or ''}"
```

`maintenance_sw_docker/models/docker_component.py` :

```python
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
```

- [ ] **Step 4: Lancer les tests**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_docker`
Expected: `0 failed, 0 error(s) of 21 tests`, `RESULT: OK`.

- [ ] **Step 5: Commit**

```bash
git add maintenance_sw_docker
git commit -m "maintenance_sw_docker : montages et composants (image ou montage, remplacement d'un composant d'image)"
```

---

### Task 6: Le conteneur (`maintenance_sw_docker`, extension de `maintenance.equipment`)

**Files:**
- Modify: `maintenance_sw_docker/models/maintenance_equipment.py` (remplacé entièrement)
- Test: `maintenance_sw_docker/tests/test_equipment.py`, `maintenance_sw_docker/tests/__init__.py`

**Interfaces:**
- Consumes: `docker.image._image_chain()`, `docker.component._effective_key()`, `docker.mount` (Tâches 4–5) ; `software_version_id` / `software_product_id` (Tâche 2).
- Produces sur `maintenance.equipment` : `docker_image_id`, `container_name`, `mount_ids`, `effective_component_ids` (Many2many calculé non stocké), `runtime_changes` ; `software_version_id` redéfini en calculé (`store=True`, `readonly=False`) depuis `docker_image_id.version_id`.

- [ ] **Step 1: Écrire les tests**

Ajouter `from . import test_equipment` à `maintenance_sw_docker/tests/__init__.py`.

`maintenance_sw_docker/tests/test_equipment.py` :

```python
from odoo.tests import TransactionCase

SRC = "/opt/odoo/custom/src"


class TestDockerEquipment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Image = cls.env["docker.image"]
        cls.Component = cls.env["docker.component"]
        cls.odoo = cls.env["software.product"].create({"name": "Odoo test"})
        cls.odoo17 = cls.env["software.version"].create({"product_id": cls.odoo.id, "name": "17.0"})
        cls.odoo18 = cls.env["software.version"].create({"product_id": cls.odoo.id, "name": "18.0"})
        Repository = cls.env["git.repository"]
        cls.ocb = Repository.create({"name": "OCA/OCB", "url": "https://github.com/OCA/OCB.git"})
        cls.ux = Repository.create({"name": "OCA/server-ux", "url": "https://github.com/OCA/server-ux.git"})
        cls.arpol = Repository.create(
            {"name": "arpol-dev/ArPol-odoo-dev", "url": "https://github.com/arpol-dev/ArPol-odoo-dev.git"}
        )
        cls.bemade = Repository.create(
            {"name": "arpol-dev/bemade-addons", "url": "https://github.com/arpol-dev/bemade-addons.git"}
        )

    def _container(self, **values):
        return self.env["maintenance.equipment"].create({
            "name": "myc_odoo-v18_1",
            "equipment_kind": "software",
            "install_type": "docker_container",
            **values,
        })

    def _component(self, owner, repository, path=None, commit=None, **values):
        key = "image_id" if owner._name == "docker.image" else "mount_id"
        return self.Component.create({
            key: owner.id, "repository_id": repository.id, "path": path, "commit": commit, **values,
        })

    def _mount(self, container):
        return self.env["docker.mount"].create({
            "equipment_id": container.id,
            "source": "/srv/datastore/data/odoo-v18/repos-arpol",
            "destination": "/opt/odoo/auto/dev",
            "usage": "repos",
        })

    def _effective(self, container):
        self.env.invalidate_all()
        return container.effective_component_ids

    # Version -----------------------------------------------------------

    def test_version_comes_from_image(self):
        image = self.Image.create({"repository": "mirror/odoo", "version_id": self.odoo18.id})
        container = self._container(docker_image_id=image.id)
        self.assertEqual(container.software_version_id, self.odoo18)
        self.assertEqual(container.software_product_id, self.odoo)

    def test_image_version_change_propagates(self):
        image = self.Image.create({"repository": "mirror/odoo", "version_id": self.odoo17.id})
        container = self._container(docker_image_id=image.id)
        image.version_id = self.odoo18
        self.assertEqual(container.software_version_id, self.odoo18)

    def test_image_without_version_keeps_manual_version(self):
        image = self.Image.create({"repository": "postgres"})
        container = self._container(software_version_id=self.odoo17.id)
        container.docker_image_id = image
        self.assertEqual(container.software_version_id, self.odoo17)

    def test_manual_version_without_image(self):
        container = self._container(software_version_id=self.odoo17.id)
        self.assertEqual(container.software_version_id, self.odoo17)

    # Effective components ------------------------------------------------

    def test_image_chain_child_replaces_parent_on_same_path(self):
        base = self.Image.create({"repository": "tecnativa/doodba"})
        image = self.Image.create({"repository": "mirror/odoo", "parent_id": base.id})
        old_ocb = self._component(base, self.ocb, f"{SRC}/odoo", "aaa")
        new_ocb = self._component(image, self.ocb, f"{SRC}/odoo", "bbb")
        ux = self._component(base, self.ux, f"{SRC}/server-ux")
        container = self._container(docker_image_id=image.id)
        effective = self._effective(container)
        self.assertIn(new_ocb, effective)
        self.assertIn(ux, effective, "a parent component nobody replaces is inherited")
        self.assertNotIn(old_ocb, effective)

    def test_mount_adds_and_overrides(self):
        image = self.Image.create({"repository": "mirror/odoo"})
        image_arpol = self._component(image, self.arpol, f"{SRC}/ArPol-odoo-dev", "old")
        ux = self._component(image, self.ux, f"{SRC}/server-ux")
        container = self._container(docker_image_id=image.id)
        mount = self._mount(container)
        mount_arpol = self._component(
            mount, self.arpol, "/opt/odoo/auto/dev/ArPol-odoo-dev", "new", overrides_id=image_arpol.id
        )
        bemade = self._component(mount, self.bemade, "/opt/odoo/auto/dev/bemade-addons")
        effective = self._effective(container)
        self.assertEqual(effective, ux | mount_arpol | bemade)

    def test_override_of_parent_component_already_replaced_by_child_image(self):
        base = self.Image.create({"repository": "tecnativa/doodba"})
        image = self.Image.create({"repository": "mirror/odoo", "parent_id": base.id})
        parent_arpol = self._component(base, self.arpol, f"{SRC}/ArPol-odoo-dev", "p")
        self._component(image, self.arpol, f"{SRC}/ArPol-odoo-dev", "c")
        container = self._container(docker_image_id=image.id)
        mount_arpol = self._component(
            self._mount(container), self.arpol, "/opt/odoo/auto/dev/ArPol-odoo-dev",
            overrides_id=parent_arpol.id,
        )
        effective = self._effective(container)
        self.assertEqual(effective, mount_arpol, "the override removes the entry by key, once")

    def test_components_without_path_resolved_by_repository(self):
        base = self.Image.create({"repository": "tecnativa/doodba"})
        image = self.Image.create({"repository": "mirror/odoo", "parent_id": base.id})
        old_ux = self._component(base, self.ux)
        ocb = self._component(base, self.ocb)
        new_ux = self._component(image, self.ux)
        container = self._container(docker_image_id=image.id)
        self.assertEqual(self._effective(container), ocb | new_ux)
        self.assertNotIn(old_ux, self._effective(container))

    def test_mounts_only_without_image(self):
        container = self._container()
        bemade = self._component(self._mount(container), self.bemade, "/opt/odoo/auto/dev/bemade-addons")
        self.assertEqual(self._effective(container), bemade)
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_docker`
Expected: `RESULT: FAILED` (`effective_component_ids` inexistant, version non issue de l'image).

- [ ] **Step 3: Implémenter**

`maintenance_sw_docker/models/maintenance_equipment.py` :

```python
from odoo import Command, api, fields, models


class MaintenanceEquipment(models.Model):
    _inherit = "maintenance.equipment"

    docker_image_id = fields.Many2one("docker.image", ondelete="restrict", tracking=True)
    container_name = fields.Char(help="e.g. myc_odoo-v18_1")
    mount_ids = fields.One2many("docker.mount", "equipment_id", string="Mounts")
    effective_component_ids = fields.Many2many(
        "docker.component",
        compute="_compute_effective_component_ids",
        string="Effective Components",
        help="What really runs in the container: the components of the image chain, then the "
        "mounts, which add components or override image ones.",
    )
    runtime_changes = fields.Text(
        help="Changes made inside the running container, outside the image and the declared "
        "mounts (e.g. a symlink added by hand). They are lost when the container is recreated.",
    )
    software_version_id = fields.Many2one(
        "software.version",
        compute="_compute_software_version_id",
        store=True,
        readonly=False,
    )

    @api.depends("docker_image_id.version_id")
    def _compute_software_version_id(self):
        for equipment in self:
            image_version = equipment.docker_image_id.version_id
            if image_version:
                equipment.software_version_id = image_version
            else:
                equipment.software_version_id = equipment.software_version_id

    @api.depends(
        "docker_image_id.parent_id",
        "docker_image_id.component_ids",
        "mount_ids.component_ids.overrides_id",
    )
    def _compute_effective_component_ids(self):
        for equipment in self:
            by_key = {}
            if equipment.docker_image_id:
                for image in equipment.docker_image_id._image_chain():
                    for component in image.component_ids:
                        by_key[component._effective_key()] = component
            for component in equipment.mount_ids.component_ids:
                if component.overrides_id:
                    by_key.pop(component.overrides_id._effective_key(), None)
                by_key[("mount", component.id)] = component
            equipment.effective_component_ids = [
                Command.set([component.id for component in by_key.values()])
            ]
```

Note : la dépendance ne couvre qu'un niveau de `parent_id` (l'ORM ne sait pas exprimer une chaîne de longueur variable). Le champ n'étant pas stocké, il est recalculé à chaque lecture hors cache ; les tests invalident le cache avant de le lire.

- [ ] **Step 4: Lancer les tests**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_docker`
Expected: `0 failed, 0 error(s) of 30 tests`, `RESULT: OK`.

- [ ] **Step 5: Vérifier que le module de base passe toujours**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_base`
Expected: `RESULT: OK`.

- [ ] **Step 6: Commit**

```bash
git add maintenance_sw_docker
git commit -m "maintenance_sw_docker : conteneur (image, montages, composants effectifs, version issue de l'image)"
```

---

### Task 7: Interface et traduction (`maintenance_sw_docker`)

**Files:**
- Create: `maintenance_sw_docker/views/git_repository_views.xml`, `docker_image_views.xml`, `docker_mount_views.xml`, `maintenance_equipment_views.xml`, `menus.xml`
- Create: `maintenance_sw_docker/i18n/maintenance_sw_docker.pot`, `maintenance_sw_docker/i18n/fr.po`
- Modify: `maintenance_sw_docker/__manifest__.py` (clé `data`)
- Test: `maintenance_sw_docker/tests/test_views.py`, `maintenance_sw_docker/tests/__init__.py`

**Interfaces:**
- Consumes: `maintenance_sw_base.menu_sw_config` et `maintenance_sw_base.hr_equipment_view_form` (page `software`) (Tâche 3).
- Produces: actions `maintenance_sw_docker.docker_image_action`, `git_repository_action` ; page `docker` dans le formulaire équipement.

- [ ] **Step 1: Écrire le test**

Ajouter `from . import test_views` à `maintenance_sw_docker/tests/__init__.py`.

`maintenance_sw_docker/tests/test_views.py` :

```python
from odoo.tests import TransactionCase


class TestDockerViews(TransactionCase):
    def test_equipment_form_has_docker_page(self):
        arch = self.env["maintenance.equipment"].get_view(view_type="form")["arch"]
        self.assertIn('name="docker"', arch)
        self.assertIn('name="effective_component_ids"', arch)

    def test_menus(self):
        self.assertEqual(
            self.env.ref("maintenance_sw_docker.menu_docker_image").parent_id,
            self.env.ref("maintenance_sw_base.menu_sw_config"),
        )
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_docker`
Expected: `RESULT: FAILED`.

- [ ] **Step 3: Vues**

`maintenance_sw_docker/views/git_repository_views.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="git_repository_view_list" model="ir.ui.view">
        <field name="name">git.repository.list</field>
        <field name="model">git.repository</field>
        <field name="arch" type="xml">
            <list>
                <field name="name"/>
                <field name="url"/>
                <field name="host"/>
                <field name="upstream_id"/>
            </list>
        </field>
    </record>

    <record id="git_repository_view_form" model="ir.ui.view">
        <field name="name">git.repository.form</field>
        <field name="model">git.repository</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <div class="oe_title">
                        <h1><field name="name" placeholder="e.g. OCA/server-ux"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="url" widget="url"/>
                            <field name="host"/>
                        </group>
                        <group>
                            <field name="upstream_id"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Components" name="components">
                            <field name="component_ids" readonly="1">
                                <list>
                                    <field name="image_id"/>
                                    <field name="mount_id"/>
                                    <field name="path"/>
                                    <field name="ref"/>
                                    <field name="commit"/>
                                </list>
                            </field>
                        </page>
                        <page string="Notes" name="notes">
                            <field name="note"/>
                        </page>
                    </notebook>
                </sheet>
            </form>
        </field>
    </record>

    <record id="git_repository_view_search" model="ir.ui.view">
        <field name="name">git.repository.search</field>
        <field name="model">git.repository</field>
        <field name="arch" type="xml">
            <search>
                <field name="name"/>
                <field name="url"/>
                <group expand="0" string="Group By">
                    <filter string="Host" name="group_host" context="{'group_by': 'host'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="git_repository_action" model="ir.actions.act_window">
        <field name="name">Git Repositories</field>
        <field name="res_model">git.repository</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

`maintenance_sw_docker/views/docker_image_views.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="docker_image_view_list" model="ir.ui.view">
        <field name="name">docker.image.list</field>
        <field name="model">docker.image</field>
        <field name="arch" type="xml">
            <list>
                <field name="registry" optional="hide"/>
                <field name="repository"/>
                <field name="tag"/>
                <field name="digest" optional="hide"/>
                <field name="build_date"/>
                <field name="version_id"/>
                <field name="parent_id" optional="hide"/>
                <field name="container_count"/>
            </list>
        </field>
    </record>

    <record id="docker_image_view_form" model="ir.ui.view">
        <field name="name">docker.image.form</field>
        <field name="model">docker.image</field>
        <field name="arch" type="xml">
            <form>
                <sheet>
                    <div class="oe_button_box" name="button_box">
                        <button name="action_view_containers" type="object"
                                class="oe_stat_button" icon="fa-cube">
                            <field name="container_count" widget="statinfo" string="Containers"/>
                        </button>
                    </div>
                    <div class="alert alert-warning" role="alert" invisible="not duplicate_warning">
                        <field name="duplicate_warning"/>
                    </div>
                    <group>
                        <group>
                            <field name="registry"/>
                            <field name="repository"/>
                            <field name="tag"/>
                            <field name="digest"/>
                            <field name="build_date"/>
                        </group>
                        <group>
                            <field name="parent_id"/>
                            <field name="product_id"/>
                            <field name="version_id"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Components" name="components">
                            <field name="component_ids">
                                <list editable="bottom">
                                    <field name="repository_id"/>
                                    <field name="path"/>
                                    <field name="ref"/>
                                    <field name="commit"/>
                                    <field name="role"/>
                                    <field name="merges" optional="hide"/>
                                </list>
                            </field>
                        </page>
                        <page string="Notes" name="notes">
                            <field name="note"/>
                        </page>
                    </notebook>
                </sheet>
            </form>
        </field>
    </record>

    <record id="docker_image_view_search" model="ir.ui.view">
        <field name="name">docker.image.search</field>
        <field name="model">docker.image</field>
        <field name="arch" type="xml">
            <search>
                <field name="repository"/>
                <field name="tag"/>
                <field name="digest"/>
                <field name="version_id"/>
                <group expand="0" string="Group By">
                    <filter string="Repository" name="group_repository" context="{'group_by': 'repository'}"/>
                    <filter string="Version" name="group_version" context="{'group_by': 'version_id'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="docker_image_action" model="ir.actions.act_window">
        <field name="name">Docker Images</field>
        <field name="res_model">docker.image</field>
        <field name="view_mode">list,form</field>
    </record>
</odoo>
```

`maintenance_sw_docker/views/docker_mount_views.xml` (formulaire ouvert depuis la liste des montages du conteneur) :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="docker_mount_view_form" model="ir.ui.view">
        <field name="name">docker.mount.form</field>
        <field name="model">docker.mount</field>
        <field name="arch" type="xml">
            <form>
                <group>
                    <group>
                        <field name="source"/>
                        <field name="destination"/>
                    </group>
                    <group>
                        <field name="mount_type"/>
                        <field name="mode"/>
                        <field name="usage"/>
                    </group>
                </group>
                <field name="component_ids" invisible="usage != 'repos'">
                    <list editable="bottom">
                        <field name="repository_id"/>
                        <field name="path"/>
                        <field name="ref"/>
                        <field name="commit"/>
                        <field name="role"/>
                        <field name="overrides_id"/>
                    </list>
                </field>
            </form>
        </field>
    </record>
</odoo>
```

`maintenance_sw_docker/views/maintenance_equipment_views.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="hr_equipment_view_form" model="ir.ui.view">
        <field name="name">equipment.form.docker</field>
        <field name="model">maintenance.equipment</field>
        <field name="inherit_id" ref="maintenance_sw_base.hr_equipment_view_form"/>
        <field name="arch" type="xml">
            <xpath expr="//page[@name='software']" position="after">
                <page string="Docker" name="docker"
                      invisible="install_type not in ('docker_container', 'compose_stack')">
                    <group>
                        <group>
                            <field name="docker_image_id"/>
                            <field name="container_name"/>
                        </group>
                    </group>
                    <separator string="Mounts"/>
                    <field name="mount_ids">
                        <list>
                            <field name="source"/>
                            <field name="destination"/>
                            <field name="mount_type"/>
                            <field name="mode"/>
                            <field name="usage"/>
                        </list>
                    </field>
                    <separator string="Effective Components"/>
                    <field name="effective_component_ids" readonly="1">
                        <list>
                            <field name="repository_id"/>
                            <field name="path"/>
                            <field name="ref"/>
                            <field name="commit"/>
                            <field name="role"/>
                            <field name="image_id"/>
                            <field name="mount_id"/>
                        </list>
                    </field>
                    <separator string="Runtime Changes"/>
                    <field name="runtime_changes"
                           placeholder="Changes made by hand inside the container, lost if it is recreated"/>
                </page>
            </xpath>
        </field>
    </record>
</odoo>
```

`maintenance_sw_docker/views/menus.xml` :

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <menuitem id="menu_docker_image" action="docker_image_action"
              parent="maintenance_sw_base.menu_sw_config" sequence="40"/>
    <menuitem id="menu_git_repository" action="git_repository_action"
              parent="maintenance_sw_base.menu_sw_config" sequence="50"/>
</odoo>
```

Dans `maintenance_sw_docker/__manifest__.py`, remplacer la clé `data` par :

```python
    "data": [
        "security/ir.model.access.csv",
        "views/git_repository_views.xml",
        "views/docker_image_views.xml",
        "views/docker_mount_views.xml",
        "views/maintenance_equipment_views.xml",
        "views/menus.xml",
    ],
```

- [ ] **Step 4: Lancer les tests**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_docker`
Expected: `0 failed, 0 error(s) of 32 tests`, `RESULT: OK`.

- [ ] **Step 5: Traduction française**

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh export maintenance_sw_docker`
Expected: `RESULT: OK`, `maintenance_sw_docker/i18n/maintenance_sw_docker.pot` créé.

Copier en `fr.po`, même en-tête que la Tâche 3 (ligne `# 	* maintenance_sw_docker`), et remplir **chaque** `msgstr` :

| Anglais | Français |
|---|---|
| Docker Inventory | Inventaire Docker |
| Docker Image(s) / Base Image | Image(s) Docker / Image de base |
| Registry / Repository / Tag / Digest / Build Date | Registre / Dépôt / Tag / Digest / Date de build |
| Git Repository / Git Repositories / Upstream / Host / URL | Dépôt git / Dépôts git / Origine amont / Hébergeur / URL |
| GitHub / GitLab / Other | GitHub / GitLab / Autre |
| Container(s) / Container Name | Conteneur(s) / Nom du conteneur |
| Mount(s) / Source / Destination / Type / Bind / Volume / Mode | Montage(s) / Source / Destination / Type / Bind / Volume / Mode |
| Read-write / Read-only | Lecture-écriture / Lecture seule |
| Usage / Code Repositories / Data / Configuration / Logs | Usage / Dépôts de code / Données / Configuration / Journaux |
| Component(s) / Effective Components | Composant(s) / Composants effectifs |
| Branch / Tag / Commit / Role / Merges / Overrides | Branche / Tag / Commit / Rôle / Fusions / Remplace |
| Core / Enterprise / OCA / Custom / Third Party | Cœur / Enterprise / OCA / Spécifique / Tiers |
| Runtime Changes | Modifications hors image |
| Software / Version / Notes / Group By | Logiciel / Version / Notes / Regrouper par |

Run: `~/dev/odoo/arpol-dev/run_sw_odoo.sh lang maintenance_sw_docker`
Expected: `RESULT: OK`.

- [ ] **Step 6: Commit**

```bash
git add maintenance_sw_docker
git commit -m "maintenance_sw_docker : vues, menus et traduction française"
```

---

### Task 8: Validation sur une copie neutralisée d'arpol.fr

**Files (hors dépôt, non commités) :**
- Create: `~/arpol-test/seed_arpol_server.py`, `~/arpol-test/screenshots.js`
- Données : `~/arpol-test/arpol.dump`, `~/arpol-test/odoo/` (filestore)

**Interfaces:**
- Consumes: modules des Tâches 1–7 ; image de prod `docker.0k.io/mirror/odoo:rc_18.0-ArPol` (contient déjà `maintenance_equipment_hierarchy`) ; `ovh_api` dans `~/ovh_api-18.0.1.5.0` (installé sur la base de prod) ; Playwright `~/tools/playwright`.
- Produces: instance `http://100.78.13.93:8070` (base `arpol_test`, réservée aux pairs Netbird), serveur arpol.fr saisi, captures `~/arpol-test/*.png`.

- [ ] **Step 1: Récupérer l'image, la base et le filestore**

```bash
mkdir -p ~/arpol-test/odoo/filestore
docker pull docker.0k.io/mirror/odoo:rc_18.0-ArPol
ssh arpol 'docker exec myc_postgres_1 pg_dump -U postgres -Fc "arpol.fr"' > ~/arpol-test/arpol.dump
ssh arpol 'tar czf - -C /srv/datastore/data/odoo-v18/var/lib/odoo/filestore arpol.fr' \
  | tar xzf - -C ~/arpol-test/odoo/filestore/
mv ~/arpol-test/odoo/filestore/arpol.fr ~/arpol-test/odoo/filestore/arpol_test
ls -la ~/arpol-test/arpol.dump ~/arpol-test/odoo/filestore/arpol_test | head -3
```

Expected : dump d'environ 30–60 Mo, dossier filestore présent. Si `docker pull` est refusé, se connecter au registre avec les identifiants décrits dans ArPol-Mind `Tech/0k/myc-manage` (§ identifiants registre).

- [ ] **Step 2: Restaurer dans un Postgres isolé et neutraliser**

```bash
docker network create arpol-test 2>/dev/null || true
docker run -d --name arpol-test-pg --network arpol-test \
  -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=arpoltest -e POSTGRES_DB=postgres postgres:16
until docker exec arpol-test-pg pg_isready -U odoo -h localhost >/dev/null 2>&1; do sleep 1; done
docker exec arpol-test-pg createdb -U odoo arpol_test
docker exec -i arpol-test-pg pg_restore -U odoo -d arpol_test --no-owner --role=odoo < ~/arpol-test/arpol.dump
docker exec -i arpol-test-pg psql -U odoo -d arpol_test -v ON_ERROR_STOP=0 <<'SQL'
UPDATE ir_cron SET active = false WHERE active = true;
UPDATE ir_mail_server SET active = false WHERE active = true;
UPDATE fetchmail_server SET active = false WHERE active = true;
UPDATE payment_provider SET state = 'test' WHERE state = 'enabled';
UPDATE ir_config_parameter SET value = 'test-migration.arpol.fr' WHERE key = 'mail.catchall.domain';
INSERT INTO ir_config_parameter (key, value, create_date, write_date, create_uid, write_uid)
  VALUES ('mail.force.smtp.from', 'neutralise@test-migration.arpol.fr', now(), now(), 1, 1)
  ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
UPDATE ir_config_parameter SET value = 'http://100.78.13.93:8070' WHERE key = 'web.base.url';
INSERT INTO ir_config_parameter (key, value, create_date, write_date, create_uid, write_uid)
  VALUES ('web.base.url.freeze', 'True', now(), now(), 1, 1)
  ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
SELECT 'crons actifs' AS check, COUNT(*) FROM ir_cron WHERE active = true
UNION ALL SELECT 'mail servers actifs', COUNT(*) FROM ir_mail_server WHERE active = true
UNION ALL SELECT 'paiements en prod', COUNT(*) FROM payment_provider WHERE state = 'enabled';
SQL
```

Expected : les trois compteurs à `0` (une erreur « relation does not exist » sur une table de module non installé est sans conséquence).

- [ ] **Step 3: Démarrer Odoo avec les modules du worktree**

```bash
sudo chown -R 1000:1000 ~/arpol-test/odoo 2>/dev/null || true
docker run -d --name arpol-test-odoo --network arpol-test \
  -p 100.78.13.93:8070:8069 \
  -e PGHOST=arpol-test-pg -e PGUSER=odoo -e PGPASSWORD=arpoltest -e PGDATABASE=arpol_test \
  -e DB_FILTER='^arpol_test$' -e LIST_DB=false -e PROXY_MODE=false -e WITHOUT_DEMO=all \
  -e ADMIN_PASSWORD="$(openssl rand -hex 12)" \
  -v ~/dev/odoo/arpol-dev/ArPol-odoo-dev-18.0:/opt/odoo/auto/dev/ArPol-odoo-dev:ro \
  -v ~/ovh_api-18.0.1.5.0:/opt/odoo/auto/dev/ovh_connector:ro \
  -v ~/arpol-test/odoo:/var/lib/odoo \
  docker.0k.io/mirror/odoo:rc_18.0-ArPol \
  odoo --addons-path=/opt/odoo/auto/dev/ArPol-odoo-dev,/opt/odoo/auto/dev/ovh_connector,/opt/odoo/auto/addons \
  --workers=0 --limit-time-cpu=300 --limit-time-real=300
sleep 20
curl -s -o /dev/null -w '%{http_code}\n' http://100.78.13.93:8070/web/login
```

Expected : `200`.

- [ ] **Step 4: Installer les modules par JSON-RPC (comme en prod)**

```bash
export BW_PASSWORD=$(timeout 15 secret-tool lookup service vaultwarden username gestion@arpol.fr)
export BW_SESSION=$(bw unlock --passwordenv BW_PASSWORD --raw)
export ODOO_PW=$(bw get password "ArPol.fr Odoo database")
python3 - <<'PY'
import os, xmlrpc.client
url, db = "http://100.78.13.93:8070", "arpol_test"
uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, "armand@arpol.fr", os.environ["ODOO_PW"], {})
m = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
call = lambda *a, **k: m.execute_kw(db, uid, os.environ["ODOO_PW"], *a, **k)
call("ir.module.module", "update_list", [])
ids = call("ir.module.module", "search", [[("name", "=", "maintenance_sw_docker")]])
call("ir.module.module", "button_immediate_install", [ids])
print(call("ir.module.module", "search_read",
           [[("name", "in", ["maintenance_equipment_hierarchy", "maintenance_sw_base", "maintenance_sw_docker"])]],
           {"fields": ["name", "state"]}))
PY
```

Expected : les trois modules en `installed`.

- [ ] **Step 5: Script de saisie du serveur arpol.fr**

`~/arpol-test/seed_arpol_server.py` (lit l'état réel d'arpol.fr par SSH, en lecture seule, et le saisit dans la copie) :

```python
#!/usr/bin/env python3
"""Seed the real arpol.fr server inventory into the arpol_test copy (read-only on arpol.fr)."""
import json
import os
import re
import subprocess
import xmlrpc.client

URL, DB, LOGIN = "http://100.78.13.93:8070", "arpol_test", "armand@arpol.fr"
PASSWORD = os.environ["ODOO_PW"]
CONTAINER = "myc_odoo-v18_1"
SRC = "/opt/odoo/custom/src"
DEV = "/opt/odoo/auto/dev"
HOST_REPOS = "/srv/datastore/data/odoo-v18/repos-arpol"


def ssh(cmd):
    return subprocess.run(["ssh", "arpol", cmd], check=True, capture_output=True, text=True).stdout


uid = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common").authenticate(DB, LOGIN, PASSWORD, {})
proxy = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)


def call(model, method, *args, **kwargs):
    return proxy.execute_kw(DB, uid, PASSWORD, model, method, list(args), kwargs)


def upsert(model, domain, values):
    ids = call(model, "search", domain, limit=1)
    if ids:
        call(model, "write", ids, values)
        return ids[0]
    return call(model, "create", values)


def ref(xmlid):
    module, name = xmlid.split(".")
    return call("ir.model.data", "search_read", [("module", "=", module), ("name", "=", name)],
                fields=["res_id"])[0]["res_id"]


def os_release(text):
    return dict(re.findall(r'^(\w+)="?([^"\n]*)"?$', text, re.M))


def version(product_id, name, **values):
    return upsert("software.version", [("product_id", "=", product_id), ("name", "=", name)],
                  {"product_id": product_id, "name": name, **values})


def repository(url, upstream_url=None):
    upstream_id = False
    if upstream_url and upstream_url != url:
        name = re.sub(r"^https?://[^/]+/|\.git$", "", upstream_url)
        upstream_id = upsert("git.repository", [("url", "=", upstream_url)],
                             {"name": name, "url": upstream_url})
    name = re.sub(r"^(https?://[^/]+/|[^:]+:/var/git/)|\.git$", "", url)
    return upsert("git.repository", [("url", "=", url)],
                  {"name": name, "url": url, "upstream_id": upstream_id})


def role(name, upstream):
    if name == "odoo":
        return "core"
    if name == "enterprise":
        return "enterprise"
    if "/OCA/" in (upstream or ""):
        return "oca"
    if "arpol" in (upstream or "").lower() or "arpol" in name.lower():
        return "custom"
    return "third_party"


# --- Catalog ---------------------------------------------------------------
debian = upsert("software.product", [("name", "=", "Debian")], {"name": "Debian", "vendor": "Debian Project",
                "website": "https://www.debian.org"})
odoo = upsert("software.product", [("name", "=", "Odoo")], {"name": "Odoo", "vendor": "Odoo SA",
              "website": "https://www.odoo.com"})
host_os = os_release(ssh("cat /etc/os-release"))
image_os = os_release(ssh(f"docker exec {CONTAINER} cat /etc/os-release"))
host_debian = version(debian, host_os["VERSION_ID"], sequence=int(host_os["VERSION_ID"]))
image_debian = version(debian, image_os["VERSION_ID"], sequence=int(image_os["VERSION_ID"]))
odoo18 = version(odoo, "18.0", sequence=180)

# --- Hardware and system ----------------------------------------------------
vps = upsert("maintenance.equipment", [("name", "=", "VPS arpol.fr")],
             {"name": "VPS arpol.fr", "equipment_kind": "hardware"})
system = upsert("maintenance.equipment", [("name", "=", "Debian (arpol.fr)")], {
    "name": "Debian (arpol.fr)", "equipment_kind": "software", "install_type": "os",
    "deployment_method_id": ref("maintenance_sw_base.deployment_method_manual"),
    "software_version_id": host_debian, "version_note": host_os.get("VERSION_CODENAME", ""),
    "parent_id": vps,
})
stack = upsert("maintenance.equipment", [("name", "=", "Stack 0k myc-deploy")], {
    "name": "Stack 0k myc-deploy", "equipment_kind": "software", "install_type": "compose_stack",
    "deployment_method_id": ref("maintenance_sw_base.deployment_method_myc"),
    "install_path": "/opt/apps/myc-deploy", "parent_id": system,
})

# --- Image --------------------------------------------------------------------
inspect = json.loads(ssh(f"docker inspect {CONTAINER}"))[0]
image_ref = inspect["Config"]["Image"]  # docker.0k.io/mirror/odoo:rc_18.0-ArPol
image_meta = json.loads(ssh(f"docker image inspect {image_ref}"))[0]
registry, _, rest = image_ref.partition("/")
repo_name, _, tag = rest.partition(":")
digest = (image_meta.get("RepoDigests") or ["@"])[0].split("@")[-1]
image = upsert("docker.image", [("repository", "=", repo_name), ("digest", "=", digest)], {
    "registry": registry, "repository": repo_name, "tag": tag, "digest": digest,
    "build_date": image_meta["Created"][:19].replace("T", " "), "version_id": odoo18,
    "note": f"<p>Debian {image_os['VERSION_ID']} ({image_os.get('VERSION_CODENAME', '')})</p>",
})

repos_yaml = ssh(f"docker exec {CONTAINER} cat {SRC}/repos.yaml")
image_components = {}
for block in re.split(r"^(?=\./)", repos_yaml, flags=re.M):
    head = re.match(r"\./([^:]+):", block)
    target = re.search(r"^\s+target:\s*(\S+)\s+(\S+)", block, re.M)
    if not head or not target:
        continue
    name, remote, ref_name = head.group(1), target.group(1), target.group(2)
    remotes = {k: v for k, v in re.findall(r"^\s+([\w-]+):\s*(\S+)\s*$", block, re.M) if "/" in v}
    upstreams = dict(re.findall(r"^\s+#\s*([\w-]+):\s*(https?://\S+)", block, re.M))
    merges = re.findall(r"^\s+-\s+(\S.*)$", block, re.M)
    if remote not in remotes:
        continue
    path = f"{SRC}/{name}"
    image_components[name] = upsert(
        "docker.component", [("image_id", "=", image), ("path", "=", path)], {
            "image_id": image, "path": path, "ref": ref_name, "merges": "\n".join(merges),
            "repository_id": repository(remotes[remote], upstreams.get(remote)),
            "role": role(name, upstreams.get(remote)),
        })

# --- Container, mounts --------------------------------------------------------
container = upsert("maintenance.equipment", [("name", "=", CONTAINER)], {
    "name": CONTAINER, "equipment_kind": "software", "install_type": "docker_container",
    "deployment_method_id": ref("maintenance_sw_base.deployment_method_myc"),
    "docker_image_id": image, "container_name": CONTAINER, "parent_id": stack,
    "runtime_changes": "Lien symbolique /opt/odoo/auto/addons/ovh_api -> "
                       "/opt/odoo/auto/dev/ovh_connector/ovh_api ajouté à la main le 2026-10-04 "
                       "(perdu si le conteneur est recréé).",
})
# 0k: the addons path is declared in compose.yml (service odoo-v18, docker-compose.command),
# which is the source of truth to edit; read it there rather than from the running container.
service = ssh("sed -n '/^odoo-v18:/,/^[a-z]/p' /opt/apps/myc-deploy/compose.yml")
addons_path = re.search(r'--addons-path=([^"\n]+)', service).group(1)
in_path = [p.strip() for p in addons_path.split(",")]
usages = {DEV: "repos", "/var/log/odoo": "logs", "/var/lib/odoo": "data"}
for mount in inspect["Mounts"]:
    mount_id = upsert("docker.mount", [("equipment_id", "=", container), ("destination", "=", mount["Destination"])], {
        "equipment_id": container, "source": mount["Source"], "destination": mount["Destination"],
        "mount_type": "volume" if mount["Type"] == "volume" else "bind",
        "mode": "rw" if mount["RW"] else "ro",
        "usage": usages.get(mount["Destination"], "config"),
    })
    if mount["Destination"] != DEV:
        continue
    listing = ssh(
        f"cd {HOST_REPOS} && for d in */; do d=${{d%/}}; "
        f"echo \"$d|$(git -C $d remote get-url origin 2>/dev/null)|$(git -C $d rev-parse HEAD 2>/dev/null)"
        f"|$(git -C $d rev-parse --abbrev-ref HEAD 2>/dev/null)\"; done")
    for line in listing.splitlines():
        name, url, commit, branch = line.split("|")
        if not url:
            continue  # not a git checkout (e.g. ovh_connector): recorded in runtime_changes
        path = f"{DEV}/{name}"
        overrides = image_components.get(name) if path in in_path else False
        upsert("docker.component", [("mount_id", "=", mount_id), ("path", "=", path)], {
            "mount_id": mount_id, "path": path, "ref": branch, "commit": commit,
            "repository_id": repository(url), "role": role(name, url),
            "overrides_id": overrides or False,
        })

effective = call("maintenance.equipment", "read", [container], fields=["effective_component_ids"])[0]
print(f"image components: {len(image_components)}, effective components: {len(effective['effective_component_ids'])}")
print(f"container id: {container}")
```

Run: `ODOO_PW=... python3 ~/arpol-test/seed_arpol_server.py` (variable exportée au Step 4)
Expected : `image components: 8x` (≈ 86, un par bloc de `repos.yaml`) et `effective components: ...` = composants d'image + 5 composants de montage − 1 remplacement (`ArPol-odoo-dev`, présent dans l'image et dans l'`addons_path` monté) ; dernière ligne `container id: <n>`.

- [ ] **Step 6: Vérifier les règles en JSON-RPC**

```bash
python3 - <<'PY'
import os, xmlrpc.client
url, db = "http://100.78.13.93:8070", "arpol_test"
uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, "armand@arpol.fr", os.environ["ODOO_PW"], {})
m = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
call = lambda *a, **k: m.execute_kw(db, uid, os.environ["ODOO_PW"], *a, **k)
c = call("maintenance.equipment", "search_read", [[("name", "=", "myc_odoo-v18_1")]],
         {"fields": ["complete_name", "software_version_id", "needs_attachment", "effective_component_ids"]})[0]
print(c["complete_name"], "|", c["software_version_id"], "| to attach:", c["needs_attachment"])
comps = call("docker.component", "read", c["effective_component_ids"], {"fields": ["path", "mount_id", "commit"]})
arpol = [x for x in comps if x["path"].endswith("/ArPol-odoo-dev")]
print("ArPol-odoo-dev effective:", arpol)
print("to attach:", call("maintenance.equipment", "search_count", [[("needs_attachment", "=", True)]]))
PY
```

Expected : `VPS arpol.fr / Debian (arpol.fr) / Stack 0k myc-deploy / myc_odoo-v18_1 | [.., 'Odoo 18.0'] | to attach: False` ; une seule entrée `ArPol-odoo-dev`, venant du montage (`/opt/odoo/auto/dev/ArPol-odoo-dev`, avec un commit) ; `to attach: 0`.

- [ ] **Step 7: Contrôle visuel (Playwright)**

`~/arpol-test/screenshots.js` :

```javascript
// Usage: CONTAINER_ID=<id> ODOO_PW=... node screenshots.js  (from ~/tools/playwright)
const { chromium } = require("playwright");
(async () => {
  const base = "http://100.78.13.93:8070";
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`${base}/web/login`, { waitUntil: "load" });
  await page.fill("input[name=login]", "armand@arpol.fr");
  await page.fill("input[name=password]", process.env.ODOO_PW);
  await Promise.all([page.waitForNavigation({ waitUntil: "load" }), page.click("button[type=submit]")]);
  const url = `${base}/odoo/action-maintenance.hr_equipment_action/${process.env.CONTAINER_ID}`;
  await page.goto(url, { waitUntil: "load" });
  await page.waitForSelector(".o_form_view");
  for (const tab of ["Software", "Logiciel", "Docker"]) {
    const link = page.locator(`.o_notebook a.nav-link:text-is("${tab}")`);
    if (await link.count()) {
      await link.first().click();
      await page.waitForTimeout(800);
      await page.screenshot({ path: `/home/armand/arpol-test/${tab.toLowerCase()}.png`, fullPage: true });
    }
  }
  await page.goto(`${base}/odoo/action-maintenance_sw_docker.docker_image_action`, { waitUntil: "load" });
  await page.waitForSelector(".o_list_view");
  await page.screenshot({ path: "/home/armand/arpol-test/images.png", fullPage: true });
  console.log(errors.length ? `JS errors: ${errors.join(" | ")}` : "no JS error");
  await browser.close();
})();
```

Run: `cd ~/tools/playwright && CONTAINER_ID=<id du Step 5> ODOO_PW=$ODOO_PW node ~/arpol-test/screenshots.js`
Expected : `no JS error`, et des captures `logiciel.png` (ou `software.png`), `docker.png`, `images.png` montrant l'onglet Logiciel (type, méthode 0k, version Odoo 18.0), l'onglet Docker (image, 4 montages, composants effectifs, modifications hors image) et la liste des images. Les regarder (outil Read) avant de conclure.

- [ ] **Step 8: Compte rendu**

Envoyer les captures à Armand, résumer ce qui a été saisi et vérifié, lister ce qui reste (push sur `origin/18.0`, déploiement sur arpol.fr, nettoyage de l'instance `arpol-test-*`) **sans** exécuter ces actions. Capitaliser dans ArPol-Mind (skill `search-and-memorize`) : note des deux modules sous `Dev/Odoo/ArPol-dev/ArPol-odoo-dev/18.0/`.
