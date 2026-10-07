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
SCENARIOS = ["debian", "proxmox", "cloudron", "alpine", "weird", "zerok"]
SECTIONS = ["machine", "os", "platforms", "proxmox", "zerok", "cloudron", "docker", "odoo"]
# Basic utilities a minimal server always has (coreutils / busybox, sed, grep, awk, iconv).
BASE_UTILS = [
    "bash", "sh", "env", "cat", "head", "tail", "sed", "grep", "awk", "iconv", "timeout",
    "mktemp", "rm", "date", "tr", "cut", "sort", "uniq", "wc", "basename", "dirname",
    "readlink", "id",
]


def run_raw(name, extra_env=None, args=(), extra_bin=None):
    """Run the script on scenario `name`; return (CompletedProcess, tmpdir listing)."""
    scenario = os.path.join(SCENARIOS_DIR, name)
    with tempfile.TemporaryDirectory(prefix="discover-test-") as tmp:
        path_dir = os.path.join(tmp, "bin")
        home = os.path.join(tmp, "home")
        tmpdir = os.path.join(tmp, "tmp")
        for directory in (path_dir, home, tmpdir):
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
            "DISCOVER_ROOT": os.path.join(scenario, "root"),
        }
        env.update(extra_env or {})
        proc = subprocess.run(
            ["bash", SCRIPT, *args], env=env, capture_output=True, timeout=60,
            executable=shutil.which("bash"),
        )
        leftovers = os.listdir(tmpdir) + os.listdir(home)
    return proc, leftovers


def run_scenario(name, extra_env=None, extra_bin=None):
    """Run the script on scenario `name` and return the parsed JSON output."""
    proc, _leftovers = run_raw(name, extra_env=extra_env, extra_bin=extra_bin)
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
        self.assertIn("charm: odoo-tecnativa", zerok["compose_yml"])
        self.assertIn("workers: 4", zerok["compose_yml"])
        # Secret keys are dropped with their nested block; inline `--x_password=` values masked.
        self.assertNotRegex(
            zerok["compose_yml"], re.compile("admin-password|private_key|BEGIN|api_token", re.I)
        )
        self.assertIn("--db_password=***", zerok["compose_yml"])
        self.assertIn("domain: arpol.fr", zerok["compose_yml"])
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
