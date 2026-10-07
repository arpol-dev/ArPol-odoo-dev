# Design — Découverte d'un serveur (`discover.sh`, `maintenance_sw_odoo`, `maintenance_sw_discovery`)

**Date :** 2026-10-07  
**Auteur :** Armand Polmard  
**Version Odoo :** 18.0  
**Dépôt :** `ArPol-odoo-dev` (branche `18.0-maintenance-sw`)  
**Complète :** `2026-10-04-maintenance-software-inventory-design.md`, `2026-10-06-maintenance-host-domain-ovh-design.md`

---

## Contexte

Les modules `maintenance_sw_base`, `maintenance_sw_docker` et `maintenance_hosting_ovh` décrivent un serveur
(OS, plateforme, conteneurs, images, montages, dépôts, support physique, client, domaines), saisi à la main.
Ce lot automatise la collecte : un script bash, lancé à la main sur un serveur, produit un fichier JSON
qu'un assistant importe dans Odoo, après aperçu. Odoo étant le principal sujet de travail, la collecte va
jusqu'aux bases de données et aux modules installés, stockés par un nouveau module `maintenance_sw_odoo`.

### Décisions prises

- Le script **ne fait que lire** ; il n'installe rien, n'exige ni Python ni `jq` (utilisé s'il est présent),
  ne porte aucun identifiant Odoo. Le serveur n'a pas besoin de joindre Odoo.
- Résultat = **un fichier JSON**, importé par un assistant Odoo qui montre ce qui va être créé ou mis à jour
  avant d'écrire.
- OS visés : famille Debian/Ubuntu (dont Proxmox VE et Cloudron), famille Red Hat (Rocky, Alma, CentOS),
  Alpine ; détection par `/etc/os-release`.
- Bases Odoo et modules installés collectés et stockés (`maintenance_sw_odoo`).

---

## Le script `discover.sh`

**Emplacement :** `maintenance_sw_discovery/static/discover.sh` (servi publiquement par Odoo) :

```bash
curl -s https://<odoo>/maintenance_sw_discovery/static/discover.sh | bash > "$(hostname).json"
ssh serveur 'bash -s' < discover.sh > serveur.json          # depuis une autre machine
```

Option `--sudo` : relance les commandes qui l'exigent avec `sudo -n` (sans demander de mot de passe) ; sans
elle et sans root, les sections qui en ont besoin sont marquées sautées.

### Collecte

| Section | Contenu | Source |
|---|---|---|
| `machine` | nom d'hôte, `machine-id`, IP (v4/v6, hors loopback), virtualisation (`physical`, `vm`, `lxc`, `container`, `unknown`) | `hostname`, `/etc/machine-id`, `ip -j addr` ou `ip addr`, `systemd-detect-virt` ou `/proc/1/environ`, `/proc/cpuinfo` |
| `os` | `ID`, `VERSION_ID`, `VERSION_CODENAME`, `PRETTY_NAME`, noyau, gestionnaire de paquets (`dpkg`, `rpm`, `apk` ou aucun) | `/etc/os-release`, `uname -r` |
| `platforms` | détections : `proxmox` (version), `0k` (chemin `/opt/apps/myc-deploy`, présence de `compose`), `cloudron` (version), `docker` (version) | `pveversion`, fichiers, `cloudron`/`/home/yellowtent`, `docker version` |
| `proxmox` | VM et LXC : `vmid`, nom, type (`qemu`/`lxc`), état, `ostype` | `qm list`, `pct list`, `pct config`, `qm config` (lecture) |
| `zerok` | services du `compose.yml` (nom, charm, image, `command`, volumes) | `/opt/apps/myc-deploy/compose.yml` (texte brut + extraction) |
| `cloudron` | version ; applications (id, nom, version, domaine) | `cloudron` CLI si présent, sinon `docker ps` des conteneurs Cloudron |
| `docker` | pour chaque conteneur en cours : `docker inspect` brut (variables d'environnement filtrées), `docker image inspect` de son image | `docker` |
| `odoo` | pour chaque conteneur Odoo (image ou commande contenant `odoo`) : version (`odoo --version`), `addons_path` effectif (commande puis `odoo.conf`), modules présents par dossier de l'`addons_path` (dossiers avec `__manifest__.py`), `repos.yaml` brut s'il existe, dépôts git (URL, branche, commit) des dossiers de l'image et des montages, liens symboliques de `/opt/odoo/auto/addons` absents de l'image, bases et modules installés | `docker exec` (lecture), `psql` dans le conteneur Postgres relié |

**Bases et modules** : le conteneur Postgres est trouvé par `db_host` (configuration Odoo ou variable
`HOST`/`PGHOST`), puis le nom de conteneur ou le réseau Docker ; requête en lecture seule, par base listée
dans `pg_database` (hors gabarits) contenant `ir_module_module` :
`SELECT name, latest_version, state FROM ir_module_module WHERE state IN ('installed','to upgrade','to remove')`.
Introuvable ou refus : section `skipped` avec la raison, sans échec.

### Garanties

- Lecture seule : aucune commande d'écriture, aucun `compose`/`restart`/`up`, aucun fichier créé hors de la
  sortie standard (fichiers temporaires dans `mktemp -d`, supprimés en fin).
- Secrets : les variables d'environnement dont le nom contient `PASS`, `SECRET`, `TOKEN`, `KEY`,
  `CREDENTIAL`, `PRIVATE` sont remplacées par `"***"` ; aucun contenu de base hors `ir_module_module` ;
  `odoo.conf` : seules les clés `addons_path`, `db_host`, `db_port`, `db_name`, `dbfilter`, `data_dir` sont
  gardées.
- Robustesse : chaque section s'exécute isolément ; un échec donne `{"status": "error", "message": ...}` et
  n'arrête pas les autres ; délai maximal par commande externe (`timeout 30` si disponible).
- JSON valide quel que soit le contenu : fonction d'échappement unique (guillemets, barres obliques
  inverses, caractères de contrôle, non-UTF-8 remplacé) ; `jq` sert seulement à valider s'il est présent.
- Compatibilité : bash ≥ 4, coreutils/busybox ; aucune dépendance obligatoire au-delà.

### Format

```json
{
  "schema_version": 1,
  "script_version": "1.0.0",
  "collected_at": "2026-10-07T10:00:00Z",
  "sections": {
    "machine": {"status": "ok", "data": {...}},
    "os": {"status": "ok", "data": {...}},
    "platforms": {...}, "proxmox": {"status": "skipped", "reason": "not a Proxmox host"},
    "zerok": {...}, "cloudron": {...}, "docker": {...}, "odoo": {...}
  }
}
```

`status` ∈ `ok`, `skipped` (avec `reason`), `error` (avec `message`). Les réponses brutes utiles
(`docker inspect`, `repos.yaml`, `compose.yml` filtré) sont conservées telles quelles sous `raw`.

---

## Module `maintenance_sw_odoo`

**Dépend de :** `maintenance_sw_docker`.

### `maintenance.odoo.database`

| Champ | Type | Remarque |
|---|---|---|
| `name` | Char, requis | Nom de la base |
| `equipment_id` | Many2one `maintenance.equipment`, requis, `ondelete="cascade"` | Conteneur (ou logiciel) Odoo qui la sert |
| `module_ids` | One2many `maintenance.odoo.module` | |
| `module_count` | Integer calculé | |
| `last_discovery` | Datetime | |
| `active` | Boolean | |

Contrainte : (`equipment_id`, `name`) unique. Sur l'équipement : `odoo_database_ids`, bouton « Bases Odoo ».

### `maintenance.odoo.module`

| Champ | Type | Remarque |
|---|---|---|
| `database_id` | Many2one, requis, `ondelete="cascade"` | |
| `name` | Char, requis | Nom technique |
| `installed_version` | Char | |
| `state` | Selection | `installed`, `to_upgrade`, `to_remove` |
| `component_id` | Many2one `docker.component` | Composant effectif qui fournit le module (premier dossier de l'`addons_path` qui le contient) |
| `repository_id` | related `component_id.repository_id`, stocké | Regroupement par dépôt |
| `active` | Boolean | |

Contrainte : (`database_id`, `name`) unique. Vues : liste des bases, formulaire avec la liste des modules
(regroupement par dépôt), recherche ; menus sous Maintenance > Configuration > Logiciels.
Droits : lecture `base.group_user`, tout `maintenance.group_equipment_manager`. Règle multi-société : la base
suit son équipement. Français dans `i18n/fr.po`.

---

## Module `maintenance_sw_discovery`

**Dépend de :** `maintenance_sw_odoo` (et donc `maintenance_sw_base`, `maintenance_sw_docker`).

### Clé de découverte

`discovery_key` (Char, index unique quand renseigné) sur `maintenance.equipment` et `maintenance.host` ;
`last_discovery` (Datetime) et `missing_since_discovery` (Boolean) sur `maintenance.equipment`.

| Objet | Modèle | Clé |
|---|---|---|
| OS du serveur (racine, `install_type = os`) | `maintenance.equipment` | `machine:<machine-id>` |
| Stack 0k (`compose_stack`, méthode 0k) | `maintenance.equipment` | `stack:<machine-id>:/opt/apps/myc-deploy` |
| Instance Cloudron (méthode Cloudron) | `maintenance.equipment` | `cloudron:<machine-id>` |
| Proxmox VE (logiciel) | `maintenance.equipment` | `pve:<machine-id>` |
| Conteneur Docker | `maintenance.equipment` | `container:<machine-id>:<nom>` |
| Application Cloudron | `maintenance.equipment` | `cloudron-app:<machine-id>:<id>` |
| VM / LXC Proxmox | `maintenance.host` (`host_type = vm`) | `pve-guest:<machine-id>:<vmid>` |

Les objets déjà modélisés gardent leur identité : `docker.image` (`repository`, `digest`), `git.repository`
(`url`), `docker.component` (image ou montage + `path`), `docker.mount` (équipement + destination),
`maintenance.odoo.database` (équipement + nom), `maintenance.odoo.module` (base + nom). Produits et versions
du catalogue créés s'ils manquent (Debian/Ubuntu/Rocky/Alma/CentOS/Alpine + `VERSION_ID`, Proxmox VE, Odoo +
série `NN.0`, PostgreSQL + majeure, Cloudron).

### Arbre construit

- Racine : l'OS (`install_type = os`, méthode « Manuel »), `physical_host_id` = support choisi.
- Sous l'OS, selon les plateformes : Proxmox VE (`package`), stack 0k, instance Cloudron.
- Sous la stack 0k ou l'instance Cloudron (sinon sous l'OS) : un équipement par conteneur Docker
  (`docker_container`) avec image, montages, composants (image depuis `repos.yaml` ou `.git`, montages depuis
  leurs `.git`, remplacements si le dépôt monté est dans l'`addons_path` à la place de celui de l'image),
  `runtime_changes` (liens symboliques hors image).
