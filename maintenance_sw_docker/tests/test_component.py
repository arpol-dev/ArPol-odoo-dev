from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestDockerComponent(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Component = cls.env["docker.component"]
        cls.repo = cls.env["git.repository"].create(
            {"name": "arpol-dev/ArPol-odoo-dev", "url": "https://github.com/arpol-dev/ArPol-odoo-dev.git"}
        )
        cls.image = cls.env["docker.image"].create({"repository": "mirror/odoo"})
        cls.container = cls.env["maintenance.equipment"].create({
            "name": "myc_odoo-v18_1",
            "equipment_kind": "software",
            "install_type": "docker_container",
            "docker_image_id": cls.image.id,
        })
        cls.mount = cls.env["docker.mount"].create({
            "equipment_id": cls.container.id,
            "source": "/srv/datastore/data/odoo-v18/repos-arpol",
            "destination": "/opt/odoo/auto/dev",
            "usage": "repos",
        })

    def test_mount_display_name(self):
        self.assertEqual(
            self.mount.display_name,
            "/srv/datastore/data/odoo-v18/repos-arpol → /opt/odoo/auto/dev",
        )

    def test_component_needs_an_owner(self):
        with self.assertRaises(ValidationError):
            self.Component.create({"repository_id": self.repo.id})

    def test_component_cannot_have_two_owners(self):
        with self.assertRaises(ValidationError):
            self.Component.create(
                {"repository_id": self.repo.id, "image_id": self.image.id, "mount_id": self.mount.id}
            )

    def test_image_component_cannot_override(self):
        target = self.Component.create({"repository_id": self.repo.id, "image_id": self.image.id})
        with self.assertRaises(ValidationError):
            self.Component.create(
                {"repository_id": self.repo.id, "image_id": self.image.id, "overrides_id": target.id}
            )

    def test_mount_component_overrides_only_image_components(self):
        other = self.Component.create({"repository_id": self.repo.id, "mount_id": self.mount.id})
        with self.assertRaises(ValidationError):
            self.Component.create(
                {"repository_id": self.repo.id, "mount_id": self.mount.id, "overrides_id": other.id}
            )

    def test_mount_component_overrides_image_component(self):
        target = self.Component.create({"repository_id": self.repo.id, "image_id": self.image.id})
        override = self.Component.create(
            {"repository_id": self.repo.id, "mount_id": self.mount.id, "overrides_id": target.id}
        )
        self.assertEqual(override.overrides_id, target)

    def test_effective_key(self):
        with_path = self.Component.create(
            {"repository_id": self.repo.id, "image_id": self.image.id, "path": " /opt/odoo/custom/src/x "}
        )
        without_path = self.Component.create({"repository_id": self.repo.id, "image_id": self.image.id})
        self.assertEqual(with_path._effective_key(), ("path", "/opt/odoo/custom/src/x"))
        self.assertEqual(without_path._effective_key(), ("repository", self.repo.id))

    def test_component_display_name(self):
        component = self.Component.create({
            "repository_id": self.repo.id,
            "image_id": self.image.id,
            "ref": "18.0",
            "commit": "4ba2ff313ae43eefd4aa0873bbcff8e37f107727",
        })
        self.assertEqual(component.display_name, "arpol-dev/ArPol-odoo-dev@18.0 (4ba2ff31)")

    def test_component_display_name_shows_path(self):
        component = self.Component.create({
            "repository_id": self.repo.id,
            "image_id": self.image.id,
            "ref": "18.0",
            "commit": "4ba2ff313ae43eefd4aa0873bbcff8e37f107727",
            "path": "/opt/odoo/custom/src/ArPol-odoo-dev",
        })
        self.assertEqual(
            component.display_name,
            "arpol-dev/ArPol-odoo-dev@18.0 (4ba2ff31) — /opt/odoo/custom/src/ArPol-odoo-dev",
        )

    # Search by typed text (Many2one dropdowns) ------------------------------

    def _name_search_ids(self, model, term):
        return [record_id for record_id, _name in self.env[model].name_search(term, limit=None)]

    def test_component_name_search(self):
        component = self.Component.create({
            "repository_id": self.repo.id,
            "image_id": self.image.id,
            "path": "/opt/odoo/custom/src/zz-arpol-path",
            "ref": "zz-ref-18.0",
            "commit": "zz4ba2ff313ae",
        })
        for term in ("ArPol-odoo-dev", "zz-arpol-path", "zz-ref-18", "zz4ba2ff"):
            self.assertIn(component.id, self._name_search_ids("docker.component", term), term)
        self.assertEqual(self._name_search_ids("docker.component", "zzz-no-such-repo"), [])

    def test_image_name_search(self):
        image = self.env["docker.image"].create(
            {"repository": "zz-mirror/odoo", "tag": "zz-rc_18.0", "digest": "sha256:zz0123456789"}
        )
        for term in ("zz-mirror/odoo", "zz-rc_18", "zz0123456789"):
            self.assertIn(image.id, self._name_search_ids("docker.image", term), term)
        self.assertEqual(self._name_search_ids("docker.image", "zzz-no-such-image"), [])

    def test_mount_name_search(self):
        self.assertIn(self.mount.id, self._name_search_ids("docker.mount", "repos-arpol"))
        self.assertIn(self.mount.id, self._name_search_ids("docker.mount", "/opt/odoo/auto/dev"))
        self.assertEqual(self._name_search_ids("docker.mount", "zzz-no-such-mount"), [])

    # Override target -------------------------------------------------------

    def test_mount_image_components_follow_container_image_chain(self):
        base = self.env["docker.image"].create({"repository": "tecnativa/doodba"})
        self.image.parent_id = base
        own = self.Component.create({"repository_id": self.repo.id, "image_id": self.image.id})
        inherited = self.Component.create({"repository_id": self.repo.id, "image_id": base.id})
        foreign_image = self.env["docker.image"].create({"repository": "other/odoo"})
        foreign = self.Component.create({"repository_id": self.repo.id, "image_id": foreign_image.id})
        self.env.invalidate_all()
        self.assertEqual(self.mount.image_component_ids, inherited | own)
        self.assertNotIn(foreign, self.mount.image_component_ids)

    def test_mount_image_components_without_image(self):
        container = self.env["maintenance.equipment"].create(
            {"name": "myc_postgres_1", "equipment_kind": "software", "install_type": "docker_container"}
        )
        mount = self.env["docker.mount"].create(
            {"equipment_id": container.id, "source": "/srv/pg", "destination": "/var/lib/postgresql"}
        )
        self.assertFalse(mount.image_component_ids)

    def test_override_target_outside_container_image_chain_rejected(self):
        other_image = self.env["docker.image"].create({"repository": "other/odoo"})
        target = self.Component.create({"repository_id": self.repo.id, "image_id": other_image.id})
        with self.assertRaises(ValidationError):
            self.Component.create(
                {"repository_id": self.repo.id, "mount_id": self.mount.id, "overrides_id": target.id}
            )
