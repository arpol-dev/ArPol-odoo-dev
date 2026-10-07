#!/usr/bin/env bash
# discover.sh — read-only description of a server for the Odoo maintenance inventory.
# Usage: discover.sh [--sudo] > "$(hostname).json"
#
# Read-only: no command changes the system; the only file written is this script's own
# `mktemp -d` directory, removed on exit. Requires bash >= 4 and coreutils/busybox (sed, awk,
# grep); iconv, timeout, jq, sudo are used when present.
set -u
SCRIPT_VERSION="1.0.0"
SCHEMA_VERSION=1
ROOT="${DISCOVER_ROOT:-}"   # tests only: prefix of every file read on the target system
USE_SUDO=0
TMP="$(mktemp -d 2>/dev/null || mktemp -d -t discover)"
trap 'rm -rf "$TMP"' EXIT

json_str() {  # JSON string literal of $1 (pure bash, byte-wise)
  # Invalid UTF-8 is replaced by U+FFFD once, on the whole document (utf8_fix): this also
  # covers raw JSON embedded as is, and avoids two processes per string.
  local LC_ALL=C s="$1"
  s="${s//\\/\\\\}"; s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"; s="${s//$'\r'/\\r}"; s="${s//$'\t'/\\t}"
  s="${s//[$'\x01'-$'\x1f']/}"
  printf '"%s"' "$s"
}
jnull() {  # JSON string of $1, or null when empty
  if [ -n "$1" ]; then json_str "$1"; else printf 'null'; fi
}
rf() { cat "${ROOT}$1" 2>/dev/null; }           # read a file of the target system
fe() { [ -e "${ROOT}$1" ]; }                     # file exists on the target system
have() { command -v "$1" >/dev/null 2>&1; }
run() {  # run a command with a timeout when available; never fails the script
  if have timeout; then timeout 30 "$@" 2>/dev/null; else "$@" 2>/dev/null; fi
}
priv() {  # command needing root: as is when root, with sudo -n when --sudo
  if [ "$(id -u)" = 0 ]; then run "$@"
  elif [ "$USE_SUDO" = 1 ] && have sudo; then run sudo -n "$@"
  else return 126; fi
}
section() {  # section NAME FUNCTION -> "NAME": {...}; FUNCTION prints the data object or
             # returns 3 with a reason on stdout (skipped)
  local name="$1" fn="$2" out rc
  out="$("$fn" 2>"$TMP/$name.err")"; rc=$?
  if [ $rc -eq 0 ]; then printf '%s: {"status": "ok", "data": %s}' "$(json_str "$name")" "$out"
  elif [ $rc -eq 3 ]; then printf '%s: {"status": "skipped", "reason": %s}' "$(json_str "$name")" "$(json_str "$out")"
  else printf '%s: {"status": "error", "message": %s}' "$(json_str "$name")" "$(json_str "$(head -c 500 "$TMP/$name.err")")"
  fi
}
trim() {  # trim leading/trailing white space of $1
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"; s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

utf8_fix() {  # stdin -> stdout, every invalid UTF-8 byte replaced by U+FFFD
  # Fast path: iconv validates; the byte-wise awk pass only runs on invalid input (or
  # without iconv).
  local doc
  doc="$(cat; printf x)"; doc="${doc%x}"
  if have iconv && printf '%s' "$doc" | iconv -f UTF-8 -t UTF-8 >/dev/null 2>&1; then
    printf '%s' "$doc"; return 0
  fi
  printf '%s' "$doc" | LC_ALL=C awk '
    BEGIN { RS = "\001"; for (i = 1; i < 256; i++) ord[sprintf("%c", i)] = i; first = 1 }
    {
      if (!first) printf "\001"
      first = 0
      s = $0; n = length(s); start = 1; i = 1
      while (i <= n) {
        b = ord[substr(s, i, 1)]
        if (b < 128) { i++; continue }
        need = 0; lo = 128; hi = 191
        if (b >= 194 && b <= 223) need = 1
        else if (b >= 224 && b <= 239) { need = 2; if (b == 224) lo = 160; if (b == 237) hi = 159 }
        else if (b >= 240 && b <= 244) { need = 3; if (b == 240) lo = 144; if (b == 244) hi = 143 }
        ok = need > 0
        for (k = 1; ok && k <= need; k++) {
          c = ord[substr(s, i + k, 1)]
          if (k == 1) { if (c < lo || c > hi) ok = 0 }
          else if (c < 128 || c > 191) ok = 0
        }
        if (ok) { i += need + 1; continue }
        printf "%s\357\277\275", substr(s, start, i - start)
        i++; start = i
      }
      printf "%s", substr(s, start)
    }'
}

json_flat() {  # stdin JSON -> lines "<path>\t<s|n>\t<value>" (paths: .key, [i]);
               # string values keep their JSON escapes; exit 2 on a parse error
  LC_ALL=C awk '
    BEGIN { RS = "\001" }
    { s = s $0 }
    function sp() { while (p <= n && index(" \t\r\n", substr(s, p, 1)) > 0) p++ }
    function fail() { bad = 1; p = n + 1 }
    function str(   start, c) {
      start = ++p
      while (p <= n) {
        c = substr(s, p, 1)
        if (c == "\\") p += 2; else if (c == "\"") break; else p++
      }
      if (p > n) { fail(); return "" }
      p++
      return substr(s, start, p - 1 - start)
    }
    function prim(path,   start, c) {
      start = p
      while (p <= n) { c = substr(s, p, 1); if (index(",]} \t\r\n", c) > 0) break; p++ }
      if (p == start) { fail(); return }
      print path "\tn\t" substr(s, start, p - start)
    }
    function val(path,   c) {
      sp(); c = substr(s, p, 1)
      if (c == "{") obj(path)
      else if (c == "[") arr(path)
      else if (c == "\"") { c = str(); if (!bad) print path "\ts\t" c }
      else prim(path)
    }
    function obj(path,   k, c) {
      p++; sp()
      if (substr(s, p, 1) == "}") { p++; return }
      while (p <= n) {
        sp(); if (substr(s, p, 1) != "\"") { fail(); return }
        k = str(); sp()
        if (substr(s, p, 1) != ":") { fail(); return }
        p++; val(path "." k); sp()
        c = substr(s, p, 1); p++
        if (c == "}") return
        if (c != ",") { fail(); return }
      }
      fail()
    }
    function arr(path,   i, c) {
      p++; sp()
      if (substr(s, p, 1) == "]") { p++; return }
      i = 0
      while (p <= n) {
        val(path "[" i "]"); i++; sp()
        c = substr(s, p, 1); p++
        if (c == "]") return
        if (c != ",") { fail(); return }
      }
      fail()
    }
    END { n = length(s); p = 1; sp(); if (p > n) exit 2; val(""); if (bad) exit 2 }'
}

# ----------------------------------------------------------------------------- machine
ip_rows() {  # "<address>\t<family>\t<interface>" for every address, from ip -j addr or ip addr
  local out
  out="$(run ip -j addr)"
  if [ "$(trim "$out" | head -c 1)" = "[" ]; then
    printf '%s' "$out" | json_flat | awk -F'\t' '
      $1 ~ /^\[[0-9]+\]\.ifname$/ { ifn = $3 }
      $1 ~ /\.addr_info\[[0-9]+\]\.family$/ { fam = $3 }
      $1 ~ /\.addr_info\[[0-9]+\]\.local$/ { print $3 "\t" fam "\t" ifn }'
    return 0
  fi
  run ip addr | awk '
    /^[0-9]+: / { ifn = $2; sub(/:$/, "", ifn); sub(/@.*/, "", ifn) }
    $1 == "inet" || $1 == "inet6" { a = $2; sub(/\/.*/, "", a); print a "\t" $1 "\t" ifn }'
}

ips_json() {
  local addr fam ifn sep="" lower
  while IFS=$'\t' read -r addr fam ifn; do
    [ -n "$addr" ] || continue
    lower="$(printf '%s' "$addr" | tr 'A-F' 'a-f')"
    case "$lower" in 127.*|::1|fe80:*) continue ;; esac
    [ "$ifn" = lo ] && continue
    case "$fam" in inet|inet6) ;; *) continue ;; esac
    printf '%s{"address": %s, "family": %s, "interface": %s}' "$sep" \
      "$(json_str "$addr")" "$(json_str "$fam")" "$(jnull "$ifn")"
    sep=", "
  done < <(ip_rows)
}

