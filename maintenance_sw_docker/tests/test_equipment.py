from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase

SRC = "/opt/odoo/custom/src"


class TestDockerEquipment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Image = cls.env["docker.image"]
        cls.Component = cls.env["docker.component"]
        cls.odoo = cls.env["software.product"].create({"name": "Odoo test"})
        cls.odoo17 = cls.env["software.version"].create({"product_id": cls.odoo.id, "name": "17.0"})
        cls.odoo18 = cls.env["software.version"].create({"product_id": cls.odoo.id, "name": "18.0"})
        Repository = cls.env["git.repository"]
        cls.ocb = Repository.create({"name": "OCA/OCB", "url": "https://github.com/OCA/OCB.git"})
        cls.ux = Repository.create({"name": "OCA/server-ux", "url": "https://github.com/OCA/server-ux.git"})
        cls.arpol = Repository.create(
            {"name": "arpol-dev/ArPol-odoo-dev", "url": "https://github.com/arpol-dev/ArPol-odoo-dev.git"}
        )
        cls.bemade = Repository.create(
            {"name": "arpol-dev/bemade-addons", "url": "https://github.com/arpol-dev/bemade-addons.git"}
        )

    def _container(self, **values):
        return self.env["maintenance.equipment"].create({
            "name": "myc_odoo-v18_1",
            "equipment_kind": "software",
            "install_type": "docker_container",
            **values,
        })

    def _component(self, owner, repository, path=None, commit=None, **values):
        key = "image_id" if owner._name == "docker.image" else "mount_id"
        return self.Component.create({
            key: owner.id, "repository_id": repository.id, "path": path, "commit": commit, **values,
        })

    def _mount(self, container):
        return self.env["docker.mount"].create({
            "equipment_id": container.id,
            "source": "/srv/datastore/data/odoo-v18/repos-arpol",
            "destination": "/opt/odoo/auto/dev",
            "usage": "repos",
        })

    def _effective(self, container):
        self.env.invalidate_all()
        return container.effective_component_ids

    # Version -----------------------------------------------------------

    def test_version_comes_from_image(self):
        image = self.Image.create({"repository": "mirror/odoo", "version_id": self.odoo18.id})
        container = self._container(docker_image_id=image.id)
        self.assertEqual(container.software_version_id, self.odoo18)
        self.assertEqual(container.software_product_id, self.odoo)

    def _real_container_values(self, image):
        """Values of the container upsert used on real data (stack parent, method, no
        product nor version)."""
        stack = self.env["maintenance.equipment"].create({
            "name": "Stack 0k myc-deploy", "equipment_kind": "software", "install_type": "compose_stack",
        })
        method = self.env.ref("maintenance_sw_base.deployment_method_myc")
        return {
            "deployment_method_id": method.id,
            "docker_image_id": image.id,
            "container_name": "myc_odoo-v18_1",
            "parent_id": stack.id,
            "runtime_changes": "symlink ovh_api added by hand",
        }

    def test_version_and_product_from_image_on_create_then_flush(self):
        """Nothing reads the container before the flush (as with an RPC create): the
        product must not be recomputed from an unset version."""
        image = self.Image.create({"repository": "mirror/odoo", "version_id": self.odoo18.id})
        container = self._container(**self._real_container_values(image))
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(container.software_version_id, self.odoo18)
        self.assertEqual(container.software_product_id, self.odoo)

    def test_version_and_product_from_image_on_write_then_flush(self):
        image = self.Image.create({"repository": "mirror/odoo", "version_id": self.odoo18.id})
        container = self._container()
        self.env.flush_all()
        container.write(self._real_container_values(image))
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(container.software_version_id, self.odoo18)
        self.assertEqual(container.software_product_id, self.odoo)

    def test_version_and_product_in_batch_then_flush(self):
        """Containers whose version comes from the image, created with others whose image has
        no version (manual version or none)."""
        image = self.Image.create({"repository": "mirror/odoo", "version_id": self.odoo18.id})
        postgres = self.Image.create({"repository": "postgres"})
        values = {"equipment_kind": "software", "install_type": "docker_container"}
        no_version, from_image, manual = self.env["maintenance.equipment"].create([
            {**values, "name": "myc_postgres_1", "docker_image_id": postgres.id},
            {**values, "name": "myc_odoo-v18_1", "docker_image_id": image.id},
            {**values, "name": "myc_odoo-v17_1", "docker_image_id": postgres.id,
             "software_version_id": self.odoo17.id},
        ])
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertFalse(no_version.software_version_id)
        self.assertFalse(no_version.software_product_id)
        self.assertEqual(from_image.software_version_id, self.odoo18)
        self.assertEqual(from_image.software_product_id, self.odoo)
        self.assertEqual(manual.software_version_id, self.odoo17)
        self.assertEqual(manual.software_product_id, self.odoo)

    def test_image_version_of_other_product_rejected(self):
        nextcloud = self.env["software.product"].create({"name": "Nextcloud test"})
        image = self.Image.create({"repository": "mirror/odoo", "version_id": self.odoo18.id})
        with self.assertRaises(ValidationError):
            self._container(docker_image_id=image.id, software_product_id=nextcloud.id)
            self.env.flush_all()

    def test_image_version_change_propagates(self):
        image = self.Image.create({"repository": "mirror/odoo", "version_id": self.odoo17.id})
        container = self._container(docker_image_id=image.id)
        image.version_id = self.odoo18
        self.assertEqual(container.software_version_id, self.odoo18)

    def test_product_follows_image_version_moved_to_other_product(self):
        version = self.env["software.version"].create({"product_id": self.odoo.id, "name": "19.0"})
        image = self.Image.create({"repository": "mirror/odoo", "version_id": version.id})
        container = self._container(docker_image_id=image.id)
        nextcloud = self.env["software.product"].create({"name": "Nextcloud test"})
        version.product_id = nextcloud
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertEqual(image.product_id, nextcloud)
        self.assertEqual(container.software_version_id, version)
        self.assertEqual(container.software_product_id, nextcloud)

    def test_image_without_version_keeps_manual_version(self):
        image = self.Image.create({"repository": "postgres"})
        container = self._container(software_version_id=self.odoo17.id)
        container.docker_image_id = image
        self.assertEqual(container.software_version_id, self.odoo17)

    def test_manual_version_without_image(self):
        container = self._container(software_version_id=self.odoo17.id)
        self.assertEqual(container.software_version_id, self.odoo17)

    # Effective components ------------------------------------------------

    def test_image_chain_child_replaces_parent_on_same_path(self):
        base = self.Image.create({"repository": "tecnativa/doodba"})
        image = self.Image.create({"repository": "mirror/odoo", "parent_id": base.id})
        old_ocb = self._component(base, self.ocb, f"{SRC}/odoo", "aaa")
        new_ocb = self._component(image, self.ocb, f"{SRC}/odoo", "bbb")
        ux = self._component(base, self.ux, f"{SRC}/server-ux")
        container = self._container(docker_image_id=image.id)
        effective = self._effective(container)
        self.assertIn(new_ocb, effective)
        self.assertIn(ux, effective, "a parent component nobody replaces is inherited")
        self.assertNotIn(old_ocb, effective)

    def test_mount_adds_and_overrides(self):
        image = self.Image.create({"repository": "mirror/odoo"})
        image_arpol = self._component(image, self.arpol, f"{SRC}/ArPol-odoo-dev", "old")
        ux = self._component(image, self.ux, f"{SRC}/server-ux")
        container = self._container(docker_image_id=image.id)
        mount = self._mount(container)
        mount_arpol = self._component(
            mount, self.arpol, "/opt/odoo/auto/dev/ArPol-odoo-dev", "new", overrides_id=image_arpol.id
        )
        bemade = self._component(mount, self.bemade, "/opt/odoo/auto/dev/bemade-addons")
        effective = self._effective(container)
        self.assertEqual(effective, ux | mount_arpol | bemade)

    def test_override_of_parent_component_already_replaced_by_child_image(self):
        base = self.Image.create({"repository": "tecnativa/doodba"})
        image = self.Image.create({"repository": "mirror/odoo", "parent_id": base.id})
        parent_arpol = self._component(base, self.arpol, f"{SRC}/ArPol-odoo-dev", "p")
        self._component(image, self.arpol, f"{SRC}/ArPol-odoo-dev", "c")
        container = self._container(docker_image_id=image.id)
        mount_arpol = self._component(
            self._mount(container), self.arpol, "/opt/odoo/auto/dev/ArPol-odoo-dev",
            overrides_id=parent_arpol.id,
        )
        effective = self._effective(container)
        self.assertEqual(effective, mount_arpol, "the override removes the entry by key, once")

    def test_components_without_path_resolved_by_repository(self):
        base = self.Image.create({"repository": "tecnativa/doodba"})
        image = self.Image.create({"repository": "mirror/odoo", "parent_id": base.id})
        old_ux = self._component(base, self.ux)
        ocb = self._component(base, self.ocb)
        new_ux = self._component(image, self.ux)
        container = self._container(docker_image_id=image.id)
        self.assertEqual(self._effective(container), ocb | new_ux)
        self.assertNotIn(old_ux, self._effective(container))

    def test_mounts_only_without_image(self):
        container = self._container()
        bemade = self._component(self._mount(container), self.bemade, "/opt/odoo/auto/dev/bemade-addons")
        self.assertEqual(self._effective(container), bemade)
