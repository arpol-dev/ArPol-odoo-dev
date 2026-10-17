"""Pure helpers of the discovery importer: reading the discovery JSON, no ORM."""

import re
from datetime import datetime

# os-release ID -> catalog product
OS_PRODUCTS = {
    "debian": "Debian",
    "ubuntu": "Ubuntu",
    "rocky": "Rocky Linux",
    "almalinux": "AlmaLinux",
    "centos": "CentOS",
    "alpine": "Alpine Linux",
}


def section(data, name):
    """Data of section `name` when it ran fine, else None."""
    sec = (data.get("sections") or {}).get(name) or {}
    if sec.get("status") == "ok" and isinstance(sec.get("data"), dict):
        return sec["data"]
    return None


def version_sequence(name):
    """Catalog sequence of a version: major * 100 + minor (10 -> 1000, 8.2.7 -> 802)."""
    match = re.match(r"\D*(\d+)(?:\.(\d+))?", name or "")
    if not match:
        return 10
    return int(match.group(1)) * 100 + int(match.group(2) or 0)


def odoo_series(version):
    """Odoo series of a version: 18.0 -> 18.0, 17.0+e -> 17.0, saas~17.4 -> None."""
    match = re.match(r"(\d+)\.", version or "")
    return f"{match.group(1)}.0" if match else None


def is_under(path, directory):
    """`path` is `directory` or inside it."""
    if not path or not directory:
        return False
    directory = directory.rstrip("/") or "/"
    return path == directory or path.startswith(directory if directory == "/" else directory + "/")


def split_image_ref(ref):
    """docker.0k.io/mirror/odoo:tag@sha256:x -> ("docker.0k.io", "mirror/odoo", "tag")."""
    ref = (ref or "").split("@", 1)[0]
    name, tag = ref, False
    head, _sep, last = ref.rpartition("/")
    if ":" in last:
        last, tag = last.split(":", 1)
        name = f"{head}/{last}" if head else last
    registry = "docker.io"
    first, sep, rest = name.partition("/")
    if sep and ("." in first or ":" in first or first == "localhost"):
        registry, name = first, rest
    elif name.startswith("library/"):
        name = name[len("library/"):]
    return registry, name, tag


def parse_docker_datetime(value):
    """2026-09-29T21:00:00.123Z -> naive UTC datetime (seconds), None when unreadable."""
    match = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", value or "")
    if not match:
        return None
    return datetime.strptime(f"{match.group(1)} {match.group(2)}", "%Y-%m-%d %H:%M:%S")


def repository_name(url):
    """https://github.com/OCA/OCB.git -> OCA/OCB; git@github.com:OCA/web.git -> OCA/web."""
    url = (url or "").strip()
    match = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/]+/(.+)$", url)
    if match:
        path = match.group(1)
    else:
        path = url.split(":", 1)[1] if ":" in url else url
    path = re.sub(r"\.git/?$", "", path.strip("/"))
    return path or url


def component_role(name, url, upstream=None):
    name = (name or "").lower()
    urls = f"{url or ''} {upstream or ''}"
    if name in ("odoo", "ocb") or "/OCB" in urls or "/odoo/odoo" in urls:
        return "core"
    if name == "enterprise" or "/odoo/enterprise" in urls:
        return "enterprise"
    if "/OCA/" in urls:
        return "oca"
    return "custom"


def mount_usage(destination, repo_paths, addons_path):
    """repos (git checkouts or addons_path directories in it), logs, data or config."""
    if any(is_under(path, destination) for path in list(repo_paths) + list(addons_path)):
        return "repos"
    if destination.startswith("/var/log"):
        return "logs"
    if destination.startswith("/var/lib"):
        return "data"
    return "config"


def labels_of(inspect):
    return ((inspect or {}).get("Config") or {}).get("Labels") or {}


def env_value(env_list, name):
    for item in env_list or []:
        key, sep, value = item.partition("=")
        if sep and key == name:
            return value
    return None


def machine_ids(data):
    """(machine id, host name, root key) of a discovery; the host name stands for a missing id.

    The identity is the SMBIOS product UUID when the script found one: the machine-id is generated
    once per installation, so two servers built from the same disk image share it (the import
    would then merge them). The machine-id stays the fallback for discoveries without a UUID.
    """
    machine = section(data, "machine") or {}
    hostname = machine.get("hostname") or "unknown"
    uuid = (machine.get("product_uuid") or "").lower()
    mid = uuid or machine.get("machine_id") or f"host-{hostname}"
    return mid, hostname, f"machine:{mid}"


def clean_url(url):
    """URL without the credentials the script masked: https://***@host/x -> https://host/x."""
    return re.sub(r"://\*\*\*@", "://", (url or "").strip())


def url_identity(url):
    """What tells two repository URLs apart: not the case of the host or the path (GitHub,
    GitLab... ignore it), nor a trailing slash."""
    return clean_url(url).rstrip("/").lower()


def like_escape(text):
    """`text` taken literally in a LIKE pattern."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