virtualization() {  # physical, vm, lxc, container or unknown
  local v
  if have systemd-detect-virt; then
    v="$(trim "$(run systemd-detect-virt)")"
    case "$v" in
      none) echo physical; return ;;
      lxc|lxc-libvirt) echo lxc; return ;;
      docker|podman|openvz|systemd-nspawn|rkt|wsl|proot|pouch|container-other) echo container; return ;;
      "") ;;
      *) echo vm; return ;;
    esac
  fi
  v="$(rf /proc/1/environ | tr '\000' '\n')"
  case $'\n'"$v" in
    *$'\ncontainer=lxc'*) echo lxc; return ;;
    *$'\ncontainer='*) echo container; return ;;
  esac
  if fe /.dockerenv; then echo container; return; fi
  v="$(rf /proc/cpuinfo)"
  if [ -n "$v" ]; then
    case "$v" in *hypervisor*) echo vm ;; *) echo physical ;; esac
    return
  fi
  echo unknown
}

collect_machine() {
  local hn mid
  hn="$(run hostname)"
  [ -n "$hn" ] || hn="$(rf /etc/hostname | head -n 1)"
  [ -n "$hn" ] || hn="$(run uname -n)"
  mid="$(rf /etc/machine-id)"; [ -n "$mid" ] || mid="$(rf /var/lib/dbus/machine-id)"
  mid="${mid//[[:space:]]/}"
  printf '{"hostname": %s, "machine_id": %s, "ips": [%s], "virtualization": %s}' \
    "$(jnull "$hn")" "$(jnull "$mid")" "$(ips_json)" "$(json_str "$(virtualization)")"
}

