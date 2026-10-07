#!/usr/bin/env bash
# discover.sh — read-only description of a server for the Odoo maintenance inventory.
# Usage: discover.sh [--sudo] > "$(hostname).json"
#
#        ssh host 'bash -s' < discover.sh > host.json
#
# Read-only: no command changes the system; the only file written is this script's own
# `mktemp -d` directory, removed on exit (without one, error details are discarded instead).
# Requires bash >= 4 and coreutils/busybox (sed, awk, grep); iconv, timeout, jq, git, sudo are
# used when present. Everything runs from main(), called on the last line: with `bash -s` the
# whole script has been read before anything runs, and stdin is then closed for every command.
set -u
SCRIPT_VERSION="1.0.0"
SCHEMA_VERSION=1
ROOT="${DISCOVER_ROOT:-}"   # tests only: prefix of every file read on the target system
USE_SUDO=0
TMP=""                      # private temp dir (mktemp -d), empty when none could be made

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
  local name="$1" fn="$2" out rc err=/dev/null msg=""
  [ -n "$TMP" ] && err="$TMP/$name.err"   # never a path outside the private temp dir
  out="$("$fn" 2>"$err")"; rc=$?
  if [ $rc -eq 0 ]; then printf '%s: {"status": "ok", "data": %s}' "$(json_str "$name")" "$out"
  elif [ $rc -eq 3 ]; then printf '%s: {"status": "skipped", "reason": %s}' "$(json_str "$name")" "$(json_str "$out")"
  else
    [ -n "$TMP" ] && msg="$(head -c 500 "$err")"
    [ -n "$msg" ] || msg="$name failed (exit $rc)"
    printf '%s: {"status": "error", "message": %s}' "$(json_str "$name")" "$(json_str "$msg")"
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
    END { n = length(s); p = 1; sp(); if (p > n) exit 2; val(""); sp(); if (bad || p <= n) exit 2 }'
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
  local out flat
  have cloudron || return 1
  out="$(run cloudron list --json)" || return 1
  [ -n "$(trim "$out")" ] || return 1
  flat="$(printf '%s' "$out" | json_flat)" || return 1
  printf '%s\n' "$flat" | awk -F'\t' '
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
    }'
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

