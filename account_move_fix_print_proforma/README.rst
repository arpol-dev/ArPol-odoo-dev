Fix Invoice Print Proforma
==========================

Prevents posted invoices from being rendered as proforma PDFs when no
official stored PDF exists yet.

**Problem**

In Odoo 18, a posted (or paid) invoice is served as a *Pro Forma* PDF in
three situations where ``invoice_pdf_report_id`` is empty:

- **Flux 1** — backend *Download > PDF* menu (``/account/download_invoice_documents/…/pdf``)
- **Flux 2** — portal HTML preview (iframe), which sets ``proforma_invoice=True`` in context
- **Flux 3** — portal *Download* button (``/my/invoices/<id>?report_type=pdf&download=True``)

This is legally incorrect: a posted invoice is a binding accounting document
and must never be labelled *Pro Forma*.

**Fix**

- ``account.move``: overrides ``_get_invoice_legal_documents`` and
  ``_get_invoice_legal_documents_all`` to render a real PDF on-the-fly
  (same engine as the backend *Print* button) when the invoice is posted
  but has no stored PDF.
- ``ir.actions.report``: overrides ``_get_rendering_context`` to strip the
  ``proforma`` rendering flag for non-draft invoices when triggered via the
  ``proforma_invoice`` context key (portal HTML preview path).

The intentional EDI error-fallback proforma (``_prepare_invoice_proforma_pdf_report``)
is **not** affected.

Usage
-----

Install the module. No configuration required.

Authors
-------

- ArPol (Armand Polmard — contact@arpol.fr)

License
-------

AGPL-3 — see https://www.gnu.org/licenses/agpl.html
