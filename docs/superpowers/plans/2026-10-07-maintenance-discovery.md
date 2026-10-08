# Découverte d'un serveur — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un script bash `discover.sh` en lecture seule qui décrit un serveur en JSON, le module `maintenance_sw_odoo` (bases et modules Odoo installés), le module `maintenance_sw_discovery` (clés de découverte, import avec aperçu) et le module de liaison `maintenance_hosting_ovh_discovery` (support OVH trouvé par IP).

**Architecture:** Le script est autonome (bash ≥ 4, coreutils/busybox), structuré en fonctions de section qui écrivent chacune un fragment JSON ; toute lecture de fichier passe par `DISCOVER_ROOT` et toute commande par le `PATH`, ce qui permet de le tester avec des commandes simulées. Côté Odoo, un importeur (`AbstractModel`) transforme le JSON en une liste d'opérations (aperçu) puis les applique ; l'assistant n'est qu'une interface sur cet importeur.

**Tech Stack:** bash, Odoo 18.0 (ORM, `TransactionCase`, `subprocess` pour lancer le script dans les tests), image `odoo:18.0` + `postgres:16` jetables via `~/dev/odoo/arpol-dev/run_sw_odoo.sh`.

**Spec:** `docs/superpowers/specs/2026-10-07-maintenance-discovery-design.md`

## Global Constraints

- Dépôt `~/dev/odoo/arpol-dev/ArPol-odoo-dev-18.0`, branche `18.0-maintenance-sw`, jamais de push.
- Nouveaux modules en `18.0.1.0.0`, `AGPL-3`, auteur `Armand Polmard`, site `https://arpol.fr`, catégorie `Manufacturing/Maintenance`, en-tête de manifeste au style de `maintenance_sw_base/__manifest__.py`.
- Code et libellés en anglais ; `i18n/fr.po` complet (en-tête avec `Plural-Forms: nplurals=2; plural=(n > 1);`), terminologie existante.
- Droits : lecture `base.group_user`, tout `maintenance.group_equipment_manager` sur chaque nouveau modèle ; l'assistant est réservé aux gestionnaires.
- Script : lecture seule stricte, aucune dépendance obligatoire (ni Python ni `jq`), aucun secret en sortie, une section en échec n'arrête pas les autres.
- Commits en français, préfixés du module (`maintenance_sw_odoo : `…), sans `Co-Authored-By` ni mention d'outil.
- Aucune action sur le serveur de production `arpol` dans ce plan.

## Review Focus