# ----------------------------------------------------------------------------- docker
SECRET_SED='([Pp][Aa][Ss][Ss]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Tt][Oo][Kk][Ee][Nn]|[Kk][Ee][Yy]|[Cc][Rr][Ee][Dd][Ee][Nn][Tt][Ii][Aa][Ll]|[Pp][Rr][Ii][Vv][Aa][Tt][Ee])'
mask_url() {  # stdin -> stdout: credentials of URLs (scheme://user:pass@host) -> ***
  sed -E 's#(://)[^/@"[:space:]\\]+@#\1***@#g'
}
mask_json() {  # stdin JSON text -> stdout with secrets masked; works on JSON string tokens, so
               # the result stays valid JSON whatever the values contain (no jq needed)
  # 1. "NAME=value" strings (Env entries, --x_password=... arguments): whole value -> ***
  # 2. "name": "value" members whose name is secret-like (labels): value -> "***"
  # 3. URL credentials;  4. NAME=value inside a longer string (stops at \ " ' , space)
  sed -E \
    -e 's/"([A-Za-z0-9_.-]*'"$SECRET_SED"'[A-Za-z0-9_.-]*)=([^"\\]|\\.)*"/"\1=***"/g' \
    -e 's/"([^"\\]*'"$SECRET_SED"'[^"\\]*)"([[:space:]]*):([[:space:]]*)"([^"\\]|\\.)*"/"\1"\3:\4"***"/g' \
    -e 's#(://)[^/@"[:space:]\\]+@#\1***@#g' \
    -e 's/([A-Za-z0-9_.-]*'"$SECRET_SED"'[A-Za-z0-9_.-]*=)[^[:space:]"'"'"'\\,]+/\1***/g'
}
# awk helpers on json_flat lines: unesc() turns a JSON-escaped string into its raw bytes (UTF-8)
JAWK='function hex(h,   i, v) {
  v = 0; h = tolower(h)
  for (i = 1; i <= length(h); i++) v = v * 16 + index("0123456789abcdef", substr(h, i, 1)) - 1
  return v
}
function utf8(c) {
  if (c < 1) return ""
  if (c < 128) return sprintf("%c", c)
  if (c < 2048) return sprintf("%c%c", 192 + int(c / 64), 128 + c % 64)
  return sprintf("%c%c%c", 224 + int(c / 4096), 128 + int(c / 64) % 64, 128 + c % 64)
}
function unesc(s,   o, i, n, c) {
  o = ""; n = length(s)
  for (i = 1; i <= n; i++) {
    c = substr(s, i, 1)
    if (c == "\\") {
      c = substr(s, ++i, 1)
      if (c == "n") c = "\n"; else if (c == "t") c = "\t"; else if (c == "r") c = "\r"
      else if (c == "b" || c == "f") c = ""
      else if (c == "u") { c = utf8(hex(substr(s, i + 1, 4))); i += 4 }
    }
    o = o c
  }
  return o
}'
jget() {  # jget FLAT PATH -> raw value at PATH (json_flat lines of an object)
  printf '%s\n' "$1" | LC_ALL=C awk -F'\t' -v p="$2" "$JAWK"'
    $1 == p { if ($2 == "s") print unesc($3); else if ($3 != "null") print $3; exit }'
}
jlist() {  # jlist FLAT PATH -> raw string items of the array at PATH, one per line
  printf '%s\n' "$1" | LC_ALL=C awk -F'\t' -v p="$2" "$JAWK"'
    index($1, p "[") == 1 && substr($1, length(p) + 1) ~ /^\[[0-9]+\]$/ && $2 == "s" { print unesc($3) }'
}

