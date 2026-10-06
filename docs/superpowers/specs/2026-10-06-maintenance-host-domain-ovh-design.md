# Design — Support physique, client, noms de domaine et pont OVH

**Date :** 2026-10-06  
**Auteur :** Armand Polmard  
**Version Odoo :** 18.0  
**Dépôt :** `ArPol-odoo-dev` (branche `18.0-maintenance-sw`)  
**Complète :** `2026-10-04-maintenance-software-inventory-design.md` (modules `maintenance_sw_base`,
`maintenance_sw_docker`, déjà implémentés sur la branche, jamais installés en production)

---

## Contexte

Le premier lot décrit un serveur comme un arbre d'équipements reliés par `parent_id`, dont la
racine était un équipement matériel. Or un VPS loué chez OVH n'est pas un équipement que l'on
maintient : le premier niveau d'intervention est l'installation de l'OS. Il faut pourtant savoir,
pour tout logiciel et quel que soit son niveau dans l'arbre, **sur quel support physique** il tourne
et **pour quel client**, sur le principe de `commercial_partner_id` (l'entreprise d'un contact,
quel que soit son niveau de dépendance).

Le support physique peut être un équipement que l'on maintient, un service OVH (VPS, dédié,
hébergement) ou un simple libellé (hébergement Alwaysdata, machine d'un tiers). Les noms de domaine
d'un client doivent être connus, qu'ils soient chez OVH ou ailleurs (Alwaysdata…).

### Décisions prises

- `parent_id` garde le seul sens « installé dans / sur ». La racine d'un serveur loué est son OS.
- Le support physique est un **modèle dédié** `maintenance.host` (un vrai many2one, groupable et
  filtrable), plutôt que plusieurs champs ou un champ `Reference`.
- Support physique et client suivent le même mécanisme : une valeur **saisie** (facultative) et une
  valeur **effective** calculée (la saisie, sinon celle du parent). Une valeur forcée sur un enfant
  survit à un changement du parent.
- Les noms de domaine sont un **modèle générique** `maintenance.domain`, lié en many2many aux
  équipements logiciels qui les servent ; pas de gestion DNS.
- Tout ce qui touche OVH vit dans un module pont, `maintenance_hosting_ovh` : `maintenance_sw_base`
  ne dépend jamais d'`ovh_api`.
- Les sous-domaines (vhosts) ne sont pas suivis en v1 : seul le domaine enregistré est modélisé.

---

## Module `maintenance_sw_base` — évolutions

### Nouveau modèle `maintenance.host` (Support physique)

| Champ | Type | Remarque |
|---|---|---|
| `name` | Char, requis | Ex. « vps-6a9adef4 (OVH) », « Tardis (Barbesson) » |
| `host_type` | Selection, requis | `physical` (serveur physique), `vps`, `vm` (machine virtuelle), `shared_hosting` (hébergement mutualisé), `other` ; défaut `other` |
| `provider_id` | Many2one `res.partner` | Hébergeur (OVHcloud, Alwaysdata…) ; vide pour une machine à soi |
| `equipment_id` | Many2one `maintenance.equipment` | Équipement matériel maintenu soi-même (ex. Tardis), domaine `equipment_kind = hardware` |
| `location` | Char | |
| `note` | Html | |
| `active` | Boolean | défaut `True` |
| `software_ids` | One2many `maintenance.equipment` (`physical_host_id`) | Logiciels dont c'est le support effectif |
| `software_count` | Integer calculé | + bouton intelligent « Logiciels » |

`_rec_names_search = ["name", "provider_id.name"]`.

### Nouveau modèle `maintenance.domain` (Nom de domaine)

| Champ | Type | Remarque |
|---|---|---|
| `name` | Char, requis | Normalisé (`strip().lower()`, sans point final) en `create`/`write` ; unique (contrainte SQL) |
| `registrar_id` | Many2one `res.partner` | |
| `expiration_date` | Date | |
| `auto_renew` | Boolean | |
| `partner_id` | Many2one `res.partner` | Client propriétaire, facultatif |
| `equipment_ids` | Many2many `maintenance.equipment` | Logiciels qui servent ce domaine ; domaine `equipment_kind = software` ; table de relation `maintenance_domain_equipment_rel` |
| `note` | Html | |
| `active` | Boolean | défaut `True` |

### Extension de `maintenance.equipment`

| Champ | Type | Remarque |
|---|---|---|
| `host_id` | Many2one `maintenance.host` | Support physique **saisi** ; `ondelete="restrict"` |
| `physical_host_id` | Many2one `maintenance.host`, calculé, stocké, `recursive=True` | `host_id`, sinon `parent_id.physical_host_id` ; indexé |
| `customer_id` | Many2one `res.partner` | Client **saisi** |
| `effective_customer_id` | Many2one `res.partner`, calculé, stocké, `recursive=True` | `customer_id`, sinon `parent_id.effective_customer_id` ; indexé |
| `domain_ids` | Many2many `maintenance.domain` | Réciproque de `equipment_ids` (même table de relation) |

- Les champs effectifs sont en lecture seule ; le formulaire montre la valeur effective et permet de
  la forcer via le champ saisi.
- Support physique et domaines : visibles pour les logiciels (`equipment_kind = software`). Client :
  visible pour tous les équipements.
- **`needs_attachment`** (« À rattacher ») devient : logiciel **sans `physical_host_id`** dont la
  méthode de déploiement n'est pas `managed_by_provider` (méthode vide comprise). Le parent n'entre
  plus dans la règle. Dépendances : `equipment_kind`, `physical_host_id`,
  `deployment_method_id.managed_by_provider`.

### Domaines d'un client

Sur `res.partner` : `maintenance_domain_ids` calculé (non stocké) = domaines dont le partenaire est
propriétaire (`partner_id`) ∪ domaines servis par un équipement dont `effective_customer_id` est ce
partenaire ; bouton intelligent « Noms de domaine » sur la fiche contact (visible pour
`maintenance.group_equipment_manager`), qui ouvre la liste filtrée sur ces domaines. Comparaison
sur le partenaire commercial (`commercial_partner_id`) des deux côtés, pour qu'un contact d'une
entreprise retrouve les domaines de l'entreprise.

### Vues et menus

- Formulaire équipement : `customer_id` / `effective_customer_id` dans l'en-tête ; dans l'onglet
  Logiciel, `host_id` / `physical_host_id` et `domain_ids` (tags).
- Liste et recherche équipement : colonnes optionnelles support physique et client effectifs ;
  regroupements par support physique et par client.
- `maintenance.host` et `maintenance.domain` : liste, formulaire, recherche (filtre Archivés,
  regroupements par hébergeur / registrar / client).
- Menus sous **Maintenance > Configuration > Software** : Physical Hosts, Domain Names.
- Traduction française complétée (`i18n/fr.po`, termes : Support physique, Hébergeur, Nom de
  domaine, Registrar, Client, Client effectif…).

### Sécurité

Même schéma que le reste de la suite : lecture `base.group_user`, tout pour
`maintenance.group_equipment_manager` sur `maintenance.host` et `maintenance.domain`. Pas de règle
multi-société (catalogues partagés, comme les produits logiciels).

---

## Module `maintenance_sw_docker` — évolution

Aucune modification de modèle. L'onglet Docker affiche en lecture seule `physical_host_id` et
`effective_customer_id` pour le contexte.

---

## Nouveau module `maintenance_hosting_ovh`

**Dépendances :** `maintenance_sw_base`, `ovh_api`.

### Champs

- `maintenance.host.ovh_service_id` : Many2one `ovh.service` (`ondelete="set null"`), unique ;
  `ovh_expiration_date` = related `ovh_service_id.expiration_date`.
- `maintenance.domain.ovh_service_id` : Many2one `ovh.service` (`ondelete="set null"`), unique.
- `ovh.service` : `host_ids` / `domain_ids` (One2many réciproques) et boutons intelligents vers le
  support ou le domaine lié.

### Synchronisation

Surcharge de `ovh.service._upsert(account, kind, service_name, payload)` : après l'appel parent,
`service._sync_maintenance_link()` crée ou met à jour l'objet lié (retrouvé par `ovh_service_id`,
archivés compris) :

