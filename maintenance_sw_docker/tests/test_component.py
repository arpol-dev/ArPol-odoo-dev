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
        cls.container = cls.env["maintenance.equipment"].create(
            {"name": "myc_odoo-v18_1", "equipment_kind": "software", "install_type": "docker_container"}
        )
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