- **Valeur contenant guillemets, barres obliques inverses, retours à la ligne, tabulations ou octets non UTF-8** (nom de conteneur, commande, chemin) : le JSON reste valide. → Tâche 2 (test d'échappement).
- **Secret dans une variable d'environnement de conteneur ou dans `odoo.conf`** : il n'apparaît jamais dans la sortie. → Tâche 3 (scénario avec `secret123` partout).
- **Commande absente ou en erreur** (pas de docker, `psql` refusé, `pct` absent) : section `skipped`/`error`, JSON valide, code de sortie 0. → Tâches 2 et 3.
- **Second import du même fichier** : aucune modification (tout `unchanged`). → Tâche 5.
- **Équipement saisi à la main avant la découverte** (arbre d'arpol.fr) : rattaché, pas dupliqué ; ses valeurs forcées et notes sont conservées. → Tâche 5.

---

## Structure des fichiers

```
maintenance_sw_odoo/
├── __init__.py, __manifest__.py
├── models/__init__.py, maintenance_odoo_database.py, maintenance_odoo_module.py, maintenance_equipment.py
├── security/ir.model.access.csv, security/maintenance_odoo_security.xml (règles multi-société)
├── views/maintenance_odoo_database_views.xml, maintenance_equipment_views.xml, menus.xml
├── i18n/maintenance_sw_odoo.pot, fr.po
└── tests/__init__.py, test_odoo_database.py

maintenance_sw_discovery/
├── __init__.py, __manifest__.py
├── static/discover.sh                      # le script (servi par Odoo)
├── models/__init__.py, maintenance_equipment.py, maintenance_host.py, discovery_importer.py
├── wizards/__init__.py, discovery_import_wizard.py, discovery_import_wizard_views.xml
├── security/ir.model.access.csv
├── views/maintenance_equipment_views.xml, menus.xml
├── i18n/maintenance_sw_discovery.pot, fr.po
└── tests/
    ├── __init__.py, common.py
    ├── test_script.py                       # lance discover.sh sur des scénarios simulés
    ├── test_importer.py, test_wizard.py
    ├── data/reference_0k_odoo.json         # JSON de référence pour l'import
    └── script/<scénario>/{root/…, bin/…}    # fichiers et commandes simulés

maintenance_hosting_ovh_discovery/
├── __init__.py, __manifest__.py (auto_install)
├── models/__init__.py, maintenance_host.py
└── tests/__init__.py, test_find_host.py
```

---

### Task 1: Module `maintenance_sw_odoo`

**Files:** tout le dossier `maintenance_sw_odoo/` ci-dessus.

**Interfaces:**
- Consumes: `maintenance.equipment` (`maintenance_sw_base`), `docker.component` et `effective_component_ids` (`maintenance_sw_docker`).
- Produces:
  - `maintenance.odoo.database` : `name` (requis), `equipment_id` (requis, `ondelete="cascade"`, index), `module_ids`, `module_count` (calculé), `last_discovery` (Datetime), `active` ; contrainte SQL `unique(equipment_id, name)` ; `_rec_names_search = ["name", "equipment_id.name"]`.
  - `maintenance.odoo.module` : `database_id` (requis, cascade, index), `name` (requis), `installed_version`, `state` (`installed`, `to_upgrade`, `to_remove`, défaut `installed`), `component_id` (Many2one `docker.component`, `ondelete="set null"`), `repository_id` (related `component_id.repository_id`, stocké), `active` ; contrainte SQL `unique(database_id, name)` ; `_order = "name"`.
  - `maintenance.equipment` : `odoo_database_ids` (One2many), `odoo_database_count`, `action_view_odoo_databases()`.
  - Règles multi-société (globales) : base `[('equipment_id.company_id', 'in', company_ids + [False])]`, module `[('database_id.equipment_id.company_id', 'in', company_ids + [False])]`.
  - Vues : liste/formulaire/recherche des bases (formulaire : modules en liste lecture seule avec regroupement par `repository_id` possible depuis la liste des modules), liste/recherche des modules (filtres par état, regroupements par base, dépôt), bouton « Odoo Databases » (`fa-database`) sur l'équipement, menus « Odoo Databases » et « Odoo Modules » sous `maintenance_sw_base.menu_sw_config`.
  - Français : Odoo Database(s) → Base(s) Odoo ; Module(s) → Module(s) ; Installed Version → Version installée ; To Upgrade → À mettre à jour ; To Remove → À supprimer ; Provided By (component) → Fourni par ; Repository → Dépôt.

- [ ] **Step 1: Tests** (`tests/test_odoo_database.py`) : création base + 2 modules ; `module_count` ; unicité (`IntegrityError` sous `mute_logger("odoo.sql_db")`) pour (équipement, nom) et (base, nom) ; `repository_id` suit `component_id` ; suppression de l'équipement supprime bases et modules ; `action_view_odoo_databases` filtre sur l'équipement ; règle multi-société (utilisateur de la société B ne lit pas la base d'un équipement de A, pattern de `maintenance_sw_docker/tests/test_security.py`) ; les vues se chargent (`get_view` du formulaire équipement contient `odoo_database_count`).
- [ ] **Step 2: RED** — `~/dev/odoo/arpol-dev/run_sw_odoo.sh test maintenance_sw_odoo` → `RESULT: FAILED`.
- [ ] **Step 3: Implémenter** modèles, sécurité, vues, menus, manifeste (`depends: ["maintenance_sw_docker"]`).
- [ ] **Step 4: GREEN** — même commande → `0 failed`, `RESULT: OK`.
- [ ] **Step 5: i18n** — `export` puis `fr.po` complet, `lang` → `RESULT: OK`, chargement du `fr.po` visible dans le log.
- [ ] **Step 6: Commit** — `maintenance_sw_odoo : bases Odoo et modules installés, reliés au dépôt qui les fournit`.

---

### Task 2: Script, socle et sections système (`maintenance_sw_discovery`)

**Files:**
- Create: `maintenance_sw_discovery/__init__.py`, `__manifest__.py` (`depends: ["maintenance_sw_odoo"]`, `data: []` pour l'instant), `static/discover.sh`, `tests/__init__.py`, `tests/test_script.py`, `tests/script/<scénario>/…`.

**Interfaces:**
- Produces: `discover.sh` (exécutable, `#!/usr/bin/env bash`, version `SCRIPT_VERSION="1.0.0"`), sortie JSON sur stdout au format de la spec ; options `--sudo`, `--help` ; variables d'environnement de test `DISCOVER_ROOT` (préfixe de toute lecture de fichier) ; code de sortie 0 dès que le JSON est produit.
- Helpers de test : `tests/test_script.py::run_scenario(name, extra_env=None) -> dict` (lance `bash static/discover.sh` avec `PATH=<scénario>/bin:/usr/bin:/bin`, `DISCOVER_ROOT=<scénario>/root`, `HOME` temporaire, et `json.loads` la sortie).

**Socle du script (obligatoire, à reprendre tel quel) :**

```bash
#!/usr/bin/env bash
# discover.sh — read-only description of a server for the Odoo maintenance inventory.
# Usage: discover.sh [--sudo] > "$(hostname).json"
set -u
SCRIPT_VERSION="1.0.0"
SCHEMA_VERSION=1
ROOT="${DISCOVER_ROOT:-}"
USE_SUDO=0
TMP="$(mktemp -d 2>/dev/null || mktemp -d -t discover)"
trap 'rm -rf "$TMP"' EXIT

json_str() {  # JSON string literal of $1 (invalid UTF-8 replaced by U+FFFD)
  local s
  s="$(printf '%s' "$1" | iconv -f UTF-8 -t UTF-8 -c 2>/dev/null || printf '%s' "$1")"
  s="${s//\\/\\\\}"; s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"; s="${s//$'\r'/\\r}"; s="${s//$'\t'/\\t}"
  s="$(printf '%s' "$s" | LC_ALL=C sed 's/[\x01-\x1f]//g')"
  printf '"%s"' "$s"
}
rf() { cat "${ROOT}$1" 2>/dev/null; }           # read a file of the target system
fe() { [ -e "${ROOT}$1" ]; }                     # file exists on the target system
have() { command -v "$1" >/dev/null 2>&1; }
run() {  # run a command with a timeout when available; never fails the script
  if have timeout; then timeout 30 "$@" 2>/dev/null; else "$@" 2>/dev/null; fi
}
priv() {  # command needing root: as is when root, with sudo -n when --sudo
  if [ "$(id -u)" = 0 ]; then run "$@"
  elif [ "$USE_SUDO" = 1 ] && have sudo; then run sudo -n "$@"
  else return 126; fi
}
section() {  # section NAME FUNCTION -> "NAME": {...}; FUNCTION prints the data object or
             # returns 3 with a reason on stdout (skipped)
  local name="$1" fn="$2" out rc
  out="$("$fn" 2>"$TMP/$name.err")"; rc=$?
  if [ $rc -eq 0 ]; then printf '%s: {"status": "ok", "data": %s}' "$(json_str "$name")" "$out"
  elif [ $rc -eq 3 ]; then printf '%s: {"status": "skipped", "reason": %s}' "$(json_str "$name")" "$(json_str "$out")"
  else printf '%s: {"status": "error", "message": %s}' "$(json_str "$name")" "$(json_str "$(head -c 500 "$TMP/$name.err")")"
  fi
}
```

Le bloc principal assemble `{"schema_version": 1, "script_version": …, "collected_at": <UTC ISO>, "sections": {<sections séparées par des virgules>}}`. Si `jq` est présent, le résultat est validé par `jq -e .` et, en cas d'échec, une sortie de secours `{"schema_version":1,…,"sections":{},"fatal":"invalid JSON produced"}` est émise (avec le JSON brut sous `"raw"` échappé) — le script ne sort jamais un JSON invalide sans le dire.

**Sections de cette tâche** (contenu exact dans la spec, table « Collecte ») : `machine`, `os`, `platforms`, `proxmox`, `zerok`, `cloudron`. Les sections `docker` et `odoo` existent déjà sous forme de fonctions qui retournent `skipped` (« not implemented ») — remplacées en Tâche 3.
- `machine.ips` : liste d'objets `{"address", "family": "inet"|"inet6", "interface"}`, hors loopback et hors adresses de lien local IPv6 (`fe80::`).
- `os.package_manager` : `dpkg` / `rpm` / `apk` / `null` selon `have`.
- `platforms` : `{"proxmox": {"version"}|null, "zerok": {"path"}|null, "cloudron": {"version"}|null, "docker": {"version"}|null}`.
- `proxmox.guests` : `[{"vmid", "name", "type": "qemu"|"lxc", "status", "ostype"}]` ; `skipped` si pas de `pveversion`.
- `zerok` : `{"path", "compose_yml": <texte brut du compose.yml sans les lignes dont la clé contient PASS/SECRET/TOKEN/KEY/CREDENTIAL/PRIVATE>, "services": [{"name", "charm", "image", "command": [..], "volumes": [..]}]}` — extraction ligne à ligne des services de premier niveau (`^[A-Za-z0-9._-]+:$`), de `charm:`, `image:`, des éléments de `command:` et `volumes:` (listes YAML `- …`) ; `skipped` si pas de `/opt/apps/myc-deploy/compose.yml`.
- `cloudron` : `{"version", "apps": [{"id", "name", "version", "domain"}]}` via `cloudron list --json` si présent, sinon depuis `docker ps --format` des conteneurs étiquetés Cloudron ; `skipped` sinon.

- [ ] **Step 1: Scénarios simulés** sous `tests/script/` :
  - `debian/` : `root/etc/os-release` (Debian 12), `root/etc/machine-id`, `bin/hostname`, `bin/ip` (sortie de `ip -j addr` avec lo, eth0 IPv4 + IPv6 globale + fe80), `bin/systemd-detect-virt` (`kvm`), `bin/uname`, `bin/dpkg` (vide) ; pas de docker.
  - `proxmox/` : idem + `bin/pveversion`, `bin/pct` (`list` : 2 LXC), `bin/qm` (`list` : 1 VM), `systemd-detect-virt` → `none`.
  - `cloudron/` : Ubuntu 24.04, `root/home/yellowtent/box/VERSION`, `bin/cloudron` (`list --json`).
  - `alpine/` : Alpine 3.20, `bin/apk`, pas de `ip -j` (sortie texte de `ip addr`), pas de `jq` ni `systemd-detect-virt`.
  - `weird/` : nom d'hôte et `PRETTY_NAME` contenant `"`, `\`, tabulation, retour à la ligne et un octet `\xff`.
  - Chaque `bin/*` est un petit script bash `#!/usr/bin/env bash` qui `case "$*"` et imprime une sortie figée ; `run_scenario` place `bin/` en tête du `PATH` et garde `/usr/bin:/bin` pour coreutils.
- [ ] **Step 2: Tests** (`tests/test_script.py`, classe `TestDiscoverScript(BaseCase)` ou `TransactionCase` ; `subprocess.run(["bash", SCRIPT], env=…, capture_output=True, timeout=60)`) :
  - pour chaque scénario : code de sortie 0, `json.loads` réussit, `schema_version == 1`, les 8 sections présentes avec un `status` valide ;
  - `debian` : `os.data.id == "debian"`, `version_id == "12"`, IP sans loopback ni fe80, `machine.data.virtualization == "vm"` ;
  - `proxmox` : 3 invités avec les bons types ; `platforms.data.proxmox.version` renseigné ;
  - `cloudron` : 2 applications ;
  - `alpine` : sections `ok` malgré l'absence de `jq` / `ip -j` / `systemd-detect-virt` (`virtualization` = `unknown` acceptable) ;
  - `weird` : les chaînes relues sont identiques aux originales (octet invalide remplacé par `�`) ;
  - `--help` : code 0 et texte d'usage ;
  - une commande simulée qui échoue (`bin/pct` qui `exit 1`) : section `error`, les autres `ok`.
- [ ] **Step 3: RED** — `run_sw_odoo.sh test maintenance_sw_discovery` (le module s'installe avec le seul `static/` et les tests) → échecs.
- [ ] **Step 4: Implémenter** le script (socle + 6 sections).
- [ ] **Step 5: GREEN** — `0 failed`, `RESULT: OK`. Vérifier aussi `bash -n static/discover.sh` et, si disponible localement, `shellcheck -S warning static/discover.sh` (corriger les avertissements ou les justifier en commentaire).
- [ ] **Step 6: Commit** — `maintenance_sw_discovery : script de découverte (socle, système, Proxmox, 0k, Cloudron)`.

---

### Task 3: Script, sections Docker et Odoo

**Files:** Modify `maintenance_sw_discovery/static/discover.sh`, `tests/test_script.py` ; Create `tests/script/zerok_odoo/…`, `tests/script/manual_odoo/…`.

**Interfaces:**
- `docker` : `{"version", "containers": [{"name", "inspect": <objet docker inspect avec Config.Env filtré>, "image_inspect": <objet docker image inspect>}]}` — uniquement les conteneurs en cours (`docker ps -q`) ; `skipped` si pas de docker ; `priv docker` si l'accès au socket l'exige. Filtrage de `Config.Env` : toute entrée `NOM=valeur` dont le NOM contient (insensible à la casse) `PASS`, `SECRET`, `TOKEN`, `KEY`, `CREDENTIAL`, `PRIVATE` devient `NOM=***`. Sans `jq`, le filtrage se fait par `sed` sur le JSON de `docker inspect` (entrées de la liste `"Env": [...]` au format `"NOM=valeur"`), avec un test dédié.
- `odoo` : `{"instances": [{"container", "version", "addons_path": [..], "addons": {"<dossier>": ["module", ...]}, "repos_yaml": <texte|null>, "repos": [{"path", "url", "branch", "commit"}], "mount_repos": [{"path", "url", "branch", "commit"}], "runtime_links": [{"link", "target"}], "config": {"db_host", "db_port", "db_name", "dbfilter", "data_dir", "addons_path"}, "databases": {"status": "ok"|"skipped"|"error", "reason"|"message", "items": [{"name", "modules": [{"name", "version", "state"}]}]}}]}`.
  - Conteneur Odoo : image dont le nom contient `odoo`, ou commande/entrypoint contenant `odoo`.
  - Version : `docker exec <c> odoo --version` (« Odoo Server 18.0-… » → `18.0`), sinon variable `ODOO_VERSION`.
  - `addons_path` : argument `--addons-path=` de la commande, sinon `odoo.conf` (`OPENERP_SERVER`/`ODOO_RC`, sinon `/etc/odoo/odoo.conf`, `/opt/odoo/auto/odoo.conf`) ; chemins séparés par virgule, espaces retirés.
  - `addons` : pour chaque dossier de l'`addons_path`, les sous-dossiers contenant `__manifest__.py` (une seule commande `docker exec <c> sh -c 'for d in …; do …; done'`).
  - `repos_yaml` : `docker exec <c> cat /opt/odoo/custom/src/repos.yaml` si présent.
  - `repos` : dossiers `.git` sous `/opt/odoo/custom/src/*` et les dossiers de l'`addons_path` (`git -C … remote get-url origin`, `rev-parse --abbrev-ref HEAD`, `rev-parse HEAD`) exécutés dans le conteneur s'il a `git`, sinon lus sur l'hôte pour les dossiers montés.
  - `mount_repos` : pour chaque montage `bind` du conteneur, les sous-dossiers git de la source sur l'hôte (avec `priv` si nécessaire) ; `path` = chemin dans le conteneur.
  - `runtime_links` : liens de `/opt/odoo/auto/addons` dont la cible n'est pas sous `/opt/odoo/custom/src/` (cas `ovh_api` → `/opt/odoo/auto/dev/ovh_connector/ovh_api`).
  - `config` : seulement les 6 clés de la spec, depuis `odoo.conf`.
  - `databases` : conteneur Postgres trouvé par `db_host` (= nom de conteneur ou alias réseau Docker du même réseau ; `docker ps` + `docker inspect` des réseaux) ; `docker exec <pg> psql -U <PGUSER du conteneur Odoo ou postgres> -Atc "<requête>"` ; liste des bases : `SELECT datname FROM pg_database WHERE NOT datistemplate` ; pour chacune, si `ir_module_module` existe : `SELECT name, latest_version, state FROM ir_module_module WHERE state IN ('installed','to upgrade','to remove') ORDER BY name` (séparateur `|`) ; `state` normalisé `to upgrade` → `to_upgrade`, `to remove` → `to_remove`. Aucun mot de passe n'est lu ni affiché (le `psql` du conteneur Postgres en local n'en demande pas ; sinon `skipped` avec la raison).
- [ ] **Step 1: Scénarios** : `zerok_odoo/` (Debian 10 hôte + 0k + `bin/docker` simulant `ps -q`, `inspect`, `image inspect`, `exec` pour `odoo --version`, `cat repos.yaml`, la liste des addons, `readlink` des liens, `psql` sur 2 bases dont une sans `ir_module_module` ; `Config.Env` contenant `PGPASSWORD=secret123`, `ADMIN_PASSWORD=secret123` ; `odoo.conf` simulé avec `admin_passwd = secret123`, `db_password = secret123`) ; `manual_odoo/` (image `odoo:18.0`, addons montés avec `.git` simulés sur l'hôte sous `root/srv/addons/*/.git` + `bin/git`) ; `docker_denied/` (`docker` qui échoue : permission refusée).
- [ ] **Step 2: Tests** : `zerok_odoo` — une instance, `version == "18.0"`, `addons_path` de la commande, `runtime_links` contient le lien hors image, `databases.items` = 1 base (la seconde ignorée) avec ses modules et états normalisés, **`secret123` absent de toute la sortie brute** (test sur la chaîne avant `json.loads`), `config` limité aux 6 clés ; `manual_odoo` — `mount_repos` avec URL/branche/commit ; `docker_denied` — sections `docker` et `odoo` en `skipped` ou `error`, JSON valide ; scénarios de la Tâche 2 inchangés.
- [ ] **Step 3: RED**, **Step 4: Implémenter**, **Step 5: GREEN** (+ `bash -n`, `shellcheck` si disponible).
- [ ] **Step 6: Exécution réelle locale** sur arpol-brain (Debian, Docker avec `casa-test-*`, `arpol-test-*`) : `bash maintenance_sw_discovery/static/discover.sh > /tmp/arpol-brain.json` puis `python3 -m json.tool /tmp/arpol-brain.json >/dev/null` ; vérifier qu'aucun secret connu des conteneurs de test (valeurs de `PGPASSWORD`, `ADMIN_PASSWORD` lues par `docker inspect` avant) n'apparaît (`grep -c`), et que les instances Odoo `arpol-test-odoo` / `casa-test-odoo` sont décrites avec leurs bases. Ne rien modifier sur la machine.
- [ ] **Step 7: Commit** — `maintenance_sw_discovery : découverte des conteneurs Docker et des instances Odoo (bases, modules, dépôts)`.

---

### Task 4: Clés de découverte et importeur

**Files:** `maintenance_sw_discovery/models/__init__.py`, `maintenance_equipment.py`, `maintenance_host.py`, `discovery_importer.py`, `security/ir.model.access.csv` (si modèle transitoire), `tests/common.py`, `tests/test_importer.py`, `tests/data/reference_0k_odoo.json`, `__manifest__.py`.

**Interfaces:**
- `maintenance.equipment` : `discovery_key` (Char, index, copy=False), `last_discovery` (Datetime), `missing_since_discovery` (Boolean) ; index SQL unique partiel `CREATE UNIQUE INDEX … ON maintenance_equipment (discovery_key) WHERE discovery_key IS NOT NULL` (via `init()`).
- `maintenance.host` : `discovery_key` (même index unique partiel), méthode `_discovery_find_host(self, ips) -> maintenance.host` (renvoie un recordset vide ; surchargée par le module de liaison).
- `maintenance.discovery.importer` (`AbstractModel`) :
  - `_parse(self, raw: bytes|str) -> dict` : `json.loads`, vérifie `schema_version == 1`, sinon `UserError` explicite.
  - `_plan(self, data, host=None, customer=None, matches=None) -> list[dict]` : liste d'opérations ordonnées `{"key", "model", "action": "create"|"update"|"unchanged"|"missing", "record_id", "label", "values", "changes": [str], "parent_key"}` ; ne modifie rien. `matches` : `{discovery_key: record_id}` choisis par l'utilisateur pour des équipements existants sans clé.
  - `_suggest(self, data) -> dict` : `{"host_id", "matches": {key: record_id}}` — support : OS existant par clé `machine:<id>` → son `physical_host_id`, sinon `maintenance.host._discovery_find_host(ips)` ; correspondances par nom (OS : `name` égal au nom d'hôte ou contenant le nom d'hôte, `install_type = os`, sans clé ; conteneur : `name` ou `container_name` égal au nom du conteneur, sans clé).
  - `_apply(self, data, host=None, customer=None, matches=None, attachment_name=None) -> maintenance.equipment` (racine) : exécute le plan dans la transaction courante.
- Construction (spec, « Arbre construit ») : clés `machine:`, `pve:`, `stack:`, `cloudron:`, `container:`, `cloudron-app:`, `pve-guest:` ; produits/versions du catalogue créés s'ils manquent (`Debian`/`Ubuntu`/`Rocky Linux`/`AlmaLinux`/`CentOS`/`Alpine Linux` selon `os.id`, version = `VERSION_ID`, `sequence` = partie entière majeure×100+mineure ; `Proxmox VE` ; `Odoo` série `NN.0` ; `Cloudron`) ; méthodes : OS → `deployment_method_manual`, stack/conteneurs 0k → `deployment_method_myc`, Cloudron → `deployment_method_cloudron`, conteneurs hors 0k/Cloudron → `deployment_method_manual`.
- Images : `docker.image` par (`repository`, `digest`) depuis `image_inspect` (`RepoDigests`, `Created`, tag depuis `Config.Image`) ; version Odoo sur l'image quand l'instance Odoo est connue.
- Composants d'image : depuis `repos_spec.items` (structuré par le script : `name`, `path`, `target` {remote, ref}, `remotes` {nom: url masquée}, `upstreams` {nom: url}, `merges`) — dépôt = `remotes[target.remote]`, amont = `upstreams[target.remote]`, `ref` = `target.ref`, `merges` joints par retour à la ligne — ou, à défaut, `repos` (dossiers `.git`) ; montages : `docker.mount` par (équipement, destination) avec usage (`repos` si la destination porte des dépôts ou est dans l'`addons_path`, `logs` pour `/var/log*`, `data` pour `/var/lib*`, sinon `config`), composants depuis `mount_repos`, `overrides_id` quand le dossier monté est dans l'`addons_path` et qu'un composant d'image a le même nom de dossier.
- Odoo : `maintenance.odoo.database` par (équipement, nom), modules par (base, nom), `component_id` = composant effectif dont le `path` est le premier dossier de l'`addons_path` (ordre de l'`addons_path`) dont la liste `addons` contient le module, rapproché par `path` (chemin de dossier ; pour `/opt/odoo/auto/addons`, résolution via le lien vers `/opt/odoo/custom/src/<dépôt>/<module>`).
- Mise à jour : un enregistrement existant n'est réécrit que si une valeur mesurée change ; jamais `name` (sauf création), `physical_host_id`/`customer_id` forcés, `note`, `runtime_changes` existants (ajout d'un bloc « Discovery of <date> » si des liens sont trouvés et pas déjà mentionnés) ; absents → `missing_since_discovery = True`, `active = False` ; réapparus → l'inverse.
- Racine : `physical_host_id` = `host` si fourni (forcé), `customer_id` = `customer` si fourni (forcé) ; pièce jointe JSON (`ir.attachment`, `res_model = maintenance.equipment`, `res_id` = racine, nom `discovery-<hostname>-<date>.json`) ; `last_discovery` sur tout ce qui est vu.

- [ ] **Step 1: JSON de référence** `tests/data/reference_0k_odoo.json` : produit en lançant le script sur le scénario `zerok_odoo` (Tâche 3) puis figé ; documenter en tête de `tests/common.py` comment le régénérer.
- [ ] **Step 2: Tests** (`tests/test_importer.py`) : fichier invalide / `schema_version` 2 → `UserError` ; premier import → arbre OS → stack → conteneur, catalogue (Debian 10, Odoo 18.0), image avec digest, montages et composants (dont un remplacement), base et modules avec `component_id`, pièce jointe sur la racine, clés posées ; second import identique → `_plan` ne contient que `unchanged`, aucun `write_date` modifié ; import modifié (conteneur retiré, nouveau digest) → conteneur archivé + `missing_since_discovery`, nouvelle `docker.image`, ancienne conservée ; réapparition → désarchivé ; arbre saisi à la main (OS « Debian (arpol.fr) » avec support forcé, conteneur `myc_odoo-v18_1` avec note) + `matches` → rattachement, aucune duplication, support/note conservés ; `host`/`customer` passés → forcés sur la racine ; `_suggest` propose les correspondances par nom.
- [ ] **Step 3: RED**, **Step 4: Implémenter** (importeur découpé en méthodes par niveau : `_plan_os`, `_plan_platforms`, `_plan_containers`, `_plan_odoo`, et un `_apply_op` générique), **Step 5: GREEN**.
- [ ] **Step 6: Commit** — `maintenance_sw_discovery : clés de découverte et import d'un fichier de découverte`.

---

### Task 5: Assistant d'import

**Files:** `maintenance_sw_discovery/wizards/*`, `views/maintenance_equipment_views.xml`, `views/menus.xml`, `security/ir.model.access.csv`, `__manifest__.py` (`data`), `i18n/*`, `tests/test_wizard.py`.

**Interfaces:**
- `maintenance.discovery.import.wizard` (TransientModel) : `file_ids` (Many2many `ir.attachment`, `string="Discovery Files"`) ou `discovery_file` (Binary) + `filename` pour un fichier — **un fichier par assistant** en v1 (plusieurs fichiers = relancer), `state` (`upload`, `preview`, `done`), `host_id`, `customer_id`, `line_ids` (One2many lignes), `root_equipment_id` (résultat) ; boutons `action_analyse` (parse + `_suggest` + `_plan` → lignes), `action_apply`, `action_back`.
- `maintenance.discovery.import.line` (TransientModel) : `wizard_id`, `key`, `model`, `label`, `action`, `changes` (Text), `match_id` (Many2one `maintenance.equipment`, éditable pour les lignes `create` d'OS ou de conteneur : rattacher à un équipement existant), `record_ref` (Char `model,id` pour ouvrir).
- Vue : étape 1 fichier + bouton « Analyse » ; étape 2 support, client, liste des lignes groupées par action (`create`/`update`/`unchanged`/`missing`), boutons « Apply » / « Back » ; étape 3 lien vers l'équipement racine. Menu « Import Discovery » sous `maintenance_sw_base.menu_sw_config`, groupe `maintenance.group_equipment_manager` ; lien « Download the discovery script » (URL `/maintenance_sw_discovery/static/discover.sh`) dans l'étape 1.
- Équipement : `discovery_key`, `last_discovery`, `missing_since_discovery` en lecture seule dans un groupe « Discovery » de l'onglet Logiciel ; filtre « Missing at Last Discovery ».
- Français : Import Discovery → Importer une découverte ; Analyse → Analyser ; Apply → Appliquer ; Discovery Key → Clé de découverte ; Last Discovery → Dernière découverte ; Missing at Last Discovery → Absent à la dernière découverte ; Create/Update/Unchanged/Missing → Créer / Mettre à jour / Inchangé / Absent.

- [ ] **Step 1: Tests** (`tests/test_wizard.py`, via `odoo.tests.Form` et appels de méthodes) : analyse du JSON de référence → lignes `create`, support suggéré vide, puis `match_id` d'une ligne mis sur un équipement existant → `action_apply` rattache ; fichier invalide → `UserError` lisible ; second passage → toutes les lignes `unchanged` ; menu présent, réservé aux gestionnaires ; le script est servi (`self.url_open('/maintenance_sw_discovery/static/discover.sh')` dans un `HttpCase`, statut 200, commence par `#!/usr/bin/env bash`).
- [ ] **Step 2: RED**, **Step 3: Implémenter**, **Step 4: GREEN**.
- [ ] **Step 5: i18n** — export, `fr.po` complet, `lang` OK.
- [ ] **Step 6: Commit** — `maintenance_sw_discovery : assistant d'import avec aperçu et rattachement`.

---

### Task 6: Module de liaison `maintenance_hosting_ovh_discovery`

**Files:** tout `maintenance_hosting_ovh_discovery/`.

**Interfaces:** manifeste `depends: ["maintenance_hosting_ovh", "maintenance_sw_discovery"]`, `auto_install: True`, `data: []` ; `maintenance.host._discovery_find_host(ips)` surchargé : `super()` d'abord ; si vide, parmi `ovh.service` (sudo) actifs de type `vps`/`dedicated`, celui dont `raw_payload["ips"]` contient une des adresses de `ips` (liste de chaînes) → son `maintenance.host` lié (`ovh_service_id`), sinon recordset vide.

- [ ] **Step 1: Tests** : service VPS avec `raw_payload = {"ips": ["152.228.135.45", "2001:…"]}` (créé via `_upsert` du pont avec un payload contenant `ips`, ou écrit directement) → trouvé par une IPv4 et par l'IPv6 ; IP inconnue → vide ; service archivé ignoré ; `_suggest` de l'importeur propose ce support.
- [ ] **Step 2: RED**, **Step 3: Implémenter**, **Step 4: GREEN** (`run_sw_odoo.sh test maintenance_hosting_ovh_discovery`).
- [ ] **Step 5: Commit** — `maintenance_hosting_ovh_discovery : support physique OVH reconnu par adresse IP à l'import`.

---

### Task 7: Validation locale (sans la production)

- [ ] **Step 1:** sur arpol-brain, `bash maintenance_sw_discovery/static/discover.sh > ~/arpol-test/arpol-brain.json` (lecture seule) ; JSON valide ; aucun secret (comparer aux valeurs `*PASSWORD*` des `docker inspect` des conteneurs `arpol-test-*`, `casa-test-*`).
- [ ] **Step 2:** sur la copie `arpol_test` (http://100.78.13.93:8070) : `docker restart arpol-test-odoo`, `update_list`, installation de `maintenance_sw_odoo`, `maintenance_sw_discovery` (et vérification que `maintenance_hosting_ovh_discovery` s'installe ou installation manuelle), puis import de `arpol-brain.json` par l'assistant en JSON-RPC (create → `action_analyse` → `action_apply`) avec un support créé « arpol-brain (Tardis CT 103) » ; vérifier l'arbre (Debian 12 → conteneurs `arpol-test-odoo`, `casa-test-odoo`… → bases `arpol_test`, `casaangels_test` et leurs modules avec dépôts) ; second import → tout `unchanged`.
- [ ] **Step 3:** captures Playwright (`~/arpol-test/disc-*.png`) : assistant (aperçu), équipement racine, conteneur Odoo avec bouton « Bases Odoo », formulaire d'une base avec ses modules groupés par dépôt ; `no JS error`.
- [ ] **Step 4:** rapport. **L'exécution sur arpol.fr n'est pas faite** : elle sera proposée à Armand, qui décide.
