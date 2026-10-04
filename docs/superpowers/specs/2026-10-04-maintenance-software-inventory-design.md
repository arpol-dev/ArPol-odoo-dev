# Design — Inventaire logiciel dans la Maintenance (`maintenance_sw_base`, `maintenance_sw_docker`)

**Date :** 2026-10-04  
**Auteur :** Armand Polmard  
**Version Odoo :** 18.0  
**Dépôt :** `ArPol-odoo-dev` (branche `18.0`)

---

## Contexte

L'application Maintenance d'Odoo suit des équipements matériels (`maintenance.equipment`). Elle ne
sait pas décrire ce qui est installé sur un serveur : système, plateforme de déploiement,
conteneurs, images Docker, dépôts de code et leurs versions.

Objectif final : **depuis Odoo, étudier l'installation complète d'un serveur pour anticiper les
mises à jour**. Ce document couvre le premier lot, les modèles de données, avec une saisie
**manuelle**. La collecte automatique et la planification des mises à jour viendront ensuite
(voir « Feuille de route »).

### Principes

- **Un seul nœud d'inventaire** : un logiciel est un `maintenance.equipment`, comme un matériel. Pas
  de modèle parallèle de « service installé ».
- **La hiérarchie dit où, la méthode de déploiement dit comment** : un logiciel est l'enfant de ce
  qui l'héberge (matériel ou autre logiciel) ; un champ distinct dit quel outil l'a installé et le
  met à jour.
- **Le parent est facultatif** : un logiciel en SaaS (Odoo Online, Odoo.sh…) n'a pas de serveur à
  renseigner.
- **Le contenu réel d'un conteneur = images + montages** : les dépôts peuvent venir de l'image, de
  ses images parentes, ou d'un volume monté qui ajoute ou remplace des dépôts.

### Existant réutilisé / écarté

- **Réutilisé** : `maintenance` (natif) et `maintenance_equipment_hierarchy` (OCA, 18.0.1.0.0) qui
  apporte `parent_id`, `child_ids`, `child_count`, `parent_path` (`_parent_store`) et
  `complete_name` sur `maintenance.equipment`.
- **Écarté** : `maintenance_server_data` (Elabore). Ses modèles `service` / `service.version` /
  `service.instance` sont plats et feraient doublon avec « un logiciel est un équipement enfant ».
  On s'en inspire, sans en dépendre.

---

## Module 1 — `maintenance_sw_base`

**Dépendances :** `maintenance`, `maintenance_equipment_hierarchy`.

### Catalogue

#### `software.product` — un logiciel, indépendamment de toute installation

| Champ | Type | Remarque |
|---|---|---|
| `name` | Char, requis | Debian, Odoo, PostgreSQL, Nextcloud, Cloudron… |
| `vendor` | Char | Éditeur |
| `website` | Char | |
| `changelog_url` | Char | |
| `version_ids` | One2many `software.version` | |
| `note` | Html | |
| `active` | Boolean | |

Contrainte : `name` unique.

#### `software.version` — une version d'un logiciel

| Champ | Type | Remarque |
|---|---|---|
| `product_id` | Many2one `software.product`, requis | |
| `name` | Char, requis | `12`, `18.0`, `12.15`, `saas~18.3` |
| `release_date` | Date | |
| `end_of_support_date` | Date | Fin de support / EOL |
| `channel` | Selection | `stable`, `lts`, `saas`, `other` |
| `is_latest` | Boolean | Dernière version connue du produit |
| `sequence` | Integer | Ordre entre versions (le tri par chaîne est faux : `9` > `12`) |
| `note` | Html | |

- `display_name` = « Produit Version » (ex. « Debian 12 »).
- Contrainte : (`product_id`, `name`) unique.
- `is_latest` : au plus une version par produit ; cocher une version décoche les autres du même
  produit (dans `write`/`create`, pas de contrainte bloquante).

#### `software.deployment.method` — l'outil ou la plateforme qui installe et met à jour

| Champ | Type | Remarque |
|---|---|---|
| `name` | Char, requis | 0k / myc (`compose`), Cloudron, apt manuel, Docker manuel, Odoo.sh, Odoo Online |
| `managed_by_provider` | Boolean | Le fournisseur exploite et met à jour (SaaS) |
| `update_procedure` | Html | Comment mettre à jour, pièges connus |
| `documentation_url` | Char | Ex. lien vers la note ArPol-Mind |
| `active` | Boolean | |

Données livrées (`noupdate="1"`) : « 0k / myc », « Cloudron », « Odoo Online », « Odoo.sh »,
« Manuel ». Les deux SaaS ont `managed_by_provider = True`.

### Extension de `maintenance.equipment`

