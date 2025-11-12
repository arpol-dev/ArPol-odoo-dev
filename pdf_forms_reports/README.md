# PDF Forms Reports

Module Odoo v18 pour générer des rapports PDF à partir de formulaires PDF templates.

## Fonctionnalités

- Upload d'un formulaire PDF comme template de rapport
- Détection automatique des champs du formulaire PDF
- Mappage flexible des champs :
  - Valeurs directes
  - Références aux champs Odoo
  - Expressions Python
  - Insertion d'images/fichiers
- Support des champs automatiques et manuels
- Génération de PDFs consolidés pour plusieurs enregistrements
- Support des signatures

## Installation

### Prérequis Python

Ce module nécessite **PyMuPDF** (bibliothèque de manipulation de PDF).

**IMPORTANT** : N'installez PAS le package `fitz` ! Installez `PyMuPDF` qui fournit le module `fitz`.

```bash
# Dans votre environnement Python/container Odoo
pip install PyMuPDF
```

**Vérification** :
```bash
python3 -c "import fitz; print(f'PyMuPDF version: {fitz.version}')"
# Devrait afficher : PyMuPDF version: ('1.26.x', ...)
```

### Installation du Module

1. Copiez le module dans votre répertoire addons
2. Mettez à jour la liste des applications (Apps → Update Apps List)
3. Recherchez "PDF Forms Reports"
4. Cliquez sur "Install"

## Utilisation

### 1. Créer un Rapport

Allez dans **Settings → Technical → Actions → Reports → Create**

- **Name** : Nom du rapport
- **Type** : Sélectionnez "PDF Form"
- **Model** : Choisissez le modèle Odoo (ex: `res.partner`, `sale.order`)
- **PDF Form Template** : Uploadez votre formulaire PDF

### 2. Configurer les Mappings

Dans l'onglet "Form Fields Mapping", configurez chaque champ :

**Champs Automatiques** (détectés du PDF) :
- **Description** : Description du champ pour documentation
- **Field Type** : Text ou Checkbox (détecté automatiquement)
- **Evaluation Type** :
  - `Value` : Valeur fixe
  - `Reference` : Champ Odoo (ex: `partner_id.name`)
  - `Equation` : Expression Python (ex: `object.amount_total * 1.2`)
  - `File` : Image ou fichier

**Champs Manuels** (pour PDFs sans champs éditables) :
- Activez "Manual Entry"
- Définissez la **Position** : `x1,y1,x2,y2` (coordonnées dans le PDF)
- Définissez la **Page** : Numéro de page (commence à 1)

### 3. Utiliser le Rapport

Le rapport apparaît maintenant dans le menu "Print" de vos enregistrements.

## Exemples de Configuration

### Exemple 1 : Valeur Fixe
```
Field Name: company_name
Evaluation Type: Value
Value: Mon Entreprise SARL
```

### Exemple 2 : Référence à un Champ
```
Field Name: customer_name
Evaluation Type: Reference
Field Reference: name (depuis le modèle res.partner)
```

### Exemple 3 : Expression Python
```
Field Name: total_with_tax
Evaluation Type: Equation
Value: object.amount_total * 1.20
```

Variables disponibles dans les expressions :
- `object` ou `record` : L'enregistrement actuel
- `env` : L'environnement Odoo
- `data` : Données additionnelles du rapport

### Exemple 4 : Insertion d'Image
```
Field Name: company_logo
Evaluation Type: File
Upload File: [Votre logo]
Position: 50,50,150,100  (si champ manuel)
```

## Architecture Technique

### Structure du Module
```
pdf_forms_reports/
├── controllers/
│   ├── __init__.py
│   └── report.py                # Contrôleur HTTP personnalisé
├── models/
│   ├── ir_actions_report.py    # Extension du système de rapports (Backend)
│   └── form_field_match.py     # Modèle de mapping des champs
├── views/
│   └── ir_actions_report_views.xml
├── static/
│   └── src/
│       └── js/
│           └── pdf_form_handler.js  # Handler JavaScript (Frontend)
└── security/
    └── ir.model.access.csv
```

### Points d'Entrée