DK_MODE=direct
dk() {  # docker command; through priv when the daemon socket needs root
  if [ "$DK_MODE" = priv ]; then priv docker "$@"; else run docker "$@"; fi
}
dk_init() {  # choose the access mode; prints the reason and returns 3 (skipped) or 1 (error)
  local rc
  have docker || { echo "docker not installed"; return 3; }
  if run docker ps -q >/dev/null; then DK_MODE=direct; return 0; fi
  priv docker ps -q >/dev/null; rc=$?
  if [ $rc -eq 0 ]; then DK_MODE=priv; return 0; fi
  if [ $rc -eq 126 ]; then echo "cannot access the Docker daemon: $ROOT_REASON"; return 3; fi
  echo "cannot access the Docker daemon (docker ps exit $rc)" >&2; return 1
}
dk_object() {  # dk_object ARGS... -> the object of `docker ARGS` (an inspect array of one),
               # secrets masked; null when the answer is not exactly one valid JSON object
  local out
  out="$(dk "$@" | mask_json)"
  out="$(trim "$out")"
  [[ $out == \[*\] ]] && out="$(trim "${out:1:${#out}-2}")"
  if [[ $out == \{*\} ]] && printf '%s' "$out" | json_flat >/dev/null; then
    printf '%s' "$out"
  else
    printf 'null'
  fi
}
collect_docker() {
  local rc ids id obj flat name image iobj containers="" sep=""
  dk_init; rc=$?; [ $rc -eq 0 ] || return $rc
  ids="$(dk ps -q)" || { echo "docker ps failed" >&2; return 1; }
  for id in $ids; do
    obj="$(dk_object inspect "$id")"
    name="$id" image="" iobj=null
    if [ "$obj" != null ]; then
      flat="$(printf '%s' "$obj" | json_flat)"
      name="$(jget "$flat" .Name)"; name="${name#/}"; [ -n "$name" ] || name="$id"
      image="$(jget "$flat" .Image)"
    fi
    [ -n "$image" ] && iobj="$(dk_object image inspect "$image")"
    containers+="$sep{\"name\": $(json_str "$name"), \"inspect\": $obj, \"image_inspect\": $iobj}"
    sep=", "
  done
  printf '{"version": %s, "containers": [%s]}' "$(jnull "$(docker_version)")" "$containers"
}

# ----------------------------------------------------------------------------- odoo
# Shell snippets run in the Odoo container (`sh -c SNIPPET TAG ARGS...`; read only).
CONF_SH='for f in "$@"; do [ -r "$f" ] || continue; grep -E "^[[:space:]]*(addons_path|db_host|db_port|db_name|db_user|dbfilter|data_dir)[[:space:]]*=" "$f"; exit 0; done; exit 1'
ADDONS_SH='for d in "$@"; do for m in "$d"/*/__manifest__.py; do [ -f "$m" ] || continue; m="${m%/__manifest__.py}"; printf "%s\t%s\n" "$d" "${m##*/}"; done; done'
REPOS_SH='for d in /opt/odoo/custom/src/* "$@"; do [ -e "$d/.git" ] || continue; if command -v git >/dev/null 2>&1 && c=$(git -c safe.directory="*" -C "$d" rev-parse HEAD 2>/dev/null); then u=$(git -c safe.directory="*" -C "$d" config --get remote.origin.url 2>/dev/null); b=$(git -c safe.directory="*" -C "$d" rev-parse --abbrev-ref HEAD 2>/dev/null); printf "ok\t%s\t%s\t%s\t%s\n" "$d" "$u" "$b" "$c"; else printf "na\t%s\n" "$d"; fi; done'
LINKS_SH='cd /opt/odoo/auto/addons 2>/dev/null || exit 0; for l in *; do [ -L "$l" ] || continue; t=$(readlink -f "$l" 2>/dev/null) || t=$(readlink "$l"); printf "%s\t%s\n" "/opt/odoo/auto/addons/$l" "$t"; done'
# Run on the host (read only), as is or through priv: git dirs at or right under $1 ("." = $1).
GITDIRS_SH='if [ -e "$1/.git" ]; then echo .; exit 0; fi; for d in "$1"/*/; do [ -e "$d.git" ] || continue; d="${d%/}"; echo "${d##*/}"; done; exit 0'

is_odoo() {  # FLAT: image name or command line mentions odoo
  printf '%s\n' "$1" | LC_ALL=C awk -F'\t' '
    ($1 == ".Config.Image" || $1 == ".Path" || $1 ~ /^\.(Args|Config\.Cmd|Config\.Entrypoint)\[/) \
      && tolower($3) ~ /odoo/ { found = 1 }
    END { exit !found }'
}
env_get() {  # env_get FLAT NAME -> value of NAME in Config.Env
  jlist "$1" .Config.Env | awk -v k="$2=" 'index($0, k) == 1 { print substr($0, length(k) + 1); exit }'
}
conf_get() {  # conf_get CONF KEY -> value of KEY in odoo.conf text
  printf '%s\n' "$1" | awk -v k="$2" '
    { key = $0; sub(/[ \t]*=.*/, "", key); sub(/^[ \t]+/, "", key) }
    key == k && index($0, "=") { v = substr($0, index($0, "=") + 1); sub(/^[ \t]+/, "", v); sub(/[ \t\r]+$/, "", v); print v; exit }'
}
binds_of() {  # FLAT -> "<source>\t<destination>" of the bind mounts
  printf '%s\n' "$1" | LC_ALL=C awk -F'\t' "$JAWK"'
    match($1, /^\.Mounts\[[0-9]+\]\./) {
      i = substr($1, 9, RLENGTH - 10); k = substr($1, RLENGTH + 1)
      if (!(i in seen)) { seen[i] = 1; order[++n] = i }
      if ($2 == "s") v[i, k] = unesc($3)
    }
    END { for (j = 1; j <= n; j++) { i = order[j]; if (v[i, "Type"] == "bind") print v[i, "Source"] "\t" v[i, "Destination"] } }'
}
networks_of() {  # FLAT -> "<network>\t<alias>" (alias empty for a network without alias)
  printf '%s\n' "$1" | LC_ALL=C awk -F'\t' -v P=".NetworkSettings.Networks." "$JAWK"'
    index($1, P) == 1 {
      r = substr($1, length(P) + 1)
      if (match(r, /\.(Aliases|DNSNames)\[[0-9]+\]$/)) print unesc(substr(r, 1, RSTART - 1)) "\t" unesc($3)
      else if (match(r, /\.NetworkID$/)) print unesc(substr(r, 1, RSTART - 1)) "\t"
    }'
}
host_path() {  # host_path BINDS CONTAINER_PATH -> host path through the longest bind mount
  local src dst best="" best_src="" p="$2"
  while IFS=$'\t' read -r src dst; do
    [ -n "$dst" ] || continue
    if [ "$p" = "$dst" ] || [[ $p == "${dst%/}/"* ]]; then
      [ ${#dst} -gt ${#best} ] && { best="$dst"; best_src="$src"; }
    fi
  done <<<"$1"
  [ -n "$best" ] || return 1
  printf '%s%s' "$best_src" "${p:${#best}}"
}
host_readable() { [ -d "${ROOT}$1" ] && [ -r "${ROOT}$1" ] && [ -x "${ROOT}$1" ]; }
host_git_dirs() {  # host_git_dirs DIR -> git dirs at or right under host DIR (relative, "." = DIR)
  if host_readable "$1"; then run sh -c "$GITDIRS_SH" discover "${ROOT}$1"
  else priv sh -c "$GITDIRS_SH" discover "${ROOT}$1"; fi
}
host_git() {  # host_git DIR ARGS... -> trimmed output of git in host DIR
  local d="$1"; shift
  have git || return 1
  if host_readable "$d"; then trim "$(run git -c safe.directory='*' -C "${ROOT}$d" "$@")"
  else trim "$(priv git -c safe.directory='*' -C "${ROOT}$d" "$@")"; fi
}
git_files() {  # git_files DIR -> "url\tbranch\tcommit" read from DIR/.git files (no git needed)
  local g="$1/.git" head ref branch="" commit url
  head="$(trim "$(rf "$g/HEAD")")"
  [ -n "$head" ] || return 1
  if [[ $head == "ref: "* ]]; then
    ref="${head#ref: }"; branch="${ref#refs/heads/}"
    commit="$(trim "$(rf "$g/$ref")")"
    [ -n "$commit" ] || commit="$(rf "$g/packed-refs" | awk -v r="$ref" '$2 == r { print $1; exit }')"
  else
    commit="$head"
  fi
  url="$(rf "$g/config" | awk '
    /^[ \t]*\[/ { s = ($0 ~ /^[ \t]*\[remote "origin"\]/) }
    s && $1 == "url" { sub(/^[^=]*=[ \t]*/, ""); print; exit }')"
  printf '%s\t%s\t%s' "$url" "$branch" "$commit"
}
repo_json() {  # repo_json PATH URL BRANCH COMMIT
  local url branch="$3"
  url="$(printf '%s' "$2" | mask_url)"
  [ "$branch" = HEAD ] && branch=""
  printf '{"path": %s, "url": %s, "branch": %s, "commit": %s}' \
    "$(json_str "$1")" "$(jnull "$url")" "$(jnull "$branch")" "$(jnull "$4")"
}
host_repo_json() {  # host_repo_json CONTAINER_PATH HOST_DIR
  local url="" branch="" commit="" info
  commit="$(host_git "$2" rev-parse HEAD)"
  if [ -n "$commit" ]; then
    url="$(host_git "$2" config --get remote.origin.url)"
    branch="$(host_git "$2" rev-parse --abbrev-ref HEAD)"
  elif info="$(git_files "$2")"; then
    url="${info%%$'\t'*}"; info="${info#*$'\t'}"
    branch="${info%%$'\t'*}"; commit="${info#*$'\t'}"
  fi
  repo_json "$1" "$url" "$branch" "$commit"
}
find_pg() {  # find_pg ODOO_ID DB_HOST -> id of the running container named DB_HOST, or with
             # the alias DB_HOST on a network of the Odoo container
  local id="$1" host="$2" other name net alias nets
  for other in $ORDER; do
    [ "$other" = "$id" ] && continue
    name="$(jget "${FLAT[$other]}" .Name)"
    [ "${name#/}" = "$host" ] && { printf '%s' "$other"; return 0; }
  done
  nets="$(networks_of "${FLAT[$id]}" | cut -f1 | sort -u)"
  for other in $ORDER; do
    [ "$other" = "$id" ] && continue
    while IFS=$'\t' read -r net alias; do
      [ "$alias" = "$host" ] || continue
      if printf '%s\n' "$nets" | grep -qxF -- "$net"; then printf '%s' "$other"; return 0; fi
    done < <(networks_of "${FLAT[$other]}")
  done
  return 1
}
odoo_databases() {  # odoo_databases ODOO_ID DB_HOST USER -> {"status", ...} object
  local id="$1" host="$2" user="$3" pg pgname dbs out db has items="" sep="" mods msep line name ver state
  local q_dbs="SELECT datname FROM pg_database WHERE NOT datistemplate ORDER BY datname"
  local q_has="SELECT to_regclass('public.ir_module_module') IS NOT NULL"
  local q_mods="SELECT name, latest_version, state FROM ir_module_module WHERE state IN ('installed','to upgrade','to remove') ORDER BY name"
  if [ -z "$host" ]; then
    printf '{"status": "skipped", "reason": "no db_host in the Odoo configuration"}'; return 0
  fi
  if ! pg="$(find_pg "$id" "$host")"; then
    printf '{"status": "skipped", "reason": %s}' \
      "$(json_str "no running Postgres container for db_host $host")"
    return 0
  fi
  pgname="$(jget "${FLAT[$pg]}" .Name)"; pgname="${pgname#/}"
  if ! dbs="$(dk exec "$pg" psql -X -w -At -U "$user" -d postgres -c "$q_dbs")"; then
    printf '{"status": "skipped", "reason": %s}' \
      "$(json_str "psql as $user in container $pgname failed (password required or access refused)")"
    return 0
  fi
  while IFS= read -r db; do
    [ -n "$db" ] || continue
    has="$(dk exec "$pg" psql -X -w -At -U "$user" -d "$db" -c "$q_has")" || continue
    [ "$(trim "$has")" = t ] || continue
    out="$(dk exec "$pg" psql -X -w -At -U "$user" -d "$db" -c "$q_mods")" || continue
    mods="" msep=""
    while IFS= read -r line; do
      [ -n "$line" ] || continue
      name="${line%%|*}"; line="${line#*|}"; ver="${line%%|*}"; state="${line#*|}"
      state="${state// /_}"
      mods+="$msep{\"name\": $(json_str "$name"), \"version\": $(jnull "$ver"), \"state\": $(json_str "$state")}"
      msep=", "
    done <<<"$out"
    items+="$sep{\"name\": $(json_str "$db"), \"modules\": [$mods]}"; sep=", "
  done <<<"$dbs"
  printf '{"status": "ok", "items": [%s]}' "$items"
}
odoo_instance() {  # odoo_instance ID -> instance object of Odoo container ID
  local id="$1" flat="${FLAT[$1]}" name ver conf arg next=0 cmd_path="" path line d m t k
  local binds addons="" asep="" yaml repos="" rsep="" seen=" " st rest u b c hp rel
  local mrepos="" msep="" src dst links="" lsep="" config="" csep="" host user plist=""
  local -a paths=() confs=()
  local -A mods=()
  name="$(jget "$flat" .Name)"; name="${name#/}"
  # version
  ver="$(dk exec "$id" odoo --version)"
  if [[ $ver =~ ([0-9]+\.[0-9]+) ]]; then ver="${BASH_REMATCH[1]}"
  else
    ver="$(env_get "$flat" ODOO_VERSION)"
    [[ $ver =~ ^([0-9]+\.[0-9]+) ]] && ver="${BASH_REMATCH[1]}"
  fi
  # odoo.conf: only the whitelisted keys leave the container (and only 6 are output)
  for k in OPENERP_SERVER ODOO_RC; do
    t="$(env_get "$flat" "$k")"; [ -n "$t" ] && confs+=("$t")
  done
  confs+=(/etc/odoo/odoo.conf /opt/odoo/auto/odoo.conf)
  conf="$(dk exec "$id" sh -c "$CONF_SH" discover-conf "${confs[@]}")"
  # addons_path: command line, else odoo.conf
  while IFS= read -r arg; do
    if [ $next = 1 ]; then cmd_path="$arg"; next=0
    elif [[ $arg == --addons-path=* ]]; then cmd_path="${arg#--addons-path=}"
    elif [ "$arg" = --addons-path ]; then next=1; fi
  done < <(jlist "$flat" .Args)
  [ -n "$cmd_path" ] || cmd_path="$(conf_get "$conf" addons_path)"
  while IFS= read -r -d , path; do
    path="$(trim "$path")"; [ -n "$path" ] && paths+=("$path")
  done <<<"$cmd_path,"
  # modules per addons_path directory
  while IFS=$'\t' read -r d m; do
    [ -n "$m" ] && mods[$d]+="$m"$'\n'
  done < <(dk exec "$id" sh -c "$ADDONS_SH" discover-addons "${paths[@]}")
  for d in "${paths[@]}"; do
    m=""; asep=""
    while IFS= read -r t; do
      [ -n "$t" ] && { m+="$asep$(json_str "$t")"; asep=", "; }
    done < <(printf '%s' "${mods[$d]:-}" | LC_ALL=C sort -u)
    addons+="${addons:+, }$(json_str "$d"): [$m]"
  done
  # repos.yaml as is, NAME=value secrets and URL credentials masked
  yaml="$(dk exec "$id" cat /opt/odoo/custom/src/repos.yaml)" || yaml=""
  [ -n "$yaml" ] && yaml="$(printf '%s\n' "$yaml" | mask_inline | mask_url)"
  # git repositories: in the container, else on the host for the bind-mounted ones
  binds="$(binds_of "$flat")"
  while IFS= read -r line; do
    st="${line%%$'\t'*}"; rest="${line#*$'\t'}"; path="${rest%%$'\t'*}"
    [ -n "$path" ] || continue
    case "$seen" in *" $path "*) continue ;; esac
    seen+="$path "
    if [ "$st" = ok ]; then
      rest="${rest#*$'\t'}"; u="${rest%%$'\t'*}"; rest="${rest#*$'\t'}"
      b="${rest%%$'\t'*}"; c="${rest#*$'\t'}"
      repos+="$rsep$(repo_json "$path" "$u" "$b" "$c")"
    elif hp="$(host_path "$binds" "$path")"; then
      repos+="$rsep$(host_repo_json "$path" "$hp")"
    else
      repos+="$rsep$(repo_json "$path" "" "" "")"
    fi
    rsep=", "
  done < <(dk exec "$id" sh -c "$REPOS_SH" discover-repos "${paths[@]}")
  # git repositories of the bind mount sources (read on the host)
  while IFS=$'\t' read -r src dst; do
    [ -n "$src" ] || continue
    while IFS= read -r rel; do
      [ -n "$rel" ] || continue
      if [ "$rel" = . ]; then mrepos+="$msep$(host_repo_json "$dst" "$src")"
      else mrepos+="$msep$(host_repo_json "${dst%/}/$rel" "${src%/}/$rel")"; fi
      msep=", "
    done < <(host_git_dirs "$src")
  done <<<"$binds"
  # links of /opt/odoo/auto/addons outside the image sources
  while IFS=$'\t' read -r d t; do
    [ -n "$d" ] || continue
    case "$t" in /opt/odoo/custom/src/*) continue ;; esac
    links+="$lsep{\"link\": $(json_str "$d"), \"target\": $(jnull "$t")}"; lsep=", "
  done < <(dk exec "$id" sh -c "$LINKS_SH" discover-links)
  for k in db_host db_port db_name dbfilter data_dir addons_path; do
    config+="$csep$(json_str "$k"): $(jnull "$(conf_get "$conf" "$k")")"; csep=", "
  done
  # databases: Postgres container of db_host, psql as PGUSER / db_user / postgres
  host="$(conf_get "$conf" db_host)"
  case "$host" in False|false|None) host="" ;; esac
  [ -n "$host" ] || host="$(env_get "$flat" PGHOST)"
  [ -n "$host" ] || host="$(env_get "$flat" HOST)"
  user="$(env_get "$flat" PGUSER)"
  [ -n "$user" ] || user="$(conf_get "$conf" db_user)"
  case "$user" in ""|False|false|None) user=postgres ;; esac
  for d in "${paths[@]}"; do plist+="${plist:+, }$(json_str "$d")"; done
  printf '{"container": %s, "version": %s, "addons_path": [%s], "addons": {%s}, "repos_yaml": %s, "repos": [%s], "mount_repos": [%s], "runtime_links": [%s], "config": {%s}, "databases": %s}' \
    "$(json_str "$name")" "$(jnull "$ver")" "$plist" \
    "$addons" "$(jnull "$yaml")" "$repos" "$mrepos" "$links" "$config" \
    "$(odoo_databases "$id" "$host" "$user")"
}
collect_odoo() {
  local rc ids id obj instances="" sep="" ORDER=""
  local -A FLAT=()
  dk_init; rc=$?; [ $rc -eq 0 ] || return $rc
  ids="$(dk ps -q)" || { echo "docker ps failed" >&2; return 1; }
  for id in $ids; do
    obj="$(dk_object inspect "$id")"
    [ "$obj" = null ] && continue
    FLAT[$id]="$(printf '%s' "$obj" | json_flat)"
    ORDER+=" $id"
  done
  for id in $ORDER; do
    is_odoo "${FLAT[$id]}" || continue
    instances+="$sep$(odoo_instance "$id")"; sep=", "
  done
  printf '{"instances": [%s]}' "$instances"
}

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

main() {
  local arg name sep collected_at header out
  exec </dev/null   # the script is fully read (bash -s): no command may consume stdin
  for arg in "$@"; do
    case "$arg" in
      --sudo) USE_SUDO=1 ;;
      -h|--help) usage; exit 0 ;;
      *) echo "discover.sh: unknown option: $arg" >&2; usage >&2; exit 2 ;;
    esac
  done
  TMP="$(mktemp -d 2>/dev/null)" && [ -d "$TMP" ] || TMP=""
  trap '[ -z "$TMP" ] || rm -rf "$TMP"' EXIT

  collected_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  header="\"schema_version\": $SCHEMA_VERSION, \"script_version\": $(json_str "$SCRIPT_VERSION"), \"collected_at\": $(json_str "$collected_at")"
  out="$(
    printf '{%s, "sections": {' "$header"
    sep=""
    for name in machine os platforms proxmox zerok cloudron docker odoo; do
      printf '%s' "$sep"; section "$name" "collect_$name"; sep=", "
    done
    printf '}}'
  )"
  out="$(printf '%s' "$out" | utf8_fix)"
  if have jq && ! printf '%s' "$out" | jq -e . >/dev/null 2>&1; then
    printf '{%s, "sections": {}, "fatal": "invalid JSON produced", "raw": %s}\n' \
      "$header" "$(json_str "$out")"
  else
    printf '%s\n' "$out"
  fi
  exit 0
}

main "$@"; exit $?