| `kind` OVH | Objet | Valeurs |
|---|---|---|
| `dedicated` | `maintenance.host`, `host_type = physical` | `name` = nom OVH à la création ; `provider_id` = OVHcloud |
| `vps` | `maintenance.host`, `host_type = vps` | idem |
| `hosting` | `maintenance.host`, `host_type = shared_hosting` | idem |
| `domain` | `maintenance.domain` | `name` = nom du service ; `registrar_id` = OVHcloud ; `expiration_date` et `auto_renew` (= `renew_automatic`) réécrits à chaque synchronisation |
| autres (`email_mxplan`, `email_domain`, `telephony_*`, `cloud_project`) | rien | |

- Le nom n'est fixé qu'à la création (renommable ensuite). Si un domaine du même nom existe déjà
  sans lien OVH (saisi à la main), il est rattaché plutôt que dupliqué.
- **Client deviné** : si `partner_id` du domaine est vide et que le contact administratif OVH
  (`contact_admin`) correspond à `ovh_nic_handle` d'un contact Odoo (champ d'`ovh_api`, comparé en
  minuscules), ce contact (son partenaire commercial) devient le propriétaire.
- **Service disparu chez OVH** : `ovh_api` l'archive (`active = False`, `state = terminated`) dans
  `_mark_terminated`, par `write`. Le pont surcharge `ovh.service.write` : quand `active` passe à
  `False`, il archive l'objet lié ; quand il repasse à `True`, il le désarchive. Rien n'est
  supprimé ; les logiciels restent rattachés à un support archivé.
