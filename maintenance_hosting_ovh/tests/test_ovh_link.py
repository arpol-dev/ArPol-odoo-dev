from ast import literal_eval
from unittest.mock import patch

from odoo.tests import TransactionCase, new_test_user
from odoo.tools import mute_logger

from odoo.addons.maintenance_hosting_ovh.hooks import post_init_hook

LOGGER = "odoo.addons.maintenance_hosting_ovh.models.ovh_service"


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

    def _sync(self, kind, name, account=None, **kwargs):
        service, _is_new = self.Service._upsert(
            account or self.account, kind, name, payload(name, **kwargs)
        )
        return service

    def _other_account(self):
        return self.env["ovh.account"].create(
            {"name": "OVH customer", "application_key": "k2", "application_secret": "s2"}
        )

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

    def test_domain_listed_by_two_accounts(self):
        first = self._sync("domain", "shared.fr")
        with self.assertLogs(LOGGER, "WARNING"):
            second = self._sync("domain", "shared.fr", account=self._other_account())
        self.assertTrue(second)
        domain = self.Domain.search([("name", "=", "shared.fr")])
        self.assertEqual(len(domain), 1)
        self.assertEqual(domain.ovh_service_id, first, "the domain stays with the first service")
        self.assertTrue(domain.active)

    def test_domain_moved_to_another_account(self):
        old = self._sync("domain", "moved.fr")
        old.write({"state": "terminated", "active": False})
        domain = self.Domain.search([("ovh_service_id", "=", old.id)])
        self.assertFalse(domain.active)
        new = self._sync("domain", "moved.fr", account=self._other_account())
        self.assertEqual(self.Domain.search([("name", "=", "moved.fr")]), domain)
        self.assertEqual(domain.ovh_service_id, new)
        self.assertTrue(domain.active)

    def test_archived_service_does_not_take_manual_domain(self):
        manual = self.Domain.create({"name": "manual-old.fr"})
        archived = self.Service.create({
            "account_id": self.account.id, "kind": "domain", "service_name": "manual-old.fr",
            "active": False,
        })
        post_init_hook(self.env)
        self.assertFalse(manual.ovh_service_id)
        self.assertTrue(manual.active)
        self.assertFalse(self.Domain.search([("ovh_service_id", "=", archived.id)]))

    def test_link_failure_does_not_stop_the_sync(self):
        service = self._sync("domain", "boom.fr", expiration="2027-06-09")
        with patch.object(
            type(self.Service), "_sync_maintenance_domain", side_effect=Exception("boom")
        ), mute_logger(LOGGER):
            again, is_new = self.Service._upsert(
                self.account, "domain", "boom.fr", payload("boom.fr", expiration="2028-06-09")
            )
        self.assertEqual(again, service)
        self.assertFalse(is_new)
        self.env.invalidate_all()
        self.assertEqual(str(service.expiration_date), "2028-06-09")

    def test_sql_failure_in_link_keeps_the_cursor_usable(self):
        def broken(service, ovhcloud):
            service.env.cr.execute("SELECT 1/0")

        with patch.object(type(self.Service), "_sync_maintenance_domain", broken), \
                mute_logger(LOGGER, "odoo.sql_db"):
            service = self._sync("domain", "sql.fr", expiration="2027-06-09")
        self.env.invalidate_all()
        self.assertEqual(str(service.expiration_date), "2027-06-09")
        self.assertFalse(self.Domain.search([("name", "=", "sql.fr")]))

    def test_archive_failure_does_not_stop_the_write(self):
        service = self._sync("vps", "vps-err.vps.ovh.net")
        with patch.object(
            type(self.Service), "_sync_maintenance_active", side_effect=Exception("boom")
        ), mute_logger(LOGGER):
            service.write({"state": "terminated", "active": False})
        self.env.invalidate_all()
        self.assertFalse(service.active)

    def test_deleted_service_releases_the_domain(self):
        service = self._sync("domain", "deleted.fr")
        domain = self.Domain.search([("ovh_service_id", "=", service.id)])
        self.assertTrue(domain.is_ovh_managed)
        service.sudo().unlink()
        self.assertFalse(domain.is_ovh_managed)

    def _kinds_offered_by(self, field):
        domain = literal_eval(field.domain)
        services = self.Service.create([
            {"account_id": self.account.id, "kind": kind, "service_name": f"{kind}-filter-test"}
            for kind, _label in self.Service._fields["kind"].selection
        ])
        return set(self.Service.search(domain).filtered(lambda s: s in services).mapped("kind"))

    def test_host_field_offers_machine_services_only(self):
        field = self.env["maintenance.host"]._fields["ovh_service_id"]
        self.assertEqual(self._kinds_offered_by(field), {"dedicated", "vps", "hosting"})

    def test_domain_field_offers_domain_services_only(self):
        field = self.env["maintenance.domain"]._fields["ovh_service_id"]
        self.assertEqual(self._kinds_offered_by(field), {"domain"})