# ----------------------------------------------------------------------------- os
OSR=""
osr_get() {  # value of KEY in $OSR (os-release syntax: "..." with \ escapes, '...', bare)
  local LC_ALL=C line val o i c n
  local -a lines
  mapfile -t lines <<<"$OSR"
  for ((n = 0; n < ${#lines[@]}; n++)); do
    line="${lines[n]}"
    [[ $line == "$1="* ]] || continue
    val="${line#*=}"
    if [[ $val == \"* ]]; then
      o=""; i=1
      while :; do
        while (( i < ${#val} )); do
          c="${val:i:1}"
          if [ "$c" = "\\" ]; then i=$((i + 1)); o+="${val:i:1}"
          elif [ "$c" = '"' ]; then printf '%s' "$o"; return 0
          else o+="$c"; fi
          i=$((i + 1))
        done
        n=$((n + 1)); (( n < ${#lines[@]} )) || break   # quoted value spanning lines
        o+=$'\n'; val="${lines[n]}"; i=0
      done
      printf '%s' "$o"
    elif [[ $val == \'* ]]; then
      val="${val#\'}"; printf '%s' "${val%\'}"
    else
      printf '%s' "$val"
    fi
    return 0
  done
  return 1
}

collect_os() {
  local pm=""
  OSR="$(rf /etc/os-release)"; [ -n "$OSR" ] || OSR="$(rf /usr/lib/os-release)"
  if have dpkg; then pm=dpkg; elif have rpm; then pm=rpm; elif have apk; then pm=apk; fi
  printf '{"id": %s, "version_id": %s, "version_codename": %s, "pretty_name": %s, "kernel": %s, "package_manager": %s}' \
    "$(jnull "$(osr_get ID)")" "$(jnull "$(osr_get VERSION_ID)")" \
    "$(jnull "$(osr_get VERSION_CODENAME)")" "$(jnull "$(osr_get PRETTY_NAME)")" \
    "$(jnull "$(trim "$(run uname -r)")")" "$(jnull "$pm")"
}

# ----------------------------------------------------------------------------- platforms
proxmox_version() {
  local out
  out="$(run pveversion)"
  [[ $out =~ pve-manager/([^/[:space:]]+) ]] && printf '%s' "${BASH_REMATCH[1]}"
}
docker_version() {
  local v rc
  v="$(trim "$(run docker version --format '{{.Server.Version}}')")"
  if [ -z "$v" ]; then
    v="$(trim "$(priv docker version --format '{{.Server.Version}}')")"; rc=$?
    [ $rc -eq 0 ] || v=""
  fi
  if [ -z "$v" ]; then
    [[ "$(run docker --version)" =~ version\ ([0-9][^,[:space:]]*) ]] && v="${BASH_REMATCH[1]}"
  fi
  printf '%s' "$v"
}
collect_platforms() {
  local pve="null" zerok="null" cloudron="null" docker="null" compose=false
  have pveversion && pve="{\"version\": $(jnull "$(proxmox_version)")}"
  if fe /opt/apps/myc-deploy; then
    fe /opt/apps/myc-deploy/compose.yml && compose=true
    zerok="{\"path\": \"/opt/apps/myc-deploy\", \"compose\": $compose}"
  fi
  fe /home/yellowtent/box && \
    cloudron="{\"version\": $(jnull "$(trim "$(rf /home/yellowtent/box/VERSION)")")}"
  have docker && docker="{\"version\": $(jnull "$(docker_version)")}"
  printf '{"proxmox": %s, "zerok": %s, "cloudron": %s, "docker": %s}' \
    "$pve" "$zerok" "$cloudron" "$docker"
}

# ----------------------------------------------------------------------------- proxmox
ROOT_REASON="root privileges required (run as root or with --sudo)"
pve_ostype() {  # pve_ostype qm|pct VMID
  local line
  while IFS= read -r line; do
    [[ $line == ostype:* ]] && { trim "${line#ostype:}"; return 0; }
  done < <(priv "$1" config "$2")
}
collect_proxmox() {
  have pveversion || { echo "not a Proxmox host"; return 3; }
  local out rc line sep="" vmid name status cmd type guests=""
  local -a f
  for cmd in qm pct; do
    have "$cmd" || continue
    out="$(priv "$cmd" list)"; rc=$?
    [ $rc -eq 126 ] && { echo "$ROOT_REASON"; return 3; }
    [ $rc -eq 0 ] || { echo "$cmd list failed (exit $rc)" >&2; return 1; }
    if [ "$cmd" = qm ]; then type=qemu; else type=lxc; fi
    while IFS= read -r line; do
      read -r -a f <<<"$line"
      [ ${#f[@]} -ge 2 ] || continue
      [[ ${f[0]} =~ ^[0-9]+$ ]] || continue   # header
      vmid="${f[0]}"
      if [ "$cmd" = qm ]; then name="${f[1]}"; status="${f[2]:-}"
      else
        status="${f[1]}"; name=""
        [ ${#f[@]} -ge 3 ] && name="${f[${#f[@]}-1]}"
      fi
      guests+="$(printf '%s{"vmid": %s, "name": %s, "type": "%s", "status": %s, "ostype": %s}' "$sep" \
        "$(json_str "$vmid")" "$(jnull "$name")" "$type" "$(jnull "$status")" \
        "$(jnull "$(pve_ostype "$cmd" "$vmid")")")"
      sep=", "
    done <<<"$out"
  done
  printf '{"guests": [%s]}' "$guests"
}

# ----------------------------------------------------------------------------- zerok
ZEROK_DIR=/opt/apps/myc-deploy
SECRET_RE='(PASS|SECRET|TOKEN|KEY|CREDENTIAL|PRIVATE)'
mask_inline() {  # stdin -> stdout: NAME=value with a secret-like NAME -> NAME=***
  sed -E 's/([A-Za-z0-9_.-]*([Pp][Aa][Ss][Ss]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Tt][Oo][Kk][Ee][Nn]|[Kk][Ee][Yy]|[Cc][Rr][Ee][Dd][Ee][Nn][Tt][Ii][Aa][Ll]|[Pp][Rr][Ii][Vv][Aa][Tt][Ee])[A-Za-z0-9_.-]*=)[^[:space:]"'"'"',]+/\1***/g'
}
compose_filter() {  # stdin compose.yml -> stdout without secret keys (and their nested block)
  local line stripped item key indent drop=-1
  while IFS= read -r line || [ -n "$line" ]; do
    stripped="${line#"${line%%[![:space:]]*}"}"
    indent=$(( ${#line} - ${#stripped} ))
    if [ $drop -ge 0 ]; then
      if [ -z "$stripped" ] || [ $indent -gt $drop ]; then continue; fi
      drop=-1
    fi
    item="${stripped#- }"
    if [[ $item =~ ^[\"\']?([A-Za-z0-9_.-]+)[\"\']?:([[:space:]]|$) ]]; then
      key="${BASH_REMATCH[1]^^}"
      if [[ $key =~ $SECRET_RE ]]; then drop=$indent; continue; fi
    fi
    printf '%s\n' "$line"
  done | mask_inline
}
yaml_scalar() {  # trimmed, unquoted YAML scalar (comment removed when unquoted)
  local v
  v="$(trim "$1")"
  case "$v" in
    \"*\") v="${v:1:${#v}-2}"; v="${v//\\\"/\"}" ;;
    \'*\') v="${v:1:${#v}-2}" ;;
    *) v="$(trim "${v%% #*}")" ;;
  esac
  printf '%s' "$v"
}
yaml_items() {  # JSON items (without brackets) of an inline value: scalar or [a, b]
  local v item sep="" IFS
  v="$(trim "$1")"
  if [[ $v == \[*\] ]]; then
    v="${v:1:${#v}-2}"
    IFS=','
    for item in $v; do
      item="$(yaml_scalar "$item")"
      [ -n "$item" ] || continue
      printf '%s%s' "$sep" "$(json_str "$item")"; sep=", "
    done
  elif [ -n "$v" ]; then
    json_str "$(yaml_scalar "$v")"
  fi
}
compose_services() {  # stdin filtered compose.yml -> JSON service objects
  local line stripped indent svc="" charm="" image="" cmd="" vols="" list="" list_indent=0 sep="" k v items
  flush() {
    [ -n "$svc" ] || return 0
    printf '%s{"name": %s, "charm": %s, "image": %s, "command": [%s], "volumes": [%s]}' "$sep" \
      "$(json_str "$svc")" "$(jnull "$charm")" "$(jnull "$image")" "$cmd" "$vols"
    sep=", "
  }
  add() {  # add LIST JSON_ITEMS
    [ -n "$2" ] || return 0
    if [ "$1" = command ]; then cmd="${cmd:+$cmd, }$2"; else vols="${vols:+$vols, }$2"; fi
  }
  while IFS= read -r line || [ -n "$line" ]; do
    [[ $line =~ ^[[:space:]]*(#.*)?$ ]] && continue
    if [[ $line =~ ^([A-Za-z0-9._-]+):[[:space:]]*(#.*)?$ ]]; then
      flush; svc="${BASH_REMATCH[1]}"; charm=""; image=""; cmd=""; vols=""; list=""
      continue
    fi
    if [[ $line =~ ^[^[:space:]] ]]; then flush; svc=""; list=""; continue; fi
    [ -n "$svc" ] || continue
    stripped="${line#"${line%%[![:space:]]*}"}"
    indent=$(( ${#line} - ${#stripped} ))
    if [ -n "$list" ]; then
      if [[ $stripped == "-" || $stripped == "- "* ]] && [ $indent -ge $list_indent ]; then
        v="$(yaml_scalar "${stripped#-}")"
        [ -n "$v" ] && add "$list" "$(json_str "$v")"
        continue
      fi
      list=""
    fi
    case "$stripped" in
      charm:*) [ -n "$charm" ] || charm="$(yaml_scalar "${stripped#charm:}")" ;;
      image:*) [ -n "$image" ] || image="$(yaml_scalar "${stripped#image:}")" ;;
      command:*|volumes:*)
        k="${stripped%%:*}"; v="$(trim "${stripped#*:}")"
        if [ -z "$v" ]; then list="$k"; list_indent=$indent
        else items="$(yaml_items "$v")"; add "$k" "$items"; fi
        ;;
    esac
  done
  flush
}
collect_zerok() {
  local f="$ZEROK_DIR/compose.yml" content rc filtered
  fe "$f" || { echo "no 0k deployment ($f not found)"; return 3; }
  if [ -r "${ROOT}$f" ]; then
    content="$(rf "$f")"
  else
    content="$(priv cat "${ROOT}$f")"; rc=$?
    [ $rc -eq 126 ] && { echo "$f not readable: $ROOT_REASON"; return 3; }
    [ $rc -eq 0 ] || { echo "cannot read $f (exit $rc)" >&2; return 1; }
  fi
  filtered="$(printf '%s\n' "$content" | compose_filter)"
  printf '{"path": %s, "compose_yml": %s, "services": [%s]}' \
    "$(json_str "$ZEROK_DIR")" "$(json_str "$filtered")" \
    "$(printf '%s\n' "$filtered" | compose_services)"
}

# ----------------------------------------------------------------------------- cloudron
cloudron_apps_cli() {  # JSON app objects from `cloudron list --json` (array or {"apps": [...]})
  local out
  have cloudron || return 1
  out="$(run cloudron list --json)" || return 1
  [ -n "$(trim "$out")" ] || return 1
  printf '%s' "$out" | json_flat > "$TMP/cloudron.flat" || return 1
  awk -F'\t' '
    function q(k) { return ((i, k) in v) ? "\"" v[i, k] "\"" : "null" }
    {
      path = $1; sub(/^\.apps/, "", path)
      if (!match(path, /^\[[0-9]+\]\./)) next
      i = substr(path, 2, RLENGTH - 3) + 0; key = substr(path, RLENGTH + 1)
      if (!(i in seen)) { seen[i] = 1; order[++cnt] = i }
      if ($2 == "s") v[i, key] = $3
    }
    END {
      for (c = 1; c <= cnt; c++) {
        i = order[c]
        name = ((i, "label") in v) ? q("label") : q("manifest.title")
        domain = ((i, "fqdn") in v) ? q("fqdn") : q("domain")
        printf "%s{\"id\": %s, \"name\": %s, \"version\": %s, \"domain\": %s}", (c > 1 ? ", " : ""), q("id"), name, q("manifest.version"), domain
      }
    }' "$TMP/cloudron.flat"
}
cloudron_apps_docker() {  # JSON app objects from the Cloudron-managed containers
  local out rc line id fqdn image ref name version sep="" seen=" "
  local fmt='{{.Label "appId"}}\t{{.Label "fqdn"}}\t{{.Image}}'
  have docker || return 1
  out="$(run docker ps --filter label=isCloudronManaged=true --format "$fmt")"; rc=$?
  if [ $rc -ne 0 ]; then
    out="$(priv docker ps --filter label=isCloudronManaged=true --format "$fmt")" || return 1
  fi
  while IFS= read -r line; do
    # split by hand: with IFS=$'\t', read would merge empty fields (tab is IFS white space)
    id="${line%%$'\t'*}"; line="${line#*$'\t'}"
    fqdn="${line%%$'\t'*}"; image="${line#*$'\t'}"
    [ -n "$id" ] || continue
    case "$seen" in *" $id "*) continue ;; esac
    seen+="$id "
    ref="${image##*/}"; name="${ref%%:*}"; version=""
    [ "$ref" != "$name" ] && version="${ref#*:}"
    printf '%s{"id": %s, "name": %s, "version": %s, "domain": %s}' "$sep" \
      "$(json_str "$id")" "$(jnull "$name")" "$(jnull "$version")" "$(jnull "$fqdn")"
    sep=", "
  done <<<"$out"
}
collect_cloudron() {
  fe /home/yellowtent/box || { echo "not a Cloudron server"; return 3; }
  local apps source=null
  if apps="$(cloudron_apps_cli)"; then source='"cli"'
  elif apps="$(cloudron_apps_docker)"; then source='"docker"'
  else apps=""; fi
  printf '{"version": %s, "apps_source": %s, "apps": [%s]}' \
    "$(jnull "$(trim "$(rf /home/yellowtent/box/VERSION)")")" "$source" "$apps"
}

# ----------------------------------------------------------------------------- docker, odoo
collect_docker() { echo "not implemented"; return 3; }
collect_odoo() { echo "not implemented"; return 3; }

# ----------------------------------------------------------------------------- main
usage() {
  cat <<'EOF'
Usage: discover.sh [--sudo] > "$(hostname).json"

Read-only description of this server (machine, OS, Proxmox VE, 0k, Cloudron, Docker, Odoo)
as JSON on stdout, to import into the Odoo maintenance inventory.

  --sudo    run the commands that need root with `sudo -n` (never asks for a password);
            without it and without root, those sections are skipped
  --help    show this help

Nothing is modified on the server; secrets (passwords, tokens, keys) are not output.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --sudo) USE_SUDO=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "discover.sh: unknown option: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

COLLECTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HEADER="\"schema_version\": $SCHEMA_VERSION, \"script_version\": $(json_str "$SCRIPT_VERSION"), \"collected_at\": $(json_str "$COLLECTED_AT")"
OUT="$(
  printf '{%s, "sections": {' "$HEADER"
  sep=""
  for name in machine os platforms proxmox zerok cloudron docker odoo; do
    printf '%s' "$sep"; section "$name" "collect_$name"; sep=", "
  done
  printf '}}'
)"
OUT="$(printf '%s' "$OUT" | utf8_fix)"
if have jq && ! printf '%s' "$OUT" | jq -e . >/dev/null 2>&1; then
  printf '{%s, "sections": {}, "fatal": "invalid JSON produced", "raw": %s}\n' \
    "$HEADER" "$(json_str "$OUT")"
else
  printf '%s\n' "$OUT"
fi
exit 0
