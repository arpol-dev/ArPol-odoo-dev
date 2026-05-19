# Design — Module `mail_partner_history`

**Date :** 2026-05-13  
**Auteur :** Armand Polmard  
**Version Odoo :** 18.0

---

## Contexte

Dans Odoo, les échanges avec un partenaire (emails, messages chatter) sont éparpillés sur chaque document (commande, devis, lead CRM, etc.). Il n'existe aucun moyen natif d'avoir une vue consolidée et chronologique de tous les échanges avec un partenaire donné, comme on l'a dans une application de messagerie ou de SMS.

Ce module ajoute un onglet **"Historique partenaire"** dans le chatter des modèles configurés, affichant l'ensemble des messages impliquant le partenaire lié, triés anti-chronologiquement, avec pour chaque message un lien vers le document source.

---

## Fonctionnalités

### Onglet "Historique partenaire" dans le chatter

- Le chatter des modèles activés affiche deux onglets :
  - **Discussion** — le chatter habituel, inchangé
  - **Historique partenaire** — vue consolidée des échanges du partenaire
- L'onglet n'est visible que si :
  - `partner_history_enabled = True` sur le modèle courant (`ir.model`)
  - Le partenaire est déterminable : l'enregistrement est un `res.partner`, ou son champ `partner_id` est renseigné

### Contenu de l'onglet historique

