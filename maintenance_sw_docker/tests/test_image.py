from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from odoo.tools import mute_logger

DIGEST = "sha256:f46e1a70b686d85611004e4da6456e71680ab0f22f4ba801de95b54fbd90757e"


class TestDockerImage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Image = cls.env["docker.image"]
        cls.Repository = cls.env["git.repository"]
        cls.odoo = cls.env["software.product"].create({"name": "Odoo test"})
        cls.odoo18 = cls.env["software.version"].create(
            {"product_id": cls.odoo.id, "name": "18.0"}
        )

    def test_display_name(self):
        image = self.Image.create({"repository": "mirror/odoo", "tag": "rc_18.0-ArPol", "digest": DIGEST})
        self.assertEqual(image.display_name, "mirror/odoo:rc_18.0-ArPol (f46e1a70b686)")
        self.assertEqual(self.Image.create({"repository": "postgres"}).display_name, "postgres")

    def test_digest_unique_per_repository(self):
        self.Image.create({"repository": "mirror/odoo", "digest": DIGEST})
        self.Image.create({"repository": "other/odoo", "digest": DIGEST})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self.Image.create({"repository": "mirror/odoo", "digest": DIGEST})

    def test_blank_digest_is_no_digest(self):
        first = self.Image.create({"repository": "mirror/odoo", "tag": "18.0", "digest": ""})
        second = self.Image.create({"repository": "mirror/odoo", "tag": "18.0", "digest": "  "})
        self.assertFalse(first.digest)
        self.assertFalse(second.digest)
        first.write({"digest": " "})
        self.assertFalse(first.digest)

    def test_digest_is_stripped(self):
        image = self.Image.create({"repository": "mirror/odoo", "digest": f" {DIGEST}\n"})
        self.assertEqual(image.digest, DIGEST)

    def test_duplicate_warning_without_digest(self):
        first = self.Image.create({"repository": "mirror/odoo", "tag": "18.0"})
        self.assertFalse(first.duplicate_warning)
        second = self.Image.create({"repository": "mirror/odoo", "tag": "18.0"})
        self.assertTrue(second.duplicate_warning)
        with_digest = self.Image.create({"repository": "mirror/odoo", "tag": "18.0", "digest": DIGEST})
        self.assertFalse(with_digest.duplicate_warning)

    def test_parent_cycle_rejected(self):
        base = self.Image.create({"repository": "tecnativa/doodba"})
        child = self.Image.create({"repository": "mirror/odoo", "parent_id": base.id})
        with self.assertRaises(ValidationError):
            base.parent_id = child

    def test_image_chain_most_distant_first(self):
        grand = self.Image.create({"repository": "python"})
        parent = self.Image.create({"repository": "tecnativa/doodba", "parent_id": grand.id})
        image = self.Image.create({"repository": "mirror/odoo", "parent_id": parent.id})
        self.assertEqual(image._image_chain().ids, [grand.id, parent.id, image.id])

    def test_chain_ids(self):
        grand = self.Image.create({"repository": "python"})
        parent = self.Image.create({"repository": "tecnativa/doodba", "parent_id": grand.id})
        image = self.Image.create({"repository": "mirror/odoo", "parent_id": parent.id})
        self.assertEqual(image.chain_ids.ids, [grand.id, parent.id, image.id])
        self.assertEqual(grand.chain_ids, grand)

    def test_product_follows_version_moved_to_other_product(self):
        version = self.env["software.version"].create({"product_id": self.odoo.id, "name": "19.0"})
        image = self.Image.create({"repository": "mirror/odoo", "version_id": version.id})
        nextcloud = self.env["software.product"].create({"name": "Nextcloud test"})
        version.product_id = nextcloud
        self.assertEqual(image.product_id, nextcloud)

    def test_version_sets_product(self):
        image = self.Image.create({"repository": "mirror/odoo", "version_id": self.odoo18.id})
        self.assertEqual(image.product_id, self.odoo)

    def test_version_of_other_product_rejected(self):
        debian = self.env["software.product"].create({"name": "Debian test"})
        image = self.Image.create({"repository": "mirror/odoo", "version_id": self.odoo18.id})
        with self.assertRaises(ValidationError):
            image.product_id = debian

    def test_repository_host_from_url(self):
        github = self.Repository.create({"name": "OCA/server-ux", "url": "https://github.com/OCA/server-ux.git"})
        mirror = self.Repository.create({"name": "mirror/server-ux", "url": "git.0k.io:/var/git/mirror/server-ux.git"})
        self.assertEqual(github.host, "github")
        self.assertEqual(mirror.host, "other")

    def test_repository_url_unique(self):
        url = "https://github.com/OCA/server-ux.git"
        self.Repository.create({"name": "a", "url": url})
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self.Repository.create({"name": "b", "url": url})

    def test_repository_upstream_cycle_rejected(self):
        upstream = self.Repository.create({"name": "OCA/server-ux", "url": "https://github.com/OCA/server-ux.git"})
        mirror = self.Repository.create(
            {"name": "mirror", "url": "git.0k.io:/var/git/mirror/server-ux.git", "upstream_id": upstream.id}
        )
        with self.assertRaises(ValidationError):
            upstream.upstream_id = mirror

    def test_container_count(self):
        image = self.Image.create({"repository": "mirror/odoo"})
        self.env["maintenance.equipment"].create(
            {"name": "myc_odoo-v18_1", "equipment_kind": "software", "docker_image_id": image.id}
        )
        self.env.invalidate_all()
        self.assertEqual(image.container_count, 1)
