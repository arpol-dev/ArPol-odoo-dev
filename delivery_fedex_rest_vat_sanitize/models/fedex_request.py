import re

from odoo.addons.delivery_fedex_rest.models.fedex_request import FedexRequest


def _sanitize_vat_for_fedex(vat):
    """Remove formatting from VAT number for FedEx API compliance (max 18 chars).

    Example: 'CHE-347.247.288 TVA' -> 'CHE347247288'
    """
    if not vat:
        return vat
    sanitized = re.sub(r'[^A-Za-z0-9]', '', vat)
    sanitized = re.sub(r'(MWST|TVA|IVA)$', '', sanitized, flags=re.IGNORECASE)
    return sanitized


_original_get_tins = FedexRequest._get_tins_from_partner


def _get_tins_from_partner_sanitized(self, partner, custom_vat=False):
    tins = _original_get_tins(self, partner, custom_vat)
    for tin in tins:
        tin['number'] = _sanitize_vat_for_fedex(tin.get('number', ''))
    return tins


FedexRequest._get_tins_from_partner = _get_tins_from_partner_sanitized