- Partenaire **OVHcloud** livré par le module (`data`, `noupdate="1"`, `is_company = True`).
- **À l'installation** (`post_init_hook`) : `_sync_maintenance_link()` sur tous les `ovh.service`
  existants (archivés compris).
- Dans le formulaire d'un domaine lié à OVH, `expiration_date` et `auto_renew` sont en lecture
  seule.

### Sécurité et traduction

Pas de nouveau modèle. Traduction française dans `i18n/fr.po`.

---

## Tests

- `maintenance_sw_base` :
  - héritage support/client : racine, enfant, petit-enfant ; valeur forcée sur un enfant qui
    survit au changement du parent ; changement du parent qui se propage aux descendants ;
  - `needs_attachment` : sans support, avec support saisi, avec support hérité, méthode SaaS ;
  - `maintenance.domain` : normalisation et unicité du nom ;
  - domaines d'un client : propriétaire direct, via équipement (client effectif hérité), via un
    contact de l'entreprise ;
  - les tests existants fondés sur le parent sont adaptés à la nouvelle règle.
- `maintenance_hosting_ovh` (appels directs à `_upsert` avec des payloads factices, aucun réseau) :
  VPS / dédié / hébergement / domaine créent le bon objet, une seule fois sur deux
  synchronisations ; échéance et renouvellement du domaine repris ; domaine saisi à la main
  rattaché ; client deviné par `ovh_nic_handle` (et non écrasé s'il est déjà renseigné) ;
  archivage et désarchivage suivis ; `post_init_hook` sur des services existants.
- L'outil de test local monte aussi `~/ovh_api-18.0.1.5.0`.

## Validation sur la copie neutralisée d'arpol.fr

- Installation de `maintenance_hosting_ovh` : les 31 services OVH donnent leurs supports
  (12 : 10 VPS, 1 dédié, 1 hébergement) et leurs 16 domaines.
- Le « VPS arpol.fr » saisi comme équipement est supprimé ; « Debian (arpol.fr) » devient la racine,
  son support est le `maintenance.host` du VPS OVH dont une IP (payload `ips`) correspond à
  l'adresse de `arpol.fr` ; client ArPol sur la stack ; domaine `arpol.fr` lié au conteneur
  `myc_odoo-v18_1`.
- Vérification JSON-RPC (supports/clients effectifs du conteneur, domaines du client ArPol) et
  contrôle visuel Playwright.

## Livraison

Même branche `18.0-maintenance-sw`, version `18.0.1.0.0` conservée (aucune installation en
production à migrer). Le pont n'est déployable en production qu'une fois `ovh_api` versionné et
chargé durablement (aujourd'hui non chargé en production : lien symbolique perdu le 2026-10-06).

## Hors périmètre (v1)

DNS et sous-domaines, MX Plan / téléphonie / Public Cloud comme équipements, détection automatique
du support d'un logiciel, facturation.