| Champ | Type | Remarque |
|---|---|---|
| `equipment_kind` | Selection, requis | `hardware` (défaut), `software` |
| `install_type` | Selection | `os`, `package`, `docker_container`, `compose_stack`, `git_checkout`, `saas`, `manual` — visible si `software` |
| `deployment_method_id` | Many2one `software.deployment.method` | |
| `software_product_id` | Many2one `software.product` | Pour filtrer/grouper même sans version précise |
| `software_version_id` | Many2one `software.version` | Domaine : versions de `software_product_id` |
| `version_note` | Char | Repli quand la version n'est pas au catalogue |
| `install_path` | Char | Ex. `/opt/apps/myc-deploy` |
| `needs_attachment` | Boolean calculé, stocké | Voir ci-dessous |

Règles :

- Changer `software_version_id` renseigne `software_product_id` (onchange + cohérence vérifiée par
  contrainte : la version doit appartenir au produit).
- **`needs_attachment`** (« à rattacher ») = logiciel **sans parent** dont la méthode de
  déploiement **n'est pas** `managed_by_provider` (y compris méthode vide). Ce n'est **pas** une
  contrainte : un filtre « À rattacher » sert au contrôle de saisie.
- Aucune contrainte sur le type du parent : un logiciel peut être l'enfant d'un matériel ou d'un
  autre logiciel (Debian → stack 0k → conteneur ; VPS → Cloudron → application).

### Vues

- Formulaire équipement : un onglet **Logiciel** (visible si `equipment_kind = software`) avec
  type d'installation, méthode, produit, version, chemin. La hiérarchie (onglet OCA) reste en
  place.
- Liste et recherche : filtres *Matériel*, *Logiciel*, *À rattacher*, *Géré par le fournisseur* ;
  regroupements par produit, version, méthode, type d'installation.
- Formulaire `software.product` avec la liste de ses versions ; bouton intelligent « Installations »
  (équipements utilisant le produit).
- Formulaire `software.version` avec bouton « Installations ».
- Menus sous **Maintenance > Configuration > Logiciels** : Produits, Versions, Méthodes de
  déploiement.

---

## Module 2 — `maintenance_sw_docker`

**Dépendances :** `maintenance_sw_base`.

### `git.repository` — un dépôt de code, enregistré une seule fois

| Champ | Type | Remarque |
|---|---|---|
| `name` | Char, requis | Ex. `OCA/server-ux` |
| `url` | Char, requis | URL réellement utilisée |
| `host` | Selection | `github`, `gitlab`, `other` |
| `upstream_id` | Many2one `git.repository` | Origine officielle d'un fork ou d'un miroir (ex. miroir `git.0k.io` → GitHub) |
| `note` | Html | |

Contrainte : `url` unique.

### `docker.image` — une image à un instant donné

| Champ | Type | Remarque |
|---|---|---|
| `registry` | Char | Ex. `docker.io` |
| `repository` | Char, requis | Ex. `tecnativa/odoo` |
| `tag` | Char | `18.0`, `latest` |
| `digest` | Char | `sha256:…` |
| `build_date` | Datetime | |
| `parent_id` | Many2one `docker.image` | Image de base (`FROM`) |
| `product_id` / `version_id` | Many2one catalogue | Ex. Odoo / 18.0 |
| `component_ids` | One2many `docker.component` | Composants propres à l'image |
| `container_ids` | One2many `maintenance.equipment` | Conteneurs qui l'utilisent |
| `note` | Html | |

- **Une ligne par digest, pas par tag** : un tag bouge, une mise à jour d'image crée un nouvel
  enregistrement ; l'ancien reste pour l'historique.
- Unicité : contrainte SQL (`repository`, `digest`). Les images sans digest sont tolérées ; un
  avertissement (non bloquant) signale un doublon (`repository`, `tag`) sans digest.
