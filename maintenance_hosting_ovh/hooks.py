def post_init_hook(env):
    """Link the OVH services synchronized before the module was installed."""
    env["ovh.service"].with_context(active_test=False).search([])._sync_maintenance_link()
