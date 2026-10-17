"""Scenario tests of static/discover.sh.

Each scenario under tests/script/<name>/ simulates a server:
- root/ is the target file system (the script reads every file through DISCOVER_ROOT);
- bin/ holds stub commands (`case "$*"` + frozen output).

The script runs with a PATH made only of a temporary directory holding copies of the scenario
stubs (made executable there, so the tests do not depend on the exec bit of the checkout, which
is mounted read-only in the test container) and links to a short allowlist of basic utilities.
No real system command (docker, ip, pct, sudo...) can therefore be reached from a scenario, and
a command absent from the scenario is absent for the script. HOME and TMPDIR are temporary
directories too, so the module directory is never written.

root/ is copied to a temporary directory where every `dot.git` is renamed `.git` (git cannot
store a path named .git). Stubs find their frozen answers (docker/*.json...) through
$SCENARIO_DIR.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

from odoo.tests import BaseCase

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(MODULE_DIR, "static", "discover.sh")
SCENARIOS_DIR = os.path.join(MODULE_DIR, "tests", "script")
SCENARIOS = [
    "debian", "proxmox", "cloudron", "alpine", "weird", "zerok", "zerok_odoo", "manual_odoo",
    "docker_denied", "leaky",
]
SECTIONS = ["machine", "os", "platforms", "proxmox", "zerok", "cloudron", "docker", "odoo"]
# Basic utilities a minimal server always has (coreutils / busybox, sed, grep, awk, iconv).
BASE_UTILS = [
    "bash", "sh", "env", "cat", "head", "tail", "sed", "grep", "awk", "iconv", "timeout",
    "mktemp", "rm", "date", "tr", "cut", "sort", "uniq", "wc", "basename", "dirname",
    "readlink", "id",
]


def copy_root(source, target):
    """Copy a scenario root, renaming every `dot.git` into `.git`."""
    if os.path.isdir(source):
        shutil.copytree(source, target, symlinks=True)
    else:
        os.mkdir(target)
    for dirpath, dirnames, filenames in os.walk(target):
        for entry in dirnames + filenames:
            if entry == "dot.git":
                os.rename(os.path.join(dirpath, entry), os.path.join(dirpath, ".git"))


def run_raw(name, extra_env=None, args=(), extra_bin=None, stdin_script=False, prepare=None):
    """Run the script on scenario `name`; return (CompletedProcess, tmpdir listing).

    With `stdin_script`, the script is fed on stdin to `bash -s` (as `ssh host 'bash -s' <
    discover.sh` does) instead of being run from its file. `prepare(root)` may change the
    copied root before the run (permissions are restored afterwards for the cleanup).
    """
    scenario = os.path.join(SCENARIOS_DIR, name)
    with tempfile.TemporaryDirectory(prefix="discover-test-") as tmp:
        root = os.path.join(tmp, "root")
        copy_root(os.path.join(scenario, "root"), root)
        if prepare:
            prepare(root)
        path_dir = os.path.join(tmp, "bin")
        home = os.path.join(tmp, "home")
        tmpdir = os.path.join(tmp, "tmp")
        cwd = os.path.join(tmp, "cwd")
        for directory in (path_dir, home, tmpdir, cwd):
            os.mkdir(directory)
        stubs = os.path.join(scenario, "bin")
        for stub in sorted(os.listdir(stubs)) if os.path.isdir(stubs) else []:
            target = os.path.join(path_dir, stub)
            shutil.copyfile(os.path.join(stubs, stub), target)
            os.chmod(target, 0o755)
        for stub, content in (extra_bin or {}).items():
            target = os.path.join(path_dir, stub)
            with open(target, "w") as handle:
                handle.write(content)
            os.chmod(target, 0o755)
        for util in BASE_UTILS:
            target = os.path.join(path_dir, util)
            real = shutil.which(util, path="/usr/bin:/bin")
            if real and not os.path.exists(target):
                os.symlink(real, target)
        env = {
            "PATH": path_dir,
            "HOME": home,
            "TMPDIR": tmpdir,
            "LANG": "C.UTF-8",
            "DISCOVER_ROOT": root,
            "SCENARIO_DIR": scenario,
        }
        env.update(extra_env or {})
        if stdin_script:
            with open(SCRIPT, "rb") as script:
                proc = subprocess.run(
                    ["bash", "-s", "--", *args], env=env, stdin=script, capture_output=True,
                    timeout=60, executable=shutil.which("bash"), cwd=cwd,
                )
        else:
            proc = subprocess.run(
                ["bash", SCRIPT, *args], env=env, capture_output=True, timeout=60,
                executable=shutil.which("bash"), cwd=cwd,
            )
        # Read-only: nothing may be left in the temp dir, HOME or the working directory.
        leftovers = (
            (os.listdir(tmpdir) if os.path.isdir(tmpdir) else []) + os.listdir(home)
            + os.listdir(cwd)
        )
        if prepare:
            for dirpath, _dirnames, _filenames in os.walk(root):
                os.chmod(dirpath, 0o755)
            os.chmod(root, 0o755)
    return proc, leftovers


def run_scenario(name, extra_env=None, extra_bin=None, stdin_script=False, prepare=None):
    """Run the script on scenario `name` and return the parsed JSON output."""
    proc, _leftovers = run_raw(
        name, extra_env=extra_env, extra_bin=extra_bin, stdin_script=stdin_script,
        prepare=prepare,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"discover.sh exited with {proc.returncode} on {name}: {proc.stderr.decode()}"
        )
    return json.loads(proc.stdout.decode("utf-8"))


class TestDiscoverScript(BaseCase):
    def sections(self, name, **kwargs):
        return run_scenario(name, **kwargs)["sections"]

    def data(self, sections, name):
        section = sections[name]
        self.assertEqual(section["status"], "ok", f"section {name}: {section}")
        return section["data"]

    # ------------------------------------------------------------------ common
    def test_all_scenarios_envelope(self):
        for name in SCENARIOS:
            with self.subTest(scenario=name):
                proc, leftovers = run_raw(name)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                result = json.loads(proc.stdout.decode("utf-8"))
                self.assertEqual(result["schema_version"], 1)
                self.assertEqual(result["script_version"], "1.0.0")
                self.assertRegex(result["collected_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
                self.assertEqual(list(result["sections"]), SECTIONS)
                for section_name, section in result["sections"].items():
                    self.assertIn(section["status"], ("ok", "skipped", "error"))
                    if section["status"] == "ok":
                        self.assertIn("data", section)
                    elif section["status"] == "skipped":
                        self.assertIsInstance(section["reason"], str)
                    else:
                        self.assertIsInstance(section["message"], str)
                for section_name in ("machine", "os", "platforms"):
                    self.assertEqual(result["sections"][section_name]["status"], "ok")
                # Read-only: nothing left behind (its own mktemp dir is removed).
                self.assertEqual(leftovers, [])

    def test_help(self):
        proc, _leftovers = run_raw("debian", args=["--help"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Usage", proc.stdout.decode())
        self.assertIn("--sudo", proc.stdout.decode())

    def test_unknown_option(self):
        proc, _leftovers = run_raw("debian", args=["--bogus"])
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, b"")

    def test_invalid_json_fallback(self):
        """With a jq that rejects the output, the script says so instead of printing it."""
        fake_jq = "#!/usr/bin/env bash\ncat >/dev/null\nexit 1\n"
        result = run_scenario("debian", extra_bin={"jq": fake_jq})
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["sections"], {})
        self.assertEqual(result["fatal"], "invalid JSON produced")
        self.assertIn('"machine"', result["raw"])

    # ------------------------------------------------------------------ debian
    def test_debian(self):
        sections = self.sections("debian")
        os_data = self.data(sections, "os")
        self.assertEqual(os_data["id"], "debian")
        self.assertEqual(os_data["version_id"], "12")
        self.assertEqual(os_data["version_codename"], "bookworm")
        self.assertEqual(os_data["pretty_name"], "Debian GNU/Linux 12 (bookworm)")
        self.assertEqual(os_data["kernel"], "6.1.0-25-amd64")
        self.assertEqual(os_data["package_manager"], "dpkg")
        machine = self.data(sections, "machine")
        self.assertEqual(machine["hostname"], "srv-debian")
        self.assertEqual(machine["machine_id"], "0f3a9b1c2d4e5f60718293a4b5c6d7e8")
        self.assertIsNone(machine["product_uuid"])  # no /sys in the scenario
        self.assertEqual(machine["virtualization"], "vm")
        self.assertEqual(machine["ips"], [
            {"address": "192.168.1.20", "family": "inet", "interface": "eth0"},
            {"address": "2001:db8::20", "family": "inet6", "interface": "eth0"},
        ])
        self.assertEqual(
            self.data(sections, "platforms"),
            {"proxmox": None, "zerok": None, "cloudron": None, "docker": None},
        )
        for name in ("proxmox", "zerok", "cloudron", "docker", "odoo"):
            self.assertEqual(sections[name]["status"], "skipped", name)

    # ------------------------------------------------------------------ proxmox
    def test_proxmox(self):
        sections = self.sections("proxmox")
        self.assertEqual(self.data(sections, "platforms")["proxmox"], {"version": "8.2.7"})
        self.assertEqual(self.data(sections, "machine")["virtualization"], "physical")
        guests = self.data(sections, "proxmox")["guests"]
        self.assertEqual(sorted(guests, key=lambda g: g["vmid"]), [
            {"vmid": "100", "name": "haos", "type": "qemu", "status": "running", "ostype": "l26"},
            {"vmid": "101", "name": "arpol-brain", "type": "lxc", "status": "running",
             "ostype": "debian"},
            {"vmid": "104", "name": "odoo-migrate", "type": "lxc", "status": "stopped",
             "ostype": "ubuntu"},
        ])

    def test_proxmox_without_root(self):
        """Not root and no --sudo: the section needing root is skipped, not failed."""
        sections = self.sections("proxmox", extra_env={"STUB_UID": "1000"})
        self.assertEqual(sections["proxmox"]["status"], "skipped")
        self.assertIn("--sudo", sections["proxmox"]["reason"])
        self.assertEqual(self.data(sections, "platforms")["proxmox"], {"version": "8.2.7"})

    def test_failing_command(self):
        """A failing command gives an error section; the others are unaffected."""
        sections = self.sections("proxmox", extra_env={"STUB_FAIL_PCT": "1"})
        self.assertEqual(sections["proxmox"]["status"], "error")
        self.assertIn("pct", sections["proxmox"]["message"])
        for name in ("machine", "os", "platforms"):
            self.assertEqual(sections[name]["status"], "ok", name)

    # ------------------------------------------------------------------ cloudron
    def test_cloudron(self):
        sections = self.sections("cloudron")
        self.assertEqual(self.data(sections, "os")["id"], "ubuntu")
        self.assertEqual(self.data(sections, "os")["version_id"], "24.04")
        platforms = self.data(sections, "platforms")
        self.assertEqual(platforms["cloudron"], {"version": "8.1.0"})
        self.assertEqual(platforms["docker"], {"version": "27.3.1"})
        cloudron = self.data(sections, "cloudron")
        self.assertEqual(cloudron["version"], "8.1.0")
        self.assertEqual(cloudron["apps_source"], "cli")
        self.assertEqual(cloudron["apps"], [
            {"id": "6cd145c1-0445-4834-a734-1eb559c00b24", "name": "Odoo",
             "version": "18.0.0", "domain": "odoo.eoloa.eu"},
            {"id": "0a1b2c3d-1111-2222-3333-444455556666", "name": 'Cloud "Airmes"',
             "version": "4.21.3", "domain": "cloud.eoloa.eu"},
        ])

    def test_cloudron_docker_fallback(self):
        sections = self.sections("cloudron", extra_env={"STUB_FAIL_CLOUDRON": "1"})
        cloudron = self.data(sections, "cloudron")
        self.assertEqual(cloudron["apps_source"], "docker")
        self.assertEqual(cloudron["apps"], [
            {"id": "6cd145c1-0445-4834-a734-1eb559c00b24", "name": "com.odoo.cloudronapp",
             "version": "18.0.0", "domain": "odoo.eoloa.eu"},
            {"id": "0a1b2c3d-1111-2222-3333-444455556666", "name": "org.nextcloud.cloudronapp",
             "version": "4.21.3", "domain": "cloud.eoloa.eu"},
        ])

    # ------------------------------------------------------------------ alpine
    def test_alpine(self):
        sections = self.sections("alpine")
        os_data = self.data(sections, "os")
        self.assertEqual(os_data["id"], "alpine")
        self.assertEqual(os_data["version_id"], "3.20.3")
        self.assertIsNone(os_data["version_codename"])
        self.assertEqual(os_data["package_manager"], "apk")
        machine = self.data(sections, "machine")
        self.assertIsNone(machine["machine_id"])
        self.assertEqual(machine["virtualization"], "unknown")
        self.assertEqual(machine["ips"], [
            {"address": "10.0.3.15", "family": "inet", "interface": "eth0"},
            {"address": "fd00::15", "family": "inet6", "interface": "eth0"},
        ])

    # ------------------------------------------------------------------ weird
    def test_weird_strings(self):
        sections = self.sections("weird")
        self.assertEqual(self.data(sections, "machine")["hostname"], 'h"q\\b\tt\nl\ufffdz')
        self.assertEqual(self.data(sections, "os")["pretty_name"], 'W "q" b\\s\tt\nl\ufffdz')

    # ------------------------------------------------------------------ zerok
    def test_zerok(self):
        proc, _leftovers = run_raw("zerok")
        raw = proc.stdout.decode()
        self.assertNotIn("topsecret", raw)
        sections = json.loads(raw)["sections"]
        self.assertEqual(
            self.data(sections, "platforms")["zerok"],
            {"path": "/opt/apps/myc-deploy", "compose": True},
        )
        zerok = self.data(sections, "zerok")
        self.assertEqual(zerok["path"], "/opt/apps/myc-deploy")
        # No compose.yml text: only the services parsed from it, masked; the private_key block
        # scalar is not understood (counted, skipped).
        self.assertEqual(set(zerok), {"path", "services", "parse_warnings"})
        self.assertEqual(zerok["parse_warnings"], 1)
        self.assertEqual(zerok["services"], [
            {"name": "odoo-v18", "charm": "odoo-tecnativa",
             "image": "docker.0k.io/mirror/odoo:rc_18.0-ARPOL-ODOO-DEV-18.0",
             "command": ["--log-level=warn", "--workers=4", "--db_password=***"],
             "volumes": ["/srv/datastore/data/odoo-v18/addons:/opt/odoo/auto/dev:rw"]},
            {"name": "postgres", "charm": None, "image": "docker.0k.io/postgres:16.0-myc",
             "command": ["postgres", "-c", "max_connections=200"], "volumes": []},
            {"name": "frontend", "charm": "apache", "image": None, "command": [],
             "volumes": ["/etc/ssl:/etc/ssl:ro"]},
        ])

    # ------------------------------------------------------------------ zerok_odoo
    def test_zerok_odoo_docker(self):
        proc, _leftovers = run_raw("zerok_odoo")
        raw = proc.stdout.decode()
        # No secret anywhere: Env, command line, labels, image Env, repos.yaml, git URL, odoo.conf.
        self.assertNotIn("secret123", raw)
        sections = json.loads(raw)["sections"]
        self.assertEqual(self.data(sections, "platforms")["docker"], {"version": "20.10.24"})
        docker = self.data(sections, "docker")
        self.assertEqual(docker["version"], "20.10.24")
        self.assertEqual(
            [c["name"] for c in docker["containers"]],
            ["myc_odoo-v18_1", "myc_postgres_1", "myc_frontend_1"],
        )
        odoo = docker["containers"][0]
        self.assertEqual(odoo["inspect"]["Name"], "/myc_odoo-v18_1")
        self.assertEqual(odoo["inspect"]["State"]["Status"], "running")
        self.assertEqual(odoo["inspect"]["Mounts"][0]["Destination"], "/opt/odoo/auto/dev")
        # Only the identification labels are kept.
        self.assertEqual(odoo["inspect"]["Config"]["Labels"], {
            "com.docker.compose.project": "myc", "com.docker.compose.service": "odoo-v18",
        })
        self.assertNotIn("Binds", odoo["inspect"]["HostConfig"])
        self.assertEqual(odoo["image_inspect"]["RepoTags"],
                         ["docker.0k.io/mirror/odoo:rc_18.0-ARPOL-ODOO-DEV-18.0"])
        self.assertEqual(docker["containers"][2]["inspect"]["Config"]["Env"], None)

    def test_docker_secret_filter_without_jq(self):
        """Env filtering is done by sed on the docker inspect text (no jq in the scenarios)."""
        proc, _leftovers = run_raw("zerok_odoo")
        containers = json.loads(proc.stdout.decode())["sections"]["docker"]["data"]["containers"]
        odoo = containers[0]
        self.assertEqual(odoo["inspect"]["Config"]["Env"], [
            "PGHOST=postgres",
            "PGUSER=odoo-v18",
            "PGPASSWORD=***",
            "ADMIN_PASSWORD=***",
            "smtp_password=***",
            "Api_Token=***",
            "OPENERP_SERVER=/opt/odoo/auto/odoo.conf",
            "ODOO_VERSION=18.0",
            "PATH=/usr/local/bin:/usr/bin:/bin",
            "DB_FILTER=***",
        ])
        self.assertEqual(odoo["inspect"]["Args"][-1], "--db_password=***")
        self.assertEqual(odoo["inspect"]["Config"]["Cmd"][-1], "--db_password=***")
        self.assertEqual(odoo["image_inspect"]["Config"]["Env"],
                         ["ODOO_VERSION=18.0", "GEOIP_LICENSE_KEY=***"])
        self.assertEqual(containers[1]["inspect"]["Config"]["Env"],
                         ["POSTGRES_PASSWORD=***", "PGDATA=***"])

    def test_zerok_odoo_instance(self):
        sections = self.sections("zerok_odoo")
        instances = self.data(sections, "odoo")["instances"]
        # the frontend mentions odoo in its arguments (--upstream http://odoo:8069): no Odoo
        self.assertEqual(len(instances), 1)
        odoo = instances[0]
        self.assertEqual(odoo["container"], "myc_odoo-v18_1")
        # read in release.py of the server sources, never from `odoo --version`
        self.assertEqual(odoo["version"], "18.0")
        # From the command line (spaces removed), not from odoo.conf.
        self.assertEqual(odoo["addons_path"], ["/opt/odoo/auto/dev/ArPol-odoo-dev",
                                               "/opt/odoo/auto/addons"])
        self.assertEqual(odoo["addons"], {
            "/opt/odoo/auto/dev/ArPol-odoo-dev": ["maintenance_sw_base", "maintenance_sw_odoo"],
            "/opt/odoo/auto/addons": ["base", "maintenance_sw_base", "ovh_api", "sale"],
        })
        # repos.yaml parsed into repositories (no text of it output)
        self.assertNotIn("repos_yaml", odoo)
        self.assertEqual(odoo["repos_spec"], {"parse_warnings": 0, "items": [
            {"name": "odoo", "path": "/opt/odoo/custom/src/odoo",
             "target": {"remote": "origin", "ref": "18.0"},
             "remotes": {"origin": "https://github.com/OCA/OCB.git"}, "upstreams": {},
             "merges": ["origin 18.0"]},
            {"name": "private-addons", "path": "/opt/odoo/custom/src/private-addons",
             "target": None,
             "remotes": {"origin": "https://***@git.example.com/arpol/private.git"},
             "upstreams": {}, "merges": ["origin 18.0"]},
            {"name": "ArPol-odoo-dev", "path": "/opt/odoo/custom/src/ArPol-odoo-dev",
             "target": {"remote": "origin", "ref": "18.0"},
             "remotes": {"origin": "https://git.0k.io/mirror/arpol/ArPol-odoo-dev.git"},
             "upstreams": {"origin": "https://github.com/arpol/ArPol-odoo-dev.git"},
             "merges": ["origin 18.0"]},
        ]})
        self.assertEqual(odoo["repos"], [{
            "path": "/opt/odoo/custom/src/private-addons",
            "url": "https://***@git.example.com/arpol/private.git",
            "branch": "18.0", "commit": "0123456789abcdef0123456789abcdef01234567",
        }])
        # The dev addons mount holds a git checkout (read on the host, without git).
        self.assertEqual(odoo["mount_repos"], [{
            "path": "/opt/odoo/auto/dev/ArPol-odoo-dev",
            "url": "https://github.com/arpol/ArPol-odoo-dev.git",
            "branch": "18.0-maintenance-sw", "commit": "4444dddd4444dddd4444dddd4444dddd4444dddd",
        }])
        self.assertEqual(odoo["mount_repos_status"], [
            {"destination": "/opt/odoo/auto/dev", "status": "ok", "reason": None},
        ])
        # Every link of /opt/odoo/auto/addons (which repository provides each module) ...
        self.assertEqual(odoo["addons_links"], [
            {"link": "/opt/odoo/auto/addons/base",
             "target": "/opt/odoo/custom/src/odoo/odoo/addons/base"},
            {"link": "/opt/odoo/auto/addons/maintenance_sw_base",
             "target": "/opt/odoo/custom/src/ArPol-odoo-dev/maintenance_sw_base"},
            {"link": "/opt/odoo/auto/addons/ovh_api",
             "target": "/opt/odoo/auto/dev/ovh_connector/ovh_api"},
            {"link": "/opt/odoo/auto/addons/sale",
             "target": "/opt/odoo/custom/src/odoo/addons/sale"},
        ])
        # ... and those outside the image sources.
        self.assertEqual(odoo["runtime_links"], [{
            "link": "/opt/odoo/auto/addons/ovh_api",
            "target": "/opt/odoo/auto/dev/ovh_connector/ovh_api",
        }])
        self.assertEqual(odoo["config"], {
            "db_host": "postgres", "db_port": "5432", "db_name": "False",
            "dbfilter": "^arpol$", "data_dir": "/var/lib/odoo",
            "addons_path": "/opt/odoo/auto/addons",
        })
        databases = odoo["databases"]
        self.assertEqual(databases["status"], "ok", databases)
        # "scratch" has no ir_module_module: not an Odoo database.
        self.assertEqual(databases["items"], [{"name": "arpol", "modules": [
            {"name": "base", "version": "18.0.1.3", "state": "installed"},
            {"name": "maintenance_sw_base", "version": "18.0.1.0.0", "state": "to_upgrade"},
            {"name": "old_module", "version": None, "state": "to_remove"},
            {"name": "sale", "version": "18.0.1.2", "state": "installed"},
        ]}, {"name": "arpol_test", "modules": [
            {"name": "base", "version": "18.0.1.3", "state": "installed"},
            {"name": "ovh_api", "version": "18.0.1.5.0", "state": "installed"},
        ]}])

    # ------------------------------------------------------------------ manual_odoo
    def test_manual_odoo(self):
        proc, _leftovers = run_raw("manual_odoo")
        raw = proc.stdout.decode()
        self.assertNotIn("secret123", raw)
        sections = json.loads(raw)["sections"]
        instances = self.data(sections, "odoo")["instances"]
        self.assertEqual([i["container"] for i in instances], ["odoo-web"])
        odoo = instances[0]
        self.assertEqual(odoo["version"], "18.0")  # no release.py found: ODOO_VERSION
        self.assertEqual(odoo["addons_path"], [
            "/mnt/extra-addons/oca-web", "/mnt/extra-addons/custom",
            "/usr/lib/python3/dist-packages/odoo/addons",
        ])
        self.assertEqual(odoo["addons"]["/mnt/extra-addons/oca-web"],
                         ["web_environment_ribbon", "web_responsive"])
        self.assertIsNone(odoo["repos_spec"])
        self.assertEqual(odoo["runtime_links"], [])
        self.assertEqual(odoo["addons_links"], [])
        self.assertEqual(odoo["mount_repos_status"], [
            {"destination": "/mnt/extra-addons", "status": "ok", "reason": None},
        ])
        oca_web = {"path": "/mnt/extra-addons/oca-web", "url": "https://github.com/OCA/web.git",
                   "branch": "18.0", "commit": "1111aaaa1111aaaa1111aaaa1111aaaa1111aaaa"}
        custom = {"path": "/mnt/extra-addons/custom",
                  "url": "https://***@git.example.com/arpol/custom.git",
                  "branch": "main", "commit": "2222bbbb2222bbbb2222bbbb2222bbbb2222bbbb"}
        # Mounted repositories read on the host (git dirs of the bind source, path in container).
        self.assertEqual(odoo["mount_repos"], [custom, oca_web])
        # No git in the image: the addons_path repositories are read on the host too.
        self.assertEqual(odoo["repos"], [oca_web, custom])
        self.assertEqual(odoo["config"], {
            "db_host": "db", "db_port": "5432", "db_name": None, "dbfilter": None,
            "data_dir": None,
            "addons_path": "/mnt/extra-addons/oca-web, /mnt/extra-addons/custom,"
                           "/usr/lib/python3/dist-packages/odoo/addons",
        })
        # Postgres found by its alias on the Odoo network, not the homonym on another network;
        # psql user from db_user (no PGUSER).
        self.assertEqual(odoo["databases"], {"status": "ok", "items": [{"name": "manual", "modules": [
            {"name": "base", "version": "18.0.1.3", "state": "installed"},
            {"name": "web_responsive", "version": "18.0.1.0.2", "state": "installed"},
        ]}]})

    def test_mount_source_unread(self):
        """An unreadable or missing mount source is reported as such, not as an empty one."""
        if os.geteuid() == 0:
            self.skipTest("root reads any directory")

        def unreadable(root):
            os.chmod(os.path.join(root, "srv", "addons"), 0)

        odoo = self.data(self.sections("manual_odoo", prepare=unreadable), "odoo")["instances"][0]
        self.assertEqual(odoo["mount_repos"], [])
        status = odoo["mount_repos_status"]
        self.assertEqual([(s["destination"], s["status"]) for s in status],
                         [("/mnt/extra-addons", "skipped")])
        self.assertIn("root privileges required", status[0]["reason"])

        def missing(root):
            shutil.rmtree(os.path.join(root, "srv", "addons"))

        odoo = self.data(self.sections("manual_odoo", prepare=missing), "odoo")["instances"][0]
        self.assertEqual(odoo["mount_repos"], [])
        self.assertEqual(odoo["mount_repos_status"], [{
            "destination": "/mnt/extra-addons", "status": "error",
            "reason": "mount source not found on the host",
        }])

    # ------------------------------------------------------------------ docker_denied
    def test_docker_denied(self):
        sections = self.sections("docker_denied")
        for name in ("docker", "odoo"):
            self.assertIn(sections[name]["status"], ("skipped", "error"), name)
        self.assertIn("--sudo", sections["docker"]["reason"])
        self.assertEqual(self.data(sections, "platforms")["docker"], {"version": "24.0.7"})
        for name in ("machine", "os"):
            self.assertEqual(sections[name]["status"], "ok", name)

    # ------------------------------------------------------------------ robustness
    def test_no_temp_dir(self):
        """mktemp impossible: no file written anywhere, sections still run, JSON valid."""
        before = set(os.listdir("/tmp"))
        proc, leftovers = run_raw(
            "proxmox", extra_env={"TMPDIR": "/nonexistent", "STUB_FAIL_PCT": "1"}
        )
        self.assertEqual(leftovers, [])  # HOME, working directory
        self.assertFalse(os.path.exists("/nonexistent"))
        # No fallback temp dir (tmp.* / discover*) in /tmp either.
        self.assertEqual(
            [n for n in set(os.listdir("/tmp")) - before if n.startswith(("tmp.", "discover."))],
            [],
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, b"")
        sections = json.loads(proc.stdout.decode())["sections"]
        for name in ("machine", "os", "platforms"):
            self.assertEqual(sections[name]["status"], "ok", name)
        self.assertEqual(sections["proxmox"]["status"], "error")
        self.assertIsInstance(sections["proxmox"]["message"], str)
        # zerok_odoo goes through every docker/odoo path without a temp dir too.
        proc, _leftovers = run_raw("zerok_odoo", extra_env={"TMPDIR": "/nonexistent"})
        sections = json.loads(proc.stdout.decode())["sections"]
        self.assertEqual(sections["odoo"]["status"], "ok")
        self.assertEqual(sections["odoo"]["data"]["instances"][0]["databases"]["status"], "ok")

    def test_bash_stdin(self):
        """`ssh host 'bash -s' < discover.sh`: a command reading stdin cannot eat the script."""
        greedy_hostname = "#!/usr/bin/env bash\ncat >/dev/null\necho greedy\n"
        result = run_scenario(
            "zerok_odoo", stdin_script=True, extra_bin={"hostname": greedy_hostname}
        )
        sections = result["sections"]
        self.assertEqual(list(sections), SECTIONS)
        self.assertEqual(self.data(sections, "machine")["hostname"], "greedy")
        self.assertEqual(len(self.data(sections, "odoo")["instances"]), 1)
        # Same result as from the file.
        from_file = run_scenario("zerok_odoo", extra_bin={"hostname": greedy_hostname})
        self.assertEqual(from_file["sections"], sections)

    def test_manual_odoo_without_git(self):
        """git unusable on the host: url/branch/commit read from the .git files."""
        sections = self.sections("manual_odoo", extra_env={"STUB_GIT_BROKEN": "1"})
        odoo = self.data(sections, "odoo")["instances"][0]
        self.assertEqual(odoo["mount_repos"], [
            {"path": "/mnt/extra-addons/custom",
             "url": "https://***@git.example.com/arpol/custom.git",
             "branch": "main", "commit": "2222bbbb2222bbbb2222bbbb2222bbbb2222bbbb"},
            {"path": "/mnt/extra-addons/oca-web", "url": "https://github.com/OCA/web.git",
             "branch": "18.0", "commit": "1111aaaa1111aaaa1111aaaa1111aaaa1111aaaa"},
        ])

    # ------------------------------------------------------------------ leaky
    def test_leaky_no_secret(self):
        """Every LEAKnn marker is a secret: none may appear in the raw output."""
        proc, _leftovers = run_raw("leaky")
        raw = proc.stdout.decode()
        self.assertEqual(re.findall(r"LEAK\d+", raw), [])
        sections = json.loads(raw)["sections"]
        containers = self.data(sections, "docker")["containers"]
        odoo, redis = containers[0]["inspect"], containers[1]["inspect"]
        self.assertEqual(odoo["Args"], [
            "odoo", "-c", "/srv/conf/odoo.conf", "--db_host", "pgx", "-r", "leakuser",
            "--addons-path=/mnt/a,/mnt/a, /mnt/b",
            "--db_password", "***", "-w", "***", "--pass", "***",
            "sh -c 'odoo --db_password ***'",
            "x; PGPASSWORD='***' psql",
            'y; DB_PASSWORD="***" z',
            "mysql -uroot -p***",
            "redis-cli -a *** ping",
            'EXTRA="--db_password=*** --workers=2"',
            "--DB_PASSWORD ***\n--db_password ***",
            "--db_password\t***",
            # after a secret key word (Authorization:, Bearer): masked up to the end of the item
            "curl -H 'Authorization: ***",
            "Bearer ***",
            # -u / --user: user:password masked, a plain user kept
            "-u", "***",
            "curl -u *** http://x",
            # attached forms of -u / --user
            "--user=***", "-u***",
            # Authorization: / Cookie: / Set-Cookie: headers, value attached or not, any case
            "curl -H Authorization:***", "AUTHORIZATION:***", "-H'authorization:***",
            "Cookie: ***", "Cookie:***", "set-cookie:***",
            # webhook URLs: path after the known prefix; secret-like query parameters
            "https://hooks.slack.com/***",
            "notify https://discord.com/api/webhooks/*** now",
            "https://h.example.com/cb?Sig=***&a=1&access_token=***",
            '--user="***"',
            # attached headers named like a credential; look-alike host:port / headers kept
            "curl -H X-Api-Key:***", "-H'X-Auth-Token:***", "Private-Token:***",
            "x-access-token:***", "Api-Key:***", "X-Vault-Token:***", "apikey:***",
            "keycloak:24.0", "keycloak-db:5432", "authelia-redis:6379", "authentik-server:9000",
            "passbolt-db:3306", "token-db:5432", "X-Forwarded-Proto:https",
            "Content-Type:application/json", "gunicorn -b 0.0.0.0:8069", "psql -U odoo",
            # user / cookie options: after a NAME=, --proxy-user, -U, -b, --cookie
            "ODOO_ARGS=--user=***", "ODOO_ARGS=--user ***", "--proxy-user=***",
            "--proxy-user", "***", "curl -U *** http://x", "-b", "***",
            "curl --cookie *** http://x", "--cookie=***",
            # JSON header objects
            '{"Authorization":***', '{"Cookie": ***',
        ])
        self.assertEqual(odoo["Config"]["Cmd"], ["odoo", "--db_password", "***", "--user=***"])
        self.assertEqual(odoo["Config"]["Entrypoint"],
                         ["/entrypoint.sh", "https://outlook.office.com/webhook/***"])
        # Env: every name, the value only for a short allowlist (still masked), *** otherwise
        self.assertEqual(odoo["Config"]["Env"], [
            "ADMIN_PASSWORD=***", "DATABASE_URL=***", "ODOO_ARGS=***", "SMTP_PWD=***",
            "HTTP_AUTH=***", "GIT_AUTHOR_NAME=***", "PWD=***", "ODOO_ARGS2=***", "GIT_URL=***",
            "DSN=***", "CONTACT=***", "IMG=***",
            "HOST=***@db", "USER=leakuser", "TZ=Europe/Paris", "PATH=/usr/local/bin:/usr/bin",
            # allowlisted names: first line of the value only, then masked like any value
            "LANG=C.UTF-8 ***", "PGHOST=https://acme.webhook.office.com/***",
            "PORT=https://h/?api_key=***", "PGUSER=Cookie:***", "PGPORT=--user=***",
            "USER=X-Auth-Token:***",
            "DB_PW=***", "PGPWD=***", "ODOO_ADMIN_PW=***", "API_SALT=***", "GITHUB_PAT=***",
            "SLACK_URL=***", "RCLONE_CONFIG=***", "OPTS=***", "CURL_HEADER=***", "NOVALUE",
        ])
        self.assertEqual(redis["Args"], ["redis-server", "--requirepass", "***"])
        # Reduced objects: no Healthcheck, health log, binds, other labels, image history.
        self.assertNotIn("Healthcheck", odoo["Config"])
        self.assertNotIn("Health", odoo["State"])
        self.assertEqual(odoo["HostConfig"], {
            "NetworkMode": "leaky_default", "RestartPolicy": {"Name": "always", "MaximumRetryCount": 0},
        })
        self.assertEqual(odoo["Config"]["Labels"], {
            "com.docker.compose.project": "leaky",
            "com.docker.compose.project.config_files": "/srv/a&b/compose.yml",
            "org.opencontainers.image.source": "https://***@h/x",
        })
        image = containers[0]["image_inspect"]
        self.assertNotIn("ContainerConfig", image)
        self.assertEqual(image["RepoTags"], ["odoo:17.0"])
        self.assertEqual(image["Config"]["Env"],
                         ["ODOO_VERSION=17.0", "PG_VERSION=16.1", "BUILD_TOKEN_FILE=***",
                          "ODOO_RC=/etc/odoo.conf ***",
                          "OPENERP_SERVER=https://discordapp.com/api/webhooks/***", "TZ=-u***",
                          "LANG=apikey:***"])
        self.assertEqual(image["Config"]["Labels"], {"org.opencontainers.image.source": "https://***@h/x"})
        # compose.yml: services only; block and flow lists masked, image digest kept
        services = self.data(sections, "zerok")["services"]
        self.assertNotIn("compose_yml", self.data(sections, "zerok"))
        self.assertEqual(services[0]["image"], "reg:5000/odoo@sha256:abababababababababababababababababababababababababababababababab")
        self.assertEqual(services[0]["command"],
                         ["--db_password", "***", "PGPASSWORD=***", "--workers=2",
                          "ODOO_ARGS=--db_password=***", "--user=***", "-u***",
                          "Authorization:***", "Cookie: ***", "https://hooks.slack.com/***",
                          "https://h/x?ok=1&pwd=***&b=2", "X-Api-Key:***",
                          "--proxy-user", "***", "-b", "***", "keycloak-db:5432",
                          "Content-Type:application/json"])
        # services named like secrets keep their data; nothing but name, charm, image, command,
        # volumes is read (environment, options... never output)
        self.assertEqual([s["name"] for s in services],
                         ["odoo", "flowsvc", "bare", "keycloak", "authelia", "passbolt", "skipper",
                          "dupsvc", "weird"])
        self.assertEqual(services[1]["command"], ["odoo", "--db_password", "***"])
        self.assertEqual(services[2]["command"], ["odoo", "--db_password", "***", "-w", "***"])
        self.assertEqual(services[3], {
            "name": "keycloak", "charm": "keycloak", "image": "quay.io/keycloak/keycloak:24.0",
            # list at the same indent as its key
            "command": ["start", "--db-password", "***"],
            # quoted flow items are not split on their commas
            "volumes": ["/srv/kc:/opt/kc", "a, b:/c"],
        })
        self.assertEqual(services[4], {
            "name": "authelia", "charm": "authelia", "image": "authelia/authelia:4",
            # YAML double-quoted escapes decoded, then masked item by item
            "command": ["--db_password\n***", "--db_password\t***", "it's", 'x"y', "--config", "/c"],
            "volumes": [],
        })
        self.assertEqual(services[5], {
            "name": "passbolt", "charm": None, "image": "passbolt/passbolt:latest",
            "command": ["--db_password", "***"], "volumes": [],
        })
        # a command item not understood (tag, unsupported escape, block scalar, quoted or plain
        # scalar spanning lines) is skipped, and the item after it is masked (it may be its value)
        self.assertEqual(services[6]["command"],
                         ["odoo", "***", "***", "***", "***", "***", "--workers=2"])
        # duplicate key: the first one wins, nothing appended from the second
        self.assertEqual(services[7]["command"], ["--db_password"])
        # not understood (multi-line plain scalar, flow map, multi-line flow list, block scalar,
        # list item in a mapping, tab indentation): skipped, never echoed
        self.assertEqual(services[8], {
            "name": "weird", "charm": None, "image": None, "command": [], "volumes": [],
        })
        self.assertEqual(self.data(sections, "zerok")["parse_warnings"], 14)
        # Image references with a digest are not taken for user:password@host
        self.assertEqual(odoo["Config"]["Image"], "odoo:17.0@sha256:abababababababababababababababababababababababababababababababab")
        self.assertEqual(image["RepoDigests"], ["reg:5000/odoo@sha256:abababababababababababababababababababababababababababababababab"])
        odoo_instance = self.data(sections, "odoo")["instances"][0]
        self.assertEqual(odoo_instance["mount_repos"], [{
            "path": "/mnt/r1", "url": "https://***@gitlab.com/r1.git", "branch": "main",
            "commit": "cafecafecafecafecafecafecafecafecafecafe",
        }])
        # repos.yaml: only name, path, target, remotes, frozen upstreams and active merges are
        # read (token:, auth:, credentials:... never output); repositories named like secrets kept
        self.assertNotIn("repos_yaml", odoo_instance)
        spec = odoo_instance["repos_spec"]
        self.assertEqual(spec["parse_warnings"], 2)  # pem: | block, deploy: {flow map}
        self.assertEqual(spec["items"], [
            {"name": "odoo", "path": "/opt/odoo/custom/src/odoo", "target": None,
             "remotes": {"origin": "https://***@git.example.com/x.git", "other": "postgres://***@h"},
             "upstreams": {}, "merges": ["origin 17.0"]},
            {"name": "private-addons", "path": "/opt/odoo/custom/src/private-addons",
             "target": {"remote": "origin", "ref": "17.0"},
             "remotes": {"origin": "https://***@github.com/x/private.git"},
             "upstreams": {}, "merges": ["origin 17.0"]},
            # upstreams: only the "Automatically frozen" comments, with a remote name and a URL
            # (token: x, bad name: url ignored); commented merges ignored;
            # ssh://git@ keeps its plain user, quoted keys understood
            {"name": "frozen", "path": "/opt/odoo/custom/src/frozen",
             "target": {"remote": "origin", "ref": "17.0-frozen"},
             "remotes": {"origin": "ssh://git@git.example.com:5022/frozen.git",
                         "quoted": "https://***@h/q.git"},
             "upstreams": {"origin": "https://***@github.com/OCA/frozen.git"},
             "merges": ["origin mirror/17.0-x", "origin refs/pull/1/head"]},
        ])

    def test_leaky_odoo_command_line(self):
        """-c, --db_host and -r of the command line win over the defaults and odoo.conf."""
        sections = self.sections("leaky")
        odoo = self.data(sections, "odoo")["instances"][0]
        # read in release.py (saas~17.2), never from `odoo --version` (no Odoo code is run)
        self.assertEqual(odoo["version"], "17.2")
        self.assertEqual(odoo["addons_path"], ["/mnt/a", "/mnt/b"])  # deduplicated
        self.assertEqual(odoo["addons"], {"/mnt/a": ["mod_a"], "/mnt/b": ["mod_b"]})
        self.assertEqual(odoo["repos"][0]["url"], "https://***@git.example.com/r.git")
        self.assertEqual(odoo["repos_spec"]["items"][0]["remotes"], {
            "origin": "https://***@git.example.com/x.git", "other": "postgres://***@h",
        })
        self.assertEqual(odoo["config"]["db_host"], "wronghost")  # odoo.conf as is
        # a database psql could not read is listed in error (never left out: the import would
        # take it for gone)
        self.assertEqual(odoo["databases"], {"status": "ok", "items": [
            {"name": "brokendb", "status": "error"},
            {"name": "flakydb", "status": "error"},
            {"name": "leakdb", "modules": [
                {"name": "base", "version": "17.0.1.3", "state": "installed"}]},
        ]})

    # ------------------------------------------------------------------ sudo
    def test_sudo_needs_password(self):
        """--sudo with a sudo asking for a password: skipped with the reason, not an error."""
        sudo = "#!/usr/bin/env bash\necho 'sudo: a password is required' >&2\nexit 1\n"
        proc, _leftovers = run_raw(
            "proxmox", extra_env={"STUB_UID": "1000"}, args=["--sudo"], extra_bin={"sudo": sudo}
        )
        sections = json.loads(proc.stdout.decode())["sections"]
        self.assertEqual(sections["proxmox"]["status"], "skipped")
        self.assertIn("password", sections["proxmox"]["reason"])
        proc, _leftovers = run_raw("docker_denied", args=["--sudo"], extra_bin={"sudo": sudo})
        sections = json.loads(proc.stdout.decode())["sections"]
        for name in ("docker", "odoo"):
            self.assertEqual(sections[name]["status"], "skipped", name)
            self.assertIn("password", sections[name]["reason"])
        # sudo refusing the command itself: "not allowed"
        denied = ("#!/usr/bin/env bash\n"
                  "echo 'Sorry, user u is not allowed to execute this as root.' >&2\nexit 1\n")
        proc, _leftovers = run_raw("docker_denied", args=["--sudo"], extra_bin={"sudo": denied})
        sections = json.loads(proc.stdout.decode())["sections"]
        self.assertEqual(sections["docker"]["status"], "skipped")
        self.assertIn("not allowed", sections["docker"]["reason"])

    def test_sudo_localized_and_command_errors(self):
        """sudo refusals are recognised whatever the locale (sudo runs with LC_ALL=C); an error
        of the command run by sudo is not taken for a sudo refusal."""
        sudo_fr = ("#!/usr/bin/env bash\n"
                   "if [ \"${LC_ALL:-}\" = C ]; then echo 'sudo: a password is required' >&2\n"
                   "else echo 'sudo: un mot de passe est nécessaire' >&2; fi\nexit 1\n")
        proc, _leftovers = run_raw(
            "proxmox", extra_env={"STUB_UID": "1000", "LC_ALL": "fr_FR.UTF-8"}, args=["--sudo"],
            extra_bin={"sudo": sudo_fr},
        )
        sections = json.loads(proc.stdout.decode())["sections"]
        self.assertEqual(sections["proxmox"]["status"], "skipped")
        self.assertIn("password", sections["proxmox"]["reason"])
        # sudo runs the command, which fails saying "not allowed": an error, not a skip
        sudo_ok = ("#!/usr/bin/env bash\nshift\n"
                   "echo \"$1: operation not allowed on this cluster\" >&2\nexit 1\n")
        proc, _leftovers = run_raw(
            "proxmox", extra_env={"STUB_UID": "1000"}, args=["--sudo"],
            extra_bin={"sudo": sudo_ok},
        )
        sections = json.loads(proc.stdout.decode())["sections"]
        self.assertEqual(sections["proxmox"]["status"], "error")

    def test_sudo_least_privilege(self):
        """sudoers allowing docker only (no `true`, no probe): docker reached through sudo -n."""
        sudo = ("#!/usr/bin/env bash\n"
                "[ \"$1\" = -n ] || exit 1\nshift\n"
                "case \"$1\" in docker) STUB_AS_ROOT=1 exec \"$@\" ;; esac\n"
                "echo 'sudo: a password is required' >&2\nexit 1\n")
        uid = "#!/usr/bin/env bash\necho 1000\n"
        proc, _leftovers = run_raw(
            "zerok_odoo", args=["--sudo"], extra_env={"STUB_DOCKER_ROOT_ONLY": "1"},
            extra_bin={"sudo": sudo, "id": uid},
        )
        sections = json.loads(proc.stdout.decode())["sections"]
        self.assertEqual(len(self.data(sections, "docker")["containers"]), 3)
        odoo = self.data(sections, "odoo")["instances"][0]
        self.assertEqual(odoo["databases"]["status"], "ok")
        self.assertEqual(self.data(sections, "platforms")["docker"], {"version": "20.10.24"})