- **Messages inclus** : tous les `mail.message` où :
  - `author_id` correspond au partenaire (messages qu'il a postés ou envoyés), **OU**
  - le partenaire figure dans `partner_ids` (messages pour lesquels il a été notifié)
- **Tous types** inclus : email, commentaire chatter, note interne — aucune exclusion
- **Tri** : anti-chronologique (du plus récent au plus ancien)
- **Pagination** : chargement par lots (load more), même comportement que le chatter natif

### Carte de message

Rendu visuellement identique au chatter natif (mêmes classes CSS, bulles, avatars, dates groupées). Chaque message affiche en plus un **badge discret en haut à droite** :

```
↗ Commande client SO/001
```

Le badge est un lien cliquable qui ouvre le document source (`res_model` + `res_id` du `mail.message`). Si le document n'existe plus ou n'est plus accessible, le badge affiche le nom du modèle seul sans lien.

### Configuration par modèle

- Champ Boolean `partner_history_enabled` ajouté sur `ir.model`
- Visible dans **Paramètres > Technique > Structure base de données > Modèles** (vue form `ir.model`)
- Par défaut : `False` sur tous les modèles
- À activer manuellement par l'admin sur les modèles souhaités (ex. `res.partner`, `crm.lead`, `sale.order`)

---

## Architecture technique

### Fichiers Python

#### `models/ir_model.py`
```python
class IrModel(models.Model):
    _inherit = 'ir.model'
    partner_history_enabled = fields.Boolean(
        string="Afficher l'historique partenaire",
        default=False,
    )

    @api.model
    def get_partner_history_enabled_models(self):
        """Retourne la liste des model (ex: 'res.partner') pour lesquels
        l'historique partenaire est activé. Appelé une fois par session JS."""
        records = self.search([('partner_history_enabled', '=', True)])
        return records.mapped('model')
```

#### `models/mail_message.py`
Nouvelle méthode `_get_partner_history_messages(partner_id, limit=30, offset=0)` :
- Domain : `['|', ('author_id', '=', partner_id), ('partner_ids', 'in', [partner_id])]`
- Tri : `[('date', 'desc')]`
- Retourne les champs nécessaires au rendu : `id`, `author_id`, `date`, `body`, `message_type`, `subtype_id`, `res_model`, `res_id`, `record_name`, `partner_ids`
- Exposé via un contrôleur JSON-RPC

### Contrôleur

#### `controllers/main.py`
Route : `POST /mail/partner_history/messages`  
Paramètres : `partner_id`, `limit`, `offset`  
Réponse : liste de messages sérialisés (JSON)  
Droits : vérifie que l'utilisateur peut lire les messages retournés (filtre via ORM)

### Vues XML

#### `views/ir_model_views.xml`
Héritage de la vue form `ir.model` pour ajouter la case à cocher dans l'onglet "Informations" ou dans un groupe dédié.

### JavaScript / OWL

#### `static/src/partner_history_service.js`
Service OWL `partnerHistoryService` (enregistré dans `web.assets_backend`) :
- Au démarrage de session, appelle `call_kw('ir.model', 'get_partner_history_enabled_models', [], {})` (nouvelle méthode Python retournant la liste des `model` activés, ex. `['res.partner', 'sale.order']`)
- Résultat mis en cache dans le service pour toute la session
- Expose `isEnabledForModel(modelName): bool`

#### `static/src/chatter_patch.js` + `chatter_patch.xml`
Patch du composant `@mail/chatter/chatter` :
- Ajout d'un état réactif `activeTab` (`"discussion"` | `"history"`)
- Au `setup()` : appel à `partnerHistoryService.isEnabledForModel(this.props.resModel)` pour savoir si l'onglet doit être affiché
- Méthode `_resolvePartnerId()` : si `resModel === 'res.partner'` → `resId`, sinon lecture du champ `partner_id` via `orm.read(resModel, [resId], ['partner_id'])`. **Hypothèse** : le champ s'appelle `partner_id` sur tous les modèles activés — c'est la convention Odoo standard, mais à documenter dans le README du module.
- Méthode `_switchTab(tab)` : met à jour `activeTab`
- Template patché : injection des boutons onglet au-dessus du fil de messages, affichage conditionnel de `<PartnerHistoryList>` ou du `<MessageList>` natif

#### `static/src/partner_history_list.js` + `partner_history_list.xml`
Nouveau composant OWL `PartnerHistoryList` :
- Props : `partnerId`, `partnerName`
- Au montage : appel `POST /mail/partner_history/messages`
- Rendu : liste de divs stylées avec les classes CSS du chatter natif (`.o-mail-Message`, `.o-mail-Message-header`, etc.)
- Badge document : `<a t-att-href="'/web#model=' + msg.res_model + '&amp;id=' + msg.res_id">↗ <t t-esc="msg.record_name"/></a>` affiché en haut à droite de chaque message si `res_model` et `res_id` sont renseignés
- Groupement par date (aujourd'hui, hier, cette semaine, date explicite) — même logique que le chatter natif
- Bouton "Charger plus" si `messages.length === limit`

### Assets

Déclaration dans `__manifest__.py` :
```python
'assets': {
    'web.assets_backend': [
        'mail_partner_history/static/src/partner_history_service.js',
        'mail_partner_history/static/src/chatter_patch.xml',
        'mail_partner_history/static/src/chatter_patch.js',
        'mail_partner_history/static/src/partner_history_list.xml',
        'mail_partner_history/static/src/partner_history_list.js',
    ],
},
```

---

## Gestion des droits d'accès

### Principe

L'historique partenaire ne doit jamais exposer un message attaché à un document que l'utilisateur ne peut pas lire. Le filtrage doit être **silencieux** : aucune erreur n'est levée, les messages inaccessibles sont simplement omis.

### Implémentation dans `_get_partner_history_messages`

Après la requête ORM initiale (qui applique déjà les ACL de `mail.message`), un second filtre par document source est appliqué :

1. Les messages **sans** `res_model`/`res_id` sont inclus directement (messages non attachés à un document)
2. Les messages **avec** `res_model`/`res_id` sont regroupés par modèle
3. Pour chaque modèle, on tente un `search([('id', 'in', res_ids)])` sur ce modèle :
   - Si le modèle n'existe pas dans le registre (`KeyError`) → les messages de ce modèle sont exclus silencieusement
   - Si l'utilisateur n'a pas accès en lecture au modèle (`AccessError`) → les messages de ce modèle sont exclus silencieusement
   - Sinon → seuls les `res_id` retournés par le `search` (ceux auxquels l'utilisateur a accès, après application des `ir.rule`) sont conservés

```python
# Pseudo-code de la logique de filtrage
accessible_messages = []
no_doc_messages = [m for m in messages if not m.res_model]
accessible_messages.extend(no_doc_messages)

by_model = defaultdict(list)
for msg in messages:
    if msg.res_model and msg.res_id:
        by_model[msg.res_model].append(msg)

for model_name, model_msgs in by_model.items():
    try:
        Model = self.env[model_name]
        res_ids = list({m.res_id for m in model_msgs})
        accessible_ids = set(Model.search([('id', 'in', res_ids)]).ids)
        accessible_messages.extend(
            m for m in model_msgs if m.res_id in accessible_ids
        )
    except (KeyError, AccessError):
        pass  # modèle inconnu ou aucun droit → exclure silencieusement
```

### Impact sur la pagination

Ce post-filtrage peut produire **moins de résultats que `limit`** par page (certains messages étant filtrés après récupération). Ce comportement est accepté en v1 : le bouton "Charger plus" reste fonctionnel mais peut parfois retourner moins que 30 messages. Une stratégie de re-fetch pour atteindre exactement `limit` est hors périmètre de cette version.

### Badge document et accès

Si l'utilisateur n'a pas accès au document source d'un message **qui lui est quand même accessible** (cas théorique rare), le badge affiche le nom du modèle sans lien cliquable — même comportement que pour un document supprimé.

---

## Cas limites

| Situation | Comportement |
|---|---|
| `partner_id` non renseigné sur l'enregistrement | Onglet masqué |
| Aucun message trouvé pour ce partenaire | Onglet visible mais message "Aucun échange avec ce partenaire" |
| Document source supprimé | Badge affiche le nom du modèle sans lien cliquable |
| Partenaire archivé | Fonctionne normalement, l'historique reste accessible |
| Modèle sans champ `partner_id` mais activé par erreur | Onglet masqué (aucun `partner_id` à résoudre) |

---

## Vérification / Tests end-to-end

1. Installer le module sur une base Odoo 18 avec des données de test
2. Activer `partner_history_enabled` sur `res.partner` et `sale.order` via Paramètres > Technique > Modèles
3. Ouvrir une fiche contact ayant des commandes avec des échanges mail → vérifier que l'onglet "Historique" apparaît et liste tous les messages
4. Cliquer sur le badge d'un message → vérifier la navigation vers le bon document
5. Ouvrir une commande liée à ce contact → vérifier que l'onglet apparaît également
6. Ouvrir une commande sans `partner_id` renseigné → vérifier que l'onglet est masqué
7. Ouvrir un modèle non activé → vérifier absence de l'onglet
8. Tester la pagination : partenaire avec > 30 messages → "Charger plus" doit charger le lot suivant

---

## Hors périmètre (non inclus dans cette version)

- Filtres dans l'onglet historique (par type, par date, par document)
- Export des échanges
- Accès portail client à l'historique
- Recherche full-text dans l'historique
