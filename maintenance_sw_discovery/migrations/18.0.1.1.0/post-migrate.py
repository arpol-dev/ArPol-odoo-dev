"""Rekey the discovery records of arpol.fr from its machine-id to its SMBIOS product UUID.

Until now the identity of a server was its machine-id, which two servers built from the same disk
image share: the VPS of MAS Réemploi carries arpol.fr's machine-id. The importer now uses the
product UUID (see discovery_tools.machine_ids); the records already imported for arpol.fr are
rekeyed here so that the next discovery of that server updates them instead of duplicating them.
The UUID and machine-id below were read on the server on 2026-10-17.
"""
from odoo import SUPERUSER_ID, api

LEGACY_MID = "3fcf01d7867d484c8d6954e4a1ac6426"
NEW_MID = "68505a59-2edf-4727-a1ff-8061bba82ebf"
ROOT_KEY = f"machine:{LEGACY_MID}"


def _rekey(key):
    """machine:<mid>, container:<mid>:<name>, stack:<mid>:<path>... with the new identity."""
    prefix, mid, rest = (key.split(":", 2) + [""])[:3]
    if mid != LEGACY_MID:
        return None
    return ":".join([prefix, NEW_MID] + ([rest] if rest else []))


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Equipment = env["maintenance.equipment"].with_context(active_test=False)
    root = Equipment.search([("discovery_key", "=", ROOT_KEY)])
    if not root:
        return  # nothing imported for this server (or already rekeyed)
    if root.discovery_hostname != "arpol.fr":
        raise ValueError(f"machine-id {LEGACY_MID} is not arpol.fr's: {root.discovery_hostname}")
    if Equipment.search_count([("discovery_key", "like", f"%:{NEW_MID}%")]):
        raise ValueError("records already carry the new identity: rekeying would collide")
    models = (Equipment, env["maintenance.host"].with_context(active_test=False))
    for model in models:
        for record in model.search([("discovery_key", "like", f"%:{LEGACY_MID}%")]):
            new_key = _rekey(record.discovery_key)
            if new_key:
                record.discovery_key = new_key
