from odoo.addons.maintenance_sw_discovery.tests.common import DiscoveryCase


class TestOvhDiscovery(DiscoveryCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Host = cls.env["maintenance.host"]
        cls.account = cls.env["ovh.account"].create(
            {"name": "OVH test", "application_key": "k", "application_secret": "s"}
        )

    def _service(self, kind, name, **payload):
        service, _new = self.env["ovh.service"]._upsert(
            self.account, kind, name, dict({"detail": {"displayName": name}}, **payload)
        )
        return service

    def _vps(self):
        return self._service("vps", "vps-1.vps.ovh.net", ips=["152.228.135.45", "2001:db8:0::A"])

    def test_vps_found_by_ipv4_and_ipv6(self):
        host = self._vps().maintenance_host_ids
        self.assertTrue(host)
        self.assertEqual(self.Host._discovery_find_host(["10.0.0.1", "152.228.135.45"]), host)
        self.assertEqual(self.Host._discovery_find_host(["2001:db8::a"]), host)

    def test_dedicated_found_by_main_ip(self):
        service = self._service("dedicated", "ns1.ip-51-91-6.eu", detail={"ip": "51.91.6.7"})
        self.assertEqual(self.Host._discovery_find_host(["51.91.6.7"]), service.maintenance_host_ids)

    def test_unknown_ip_or_empty(self):
        self._vps()
        self.assertFalse(self.Host._discovery_find_host(["192.168.1.20"]))
        self.assertFalse(self.Host._discovery_find_host([]))
        self.assertFalse(self.Host._discovery_find_host(["not-an-ip"]))

    def test_other_kinds_ignored(self):
        self._service("hosting", "example.com", ips=["203.0.113.9"])
        self.assertFalse(self.Host._discovery_find_host(["203.0.113.9"]))

    def test_archived_service_ignored(self):
        service = self._vps()
        service.active = False
        self.assertFalse(self.Host._discovery_find_host(["152.228.135.45"]))

    def test_unprivileged_user(self):
        host = self._vps().maintenance_host_ids
        user = self.env["res.users"].create({
            "name": "Importer", "login": "importer_ovh",
            "groups_id": [(6, 0, [self.env.ref("maintenance.group_equipment_manager").id])],
        })
        self.assertEqual(
            self.Host.with_user(user)._discovery_find_host(["152.228.135.45"]), host.with_user(user)
        )

    def test_suggest_proposes_ovh_host(self):
        host = self._service("vps", "vps-2.vps.ovh.net", ips=["192.168.1.20"]).maintenance_host_ids
        self.assertEqual(self.Importer._suggest(self.reference())["host_id"], host.id)
