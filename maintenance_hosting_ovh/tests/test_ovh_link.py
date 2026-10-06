from odoo.tests import TransactionCase, new_test_user

from odoo.addons.maintenance_hosting_ovh.hooks import post_init_hook


def payload(name, expiration="2027-06-09", automatic=True, admin="pa1413842-ovh"):
    return {
        "detail": {"displayName": name},
        "serviceInfos": {
            "status": "ok",
            "expiration": expiration,
            "renew": {"automatic": automatic},
            "contactAdmin": admin,
        },
    }


class TestOvhLink(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Service = cls.env["ovh.service"]
        cls.Host = cls.env["maintenance.host"].with_context(active_test=False)
        cls.Domain = cls.env["maintenance.domain"].with_context(active_test=False)
        cls.account = cls.env["ovh.account"].create(
            {"name": "OVH test", "application_key": "k", "application_secret": "s"}
        )
        cls.ovhcloud = cls.env.ref("maintenance_hosting_ovh.partner_ovhcloud")

    def _sync(self, kind, name, **kwargs):
        service, _is_new = self.Service._upsert(self.account, kind, name, payload(name, **kwargs))
        return service

    def test_vps_creates_host_once(self):
        service = self._sync("vps", "vps-d4d16c17.vps.ovh.net")
        self._sync("vps", "vps-d4d16c17.vps.ovh.net")
        host = self.Host.search([("ovh_service_id", "=", service.id)])
        self.assertEqual(len(host), 1)
        self.assertEqual(host.host_type, "vps")
        self.assertEqual(host.provider_id, self.ovhcloud)
        self.assertEqual(host.name, "vps-d4d16c17.vps.ovh.net")
        self.assertEqual(service.maintenance_host_ids, host)

    def test_dedicated_and_hosting_types(self):
        dedicated = self._sync("dedicated", "ns3148992.ip-51-91-6.eu")
        hosting = self._sync("hosting", "example.com")
        self.assertEqual(self.Host.search([("ovh_service_id", "=", dedicated.id)]).host_type, "physical")
        self.assertEqual(self.Host.search([("ovh_service_id", "=", hosting.id)]).host_type, "shared_hosting")

    def test_domain_created_with_expiration(self):
        service = self._sync("domain", "Example.FR", expiration="2027-06-09", automatic=True)
        domain = self.Domain.search([("ovh_service_id", "=", service.id)])
        self.assertEqual(domain.name, "example.fr")
        self.assertEqual(str(domain.expiration_date), "2027-06-09")
        self.assertTrue(domain.auto_renew)
        self.assertEqual(domain.registrar_id, self.ovhcloud)
        self.assertTrue(domain.is_ovh_managed)

    def test_domain_values_refreshed_on_resync(self):
        service = self._sync("domain", "example.fr", expiration="2027-06-09", automatic=True)
        self._sync("domain", "example.fr", expiration="2028-06-09", automatic=False)
        domain = self.Domain.search([("ovh_service_id", "=", service.id)])
        self.assertEqual(str(domain.expiration_date), "2028-06-09")
        self.assertFalse(domain.auto_renew)

    def test_manual_domain_is_linked_not_duplicated(self):
        alwaysdata = self.env["res.partner"].create({"name": "Registrar X", "is_company": True})
        manual = self.Domain.create({"name": " Example.fr. ", "registrar_id": alwaysdata.id})
        service = self._sync("domain", "example.fr")
        self.assertEqual(self.Domain.search([("name", "=", "example.fr")]), manual)
        self.assertEqual(manual.ovh_service_id, service)
        self.assertEqual(manual.registrar_id, alwaysdata, "an existing registrar is kept")

    def test_owner_guessed_from_nic_handle(self):
        company = self.env["res.partner"].create({"name": "Client SA", "is_company": True})
        self.env["res.partner"].create(
            {"name": "Boss", "parent_id": company.id, "ovh_nic_handle": "ab12345-ovh"}
        )
        service = self._sync("domain", "client.fr", admin="AB12345-ovh")
        self.assertEqual(self.Domain.search([("ovh_service_id", "=", service.id)]).partner_id, company)

    def test_owner_not_overwritten(self):
        owner = self.env["res.partner"].create({"name": "Owner", "is_company": True})
        self.env["res.partner"].create({"name": "Other", "ovh_nic_handle": "cd67890-ovh"})
        manual = self.Domain.create({"name": "kept.fr", "partner_id": owner.id})
        self._sync("domain", "kept.fr", admin="cd67890-ovh")
        self.assertEqual(manual.partner_id, owner)

    def test_other_kinds_create_nothing(self):
        hosts, domains = self.Host.search_count([]), self.Domain.search_count([])
        self._sync("email_mxplan", "mxplan-test-1")
        self._sync("telephony_account", "pa1413842-ovh-1")
        self.assertEqual(self.Host.search_count([]), hosts)
        self.assertEqual(self.Domain.search_count([]), domains)

    def test_archive_and_restore_follow_service(self):
        vps = self._sync("vps", "vps-1.vps.ovh.net")
        dom = self._sync("domain", "gone.fr")
        (vps | dom).write({"state": "terminated", "active": False})
        host = self.Host.search([("ovh_service_id", "=", vps.id)])
        domain = self.Domain.search([("ovh_service_id", "=", dom.id)])
        self.assertFalse(host.active)
        self.assertFalse(domain.active)
        self._sync("vps", "vps-1.vps.ovh.net")
        self._sync("domain", "gone.fr")
        self.assertTrue(host.active)
        self.assertTrue(domain.active)

    def test_post_init_hook_links_existing_services(self):
        service = self.Service.create({
            "account_id": self.account.id, "kind": "vps", "service_name": "vps-old.vps.ovh.net",
        })
        archived = self.Service.create({
            "account_id": self.account.id, "kind": "domain", "service_name": "old.fr", "active": False,
        })
        post_init_hook(self.env)
        self.assertTrue(self.Host.search([("ovh_service_id", "=", service.id)]))
        domain = self.Domain.search([("ovh_service_id", "=", archived.id)])
        self.assertTrue(domain)
        self.assertFalse(domain.active)

    def test_sync_by_ovh_operator_without_maintenance_rights(self):
        operator = new_test_user(
            self.env, login="ovh-operator", groups="base.group_user,ovh_api.group_ovh_operator"
        )
        self.assertFalse(operator.has_group("maintenance.group_equipment_manager"))
        Service = self.Service.with_user(operator)
        service, _is_new = Service._upsert(
            self.account.with_user(operator), "domain", "operator.fr", payload("operator.fr")
        )
        self.assertTrue(self.Domain.search([("ovh_service_id", "=", service.id)]))