- Pour chaque conteneur Odoo : version Odoo, bases et modules (`maintenance_sw_odoo`), composant de chaque
  module.
- Applications Cloudron sans conteneur Docker visible : équipement logiciel (méthode Cloudron, version).
- Invités Proxmox : un `maintenance.host` (`vm`) par VM/LXC, `equipment_id` = l'équipement matériel du
  support du Proxmox s'il existe ; la découverte d'un invité se fait en relançant le script dans l'invité.

### Assistant `maintenance.discovery.import.wizard`

1. **Fichiers** : un ou plusieurs JSON ; refus explicite si illisible ou `schema_version` inconnu.
2. **Rattachement** (par fichier, modifiable) :
   - support physique : proposé par `discovery_key` de l'OS existant, sinon par la méthode
     `_discovery_find_host(ips)` de `maintenance.host` (vide dans ce module, surchargée par le pont OVH pour
     chercher un VPS/dédié OVH dont la réponse brute contient une des IP), sinon création proposée au nom
     d'hôte ;
   - client : posé sur la racine (forcé) ;
   - équipements existants sans clé reconnus par nom (OS par nom d'hôte, conteneur par nom) : rattachement
     proposé, à confirmer ligne par ligne.
3. **Aperçu** : une ligne par objet (`create`, `update`, `unchanged`, `missing`) avec un résumé des
   changements ; rien n'est écrit.
4. **Application** : une transaction ; le JSON est joint (`ir.attachment`) à l'équipement racine ;
   `last_discovery` mis à jour.

### Règles de mise à jour

- Rien n'est supprimé : un conteneur, une application, une base ou un module absent du fichier est marqué
  `missing_since_discovery` et archivé ; il est désarchivé s'il réapparaît.
- Les saisies manuelles sont respectées : support et client forcés, notes, nom de l'équipement,
  `runtime_changes` déjà saisis (la découverte ajoute sous un titre « Découverte du <date> » plutôt que
  d'écraser).
- La découverte réécrit seulement ce qu'elle mesure : version, image, montages, composants, bases, modules.
- Nouvelle image (nouveau digest) : nouvel enregistrement `docker.image`, l'ancien est conservé.

---

## Module de liaison `maintenance_hosting_ovh_discovery`

Pour n'imposer ni la découverte au pont OVH ni l'inverse, la recherche du support OVH par IP vit dans un petit
module à installation automatique (`auto_install`) quand `maintenance_hosting_ovh` et
`maintenance_sw_discovery` sont présents. Il surcharge `maintenance.host._discovery_find_host(ips)` : parmi
les `ovh.service` actifs de type `vps` ou `dedicated`, celui dont la réponse brute (`ips`) contient une des IP
donne son `maintenance.host`.

---

## Tests

- **Script** (`maintenance_sw_discovery/tests/script/`, lancés par un test Odoo qui exécute bash) : un
  répertoire de commandes simulées par scénario, placé en tête du `PATH` (`hostname`, `cat` de fichiers
  factices via une racine `DISCOVER_ROOT`, `docker`, `pveversion`, `pct`, `qm`, `cloudron`, `psql` via
  `docker exec`, `jq` absent) : Debian simple, Proxmox, 0k avec Odoo, Cloudron, Odoo manuel (`.git`), Alpine
  sans `jq`. Pour chacun : JSON valide (`json.loads`), sections attendues, aucun secret (valeurs factices
  `secret123` jamais présentes), caractères spéciaux préservés.
- **Odoo** : import complet d'un JSON de référence (0k + Odoo + 2 bases) ; second import identique sans
  changement ; import avec conteneur disparu (archivé) et nouvelle image ; rattachement d'un équipement saisi
  à la main ; modules reliés au bon composant ; support OVH trouvé par IP (`maintenance_hosting_ovh_discovery`) ; fichier
  invalide refusé.
- **Réel** : exécution sur arpol-brain (Debian, Docker) ; puis, **avec l'accord d'Armand au moment venu**,
  sur arpol.fr en lecture seule, import dans la copie neutralisée `arpol_test` (attendu : arbre d'arpol.fr,
  base `arpol.fr` et ses modules installés, avec leur dépôt).

## Livraison

Branche `18.0-maintenance-sw`, nouveaux modules en `18.0.1.0.0`. Rien n'est poussé ni installé en
production sans demande d'Armand.

## Hors périmètre (v1)

Lancement planifié, envoi automatique vers Odoo, découverte récursive des invités Proxmox, paquets système
détaillés, CVE, analyse de configuration nginx/DNS.