Le module utilise le système de rapports standard d'Odoo avec un nouveau type `pdf_form`.

**Architecture simplifiée (Frontend + HTTP + Backend)** :

1. **Frontend JavaScript** (`static/src/js/pdf_form_handler.js`) :
   - Enregistre un handler personnalisé pour `report_type == 'pdf_form'`
   - Intercepte le clic sur le bouton "Print"
   - Construit l'URL `/report/pdf_form/report_name/record_ids`
   - Télécharge directement depuis cette URL (pas de passage par `/report/download`)

2. **Contrôleur HTTP** (`controllers/report.py`) :
   - Route `/report/pdf_form/<reportname>/<docids>` : Reçoit la requête directement
   - Appelle `ir.actions.report._render()` qui dispatche vers `_render_pdf_form()`
   - Génère le nom de fichier approprié
   - Retourne le PDF avec les headers corrects (Content-Type, Content-Disposition)

3. **Backend Python** (`models/ir_actions_report.py`) :
   - `_render()` détecte `report_type == 'pdf_form'`
   - Lookup dynamique trouve `_render_pdf_form()`
   - Génère le PDF rempli via `_generate_pdf_form_for_record()`
   - Fusionne si multi-records via `_merge_pdfs()`
   - Retourne le contenu PDF

**Compatibilité v16/v18** :
- Le système `_render()` avec dispatch dynamique existe dans v16 et v18
- Le registry `ir.actions.report handlers` est identique dans les deux versions
- Aucune modification nécessaire pour passer de v16 à v18

**Pourquoi cette architecture ?**
- Simplicité : téléchargement direct sans passer par le système standard `/report/download`
- Fiabilité : pas de conflits avec les contrôleurs standards d'Odoo
- Maintenabilité : architecture claire et facile à déboguer
- Pas de modification du core Odoo, tout est dans notre module

## Dépannage

### Erreur : "The ActionManager can't handle reports of type pdf_form"

**Cause** : Le fichier JavaScript `pdf_form_handler.js` n'est pas chargé ou enregistré correctement.

**Solution** :
1. Vérifiez que le module est mis à jour : Settings → Apps → pdf_forms_reports → Upgrade
2. **Videz le cache du navigateur** et rechargez la page (Ctrl+F5)
3. Vérifiez dans les assets backend que le fichier est présent :
   - Activer le mode développeur
   - Settings → Technical → User Interface → Assets Bundles
   - Chercher `web.assets_backend`
   - Vérifier la présence de `pdf_forms_reports/static/src/js/pdf_form_handler.js`

### Erreur : "ModuleNotFoundError: No module named 'frontend'"

**Cause** : Le mauvais package `fitz` est installé au lieu de `PyMuPDF`.

**Solution** :
```bash
pip uninstall -y fitz
pip install PyMuPDF
```

### Erreur : "Invalid PDF template"

**Cause** : Le fichier uploadé n'est pas un PDF valide ou est corrompu.

**Solution** : Vérifiez que le fichier est bien un PDF et qu'il s'ouvre dans un lecteur PDF.

### Les champs ne sont pas remplis

**Causes possibles** :
1. Le nom du champ dans le mapping ne correspond pas au nom dans le PDF
2. Le champ PDF n'est pas éditable (vérifiez dans Adobe Acrobat)
3. L'expression Python contient une erreur

**Solution** : Vérifiez les logs Odoo (niveau DEBUG) pour voir les détails.

## Limitations

- Les PDFs générés ne peuvent pas être modifiés interactivement (champs "applatis")
- Les checkboxes complexes (avec plusieurs états) ne sont pas supportées
- Les champs calculés du PDF ne sont pas évalués

## Développement Futur

Fonctionnalités prévues :
- Support des attachments (sauvegarde/réutilisation des PDFs générés)
- Interface graphique pour positionner les champs manuels
- Support des champs date avec formatage
- Support des tableaux dynamiques
- Aperçu du PDF avant génération

## Auteur

- **Armand Polmard** (contact@arpol.fr)
- License: AGPL-3.0

## Support

Pour signaler un bug ou demander une fonctionnalité, contactez l'auteur.