- `display_name` = `repository:tag` (+ 12 premiers caractères du digest s'il existe).
- Contrainte : pas de cycle sur `parent_id`.

### `docker.mount` — un montage d'un conteneur

| Champ | Type | Remarque |
|---|---|---|
| `equipment_id` | Many2one `maintenance.equipment`, requis | Le conteneur |
| `mount_type` | Selection | `bind`, `volume` |
| `source` | Char, requis | Chemin hôte ou nom du volume |
| `destination` | Char, requis | Chemin dans le conteneur |
| `mode` | Selection | `rw`, `ro` |
| `usage` | Selection | `repos`, `data`, `config`, `logs`, `other` |
| `component_ids` | One2many `docker.component` | Dépôts apportés par ce montage |

### `docker.component` — un dépôt présent dans une image ou un montage

| Champ | Type | Remarque |
|---|---|---|
| `image_id` | Many2one `docker.image` | |
| `mount_id` | Many2one `docker.mount` | |
| `repository_id` | Many2one `git.repository`, requis | |
| `path` | Char | Chemin dans le conteneur (ex. `/opt/odoo/custom/src/server-ux`) |
| `ref` | Char | Branche ou tag (`18.0`) |
| `commit` | Char | SHA exact |
| `role` | Selection | `core`, `enterprise`, `oca`, `custom`, `third_party` |
| `merges` | Text | PR / branches fusionnées par-dessus |
| `overrides_id` | Many2one `docker.component` | Composant d'image remplacé (montage uniquement) |

Contraintes :

- Exactement un de `image_id` / `mount_id`.
- `overrides_id` seulement sur un composant de montage, et il doit pointer vers un composant
  d'image.

### Extension de `maintenance.equipment`

| Champ | Type | Remarque |
|---|---|---|
| `docker_image_id` | Many2one `docker.image` | |
| `container_name` | Char | Ex. `myc_odoo-v18_1` |
| `mount_ids` | One2many `docker.mount` | |
| `effective_component_ids` | Many2many `docker.component`, calculé, non stocké | Voir ci-dessous |
| `runtime_changes` | Text | Modifications hors image et hors montage déclaré |

Visibles si `install_type` ∈ {`docker_container`, `compose_stack`}.

**Version effective** : si `docker_image_id` a un `version_id`, `software_version_id` (et le
produit) en sont calculés (`compute`, `store=True`, `readonly=False`) ; sinon la saisie manuelle
reste. Changer d'image recalcule ; la saisie manuelle reste possible quand l'image n'a pas de
version.

**Composants effectifs** (« quelle version de chaque dépôt tourne vraiment ici ») :

1. composants de la chaîne d'images, du parent le plus lointain à l'image du conteneur ; un
   composant d'une image fille remplace celui d'un parent pour le même `path` ;
2. puis composants des montages : un composant avec `overrides_id` retire le composant remplacé,
   les autres s'ajoutent.

**`runtime_changes`** : texte libre pour noter les écarts invisibles autrement — par exemple un
lien symbolique ajouté à la main dans la couche du conteneur (cas d'`ovh_api` sur arpol.fr), perdu
si le conteneur est recréé.

### Vues

- Formulaire équipement : onglet **Docker** (image, conteneur, montages avec leurs composants,
  tableau des composants effectifs en lecture seule, modifications hors image).
- Formulaires / listes `docker.image` (composants, chaîne d'images, conteneurs utilisateurs),
  `git.repository`.
- Menus sous **Maintenance > Configuration > Logiciels** : Images Docker, Dépôts git.

---

## Sécurité

- Groupes natifs de `maintenance` : *Utilisateur* (lecture sur les catalogues, écriture sur les
  équipements comme aujourd'hui), *Gestionnaire* (`maintenance.group_equipment_manager`, écriture
  sur tous les nouveaux modèles).
- Règles multi-société : aucune sur les catalogues (partagés) ; les montages suivent l'équipement.

## Traductions

Code et libellés en anglais ; traduction française dans `i18n/fr.po` de chaque module.

## Tests

`TransactionCase` par module :

- `maintenance_sw_base` : `needs_attachment` (avec/sans parent, méthode SaaS ou non, méthode vide) ;
  cohérence produit/version ; unicité de `is_latest` par produit ; unicité des catalogues.
- `maintenance_sw_docker` : version calculée depuis l'image et repli manuel ; contrainte image XOR
  montage ; `overrides_id` valide ; absence de cycle d'images ; composants effectifs (héritage
  d'image par `path`, ajout et remplacement par montage) ; unicité (`repository`, `digest`).

Validation fonctionnelle : copie neutralisée de la base arpol.fr, saisie du serveur arpol.fr
(VPS → Debian → stack 0k → `myc_odoo-v18_1` avec image, dépôts lus dans `repos.yaml`, montage
`repos-arpol`), pilotage et vérifications en JSON-RPC, contrôle visuel avec Playwright.

## Déploiement

Modules dans `ArPol-odoo-dev`, branche `18.0`. Push sur le dépôt distant avant tout déploiement ;
installation sur arpol.fr seulement après validation sur la copie neutralisée.
`maintenance_equipment_hierarchy` est déjà disponible sur arpol.fr (dépôt OCA `maintenance`).

---

## Hors périmètre (v1)

Collecte automatique, import de `repos.yaml`, couches Docker, vulnérabilités (CVE), liste des
paquets installés, licences, ports/URL de services, supervision, comparaison de deux images.

## Feuille de route

1. `maintenance_sw_base` + `maintenance_sw_docker` — ce document.
2. `maintenance_sw_odoo` — série, bases de données, puis modules installés.
3. `maintenance_hosting_ovh` — pont avec `ovh_api` : services OVH → équipements matériels, client
   (`partner_id`), échéance.
4. `maintenance_sw_discovery` — collecte (`os-release`, `docker inspect`, `repos.yaml`) poussée en
   JSON-RPC.
5. `maintenance_sw_lifecycle` — installé vs dernière version / fin de support (éventuellement via
   endoflife.date), vue par serveur et par client, demandes de maintenance préventives ; les
   logiciels `managed_by_provider` rangés en « mises à jour subies ».
