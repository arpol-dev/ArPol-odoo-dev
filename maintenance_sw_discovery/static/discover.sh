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
#
# Secrets: odoo.conf only leaves its container as a key whitelist; no YAML text is output:
# compose.yml and repos.yaml are parsed here (YAML_AWK, a small conservative reader: what it does
# not understand is skipped and counted in parse_warnings) and only a few values are kept (services:
# name, charm, image, command, volumes; repositories: name, path, target, remotes, frozen upstreams,
# merges); docker inspect / image inspect are reduced to the members the import needs (see
# INSPECT_KEPT, IMAGE_KEPT: no Healthcheck, health log, image history, nor labels other than
# compose / Cloudron / OCI identification). Env of containers and images: every name is kept, the
# value only for a short allowlist (ENV_KEPT: versions, Odoo configuration path, Postgres host /
# port / user / database, HOST, PORT, USER, LANG, TZ, PATH), NAME=*** otherwise. Every value kept
# is then masked on its own (one argv item, one Env string, one URL; MASK_AWK): NAME=value (also
# quoted, at any = of a word) with NAME containing PASS, SECRET, TOKEN, KEY, CREDENTIAL, PRIVATE,
# AUTH (not AUTHOR) or _PWD; the word or list item after such an option or after -w, -a, --pass,
# --requirepass; the rest of the item after a secret key word (Authorization:, DB_PASSWORD:,
# Bearer); user:password after -u / --user; -p<value>; the user info of URLs (up to the last @; a
# plain "git" user and image digests kept) and user:password@host.
# Heuristic limits: a secret passed as a free word (positional argument, other short options
# such as -P x), a URL whose password contains a blank or a quote, a non-URL value under a
# repos.yaml remote, or a secret inside an upstream URL (frozen "# <remote>: <url>" comments,
# kept only for a remote name and a URL / scp-like address, masked like remotes) may still leak; masking may hide harmless values (-p8080, the word after -a).
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
NO_PRIV=126       # priv: not root and no --sudo
SUDO_PASSWORD=120 # priv: --sudo but sudo -n wants a password for this command
SUDO_DENIED=121   # priv: --sudo but this command is not allowed by sudoers
priv() {  # command needing root: as is when root, with sudo -n when --sudo (no probe: works with
          # sudoers allowing only the needed commands); stdout passes through, stderr is read
  local err rc
  if [ "$(id -u)" = 0 ]; then run "$@"
  elif [ "$USE_SUDO" = 1 ] && have sudo; then
    # LC_ALL=C: sudo messages in English whatever the locale; only sudo's own refusal (first
    # stderr line from sudo, exit 1) is taken for one, not an error of the command it ran
    exec 4>&1
    if have timeout; then err="$(LC_ALL=C timeout 30 sudo -n "$@" 2>&1 1>&4)"; rc=$?
    else err="$(LC_ALL=C sudo -n "$@" 2>&1 1>&4)"; rc=$?; fi
    exec 4>&-
    if [ $rc -eq 1 ]; then
      case "${err%%$'\n'*}" in
        "sudo: "*"password is required"*|"sudo: "*"a terminal is required"*) return $SUDO_PASSWORD ;;
        "Sorry, user "*" is not allowed "*|"sudo: Sorry, user "*|"sudo: "*"not in the sudoers"*|*"may not run sudo"*)
          return $SUDO_DENIED ;;
      esac
    fi
    return $rc
  else return $NO_PRIV; fi
}
priv_denied() { [ "$1" -eq $NO_PRIV ] || [ "$1" -eq $SUDO_PASSWORD ] || [ "$1" -eq $SUDO_DENIED ]; }
priv_reason() {  # priv_reason RC -> why priv could not run the command
  if [ "$1" -eq $SUDO_PASSWORD ]; then
    echo "root privileges required: sudo -n refused, a password is required (allow these read-only commands without password, or run as root)"
  elif [ "$1" -eq $SUDO_DENIED ]; then
    echo "root privileges required: sudo refused, the command is not allowed for this user (sudoers)"
  else
    echo "$ROOT_REASON"
  fi
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
    priv_denied $rc && { priv_reason $rc; return 3; }
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

# ----------------------------------------------------------------------------- secrets
# Masking (awk functions shared by json_pick, the YAML readers and str_mask). It only applies to
# well-delimited values: one argv item, one NAME=value string, one URL (never to free YAML text,
# which is not output). Strings may be raw text (json = 0) or JSON string contents (json = 1:
# \" \\ \n... escapes); masking never cuts an escape sequence.
# Secret-like name: contains PASS, SECRET, TOKEN, KEY, CREDENTIAL, PRIVATE, AUTH (not AUTHOR) or
# _PWD, case-insensitive. Heuristic limits: see the script header.
# Env (Config/Env of containers and images): every name is kept, the value only for the names of
# ENV_KEPT (what the import and this script read, plus harmless ones), masked like any value.
ENV_KEPT="PG_MAJOR|PG_VERSION|ODOO_VERSION|ODOO_RC|OPENERP_SERVER|PGHOST|PGPORT|PGUSER|PGDATABASE|HOST|PORT|USER|LANG|TZ|PATH"
MASK_AWK='BEGIN { ENV_KEPT = "'"$ENV_KEPT"'"; for (_i = 1; _i < 32; _i++) { _c = sprintf("%c", _i); CTL = CTL _c; ORD[_c] = _i } }
function jstr(s,   o, i, n, c) {  # JSON string literal of raw text s
  o = ""; n = length(s)
  for (i = 1; i <= n; i++) {
    c = substr(s, i, 1)
    if (c == "\\" || c == "\"") o = o "\\" c
    else if (c == "\n") o = o "\\n"
    else if (c == "\t") o = o "\\t"
    else if (c == "\r") o = o "\\r"
    else if (index(CTL, c)) o = o sprintf("\\u%04x", ORD[c])
    else o = o c
  }
  return "\"" o "\""
}
function secret_name(n,   u) {
  u = toupper(n); gsub(/AUTHOR_/, "_", u); sub(/AUTHOR$/, "", u)
  return u ~ /PASS|SECRET|TOKEN|KEY|CREDENTIAL|PRIVATE|AUTH|_PWD/
}
function user_flag(t) { return t == "-u" || t == "--user" }  # next word: user, or user:password
function secret_word(t) {  # key word after which the rest of the item is a secret
  return tolower(t) == "bearer" || (t ~ /^[A-Za-z0-9_.-]+:$/ && secret_name(substr(t, 1, length(t) - 1)))
}
function is_flag(t) {  # option whose next word is a secret
  if (t == "-w" || t == "-a" || t == "--requirepass" || t == "--pass") return 1
  return t ~ /^--?[A-Za-z0-9_.-]+$/ && secret_name(t)
}
function whole_secret(t,   e) {  # NAME=value with a secret-like NAME (whole string)
  e = index(t, "=")
  return e > 1 && substr(t, 1, e - 1) ~ /^[A-Za-z0-9_.-]+$/ && secret_name(substr(t, 1, e - 1))
}
function quote_at(s, i,   c) {
  c = substr(s, i, 1)
  if (c == SQ || c == "\"") return c
  if (c == "\\" && substr(s, i + 1, 1) == "\"") return "\\\""
  return ""
}
function qend(s, i, q,   n, c) {  # index after the quote q closing a value that starts at i
  n = length(s)
  while (i <= n) {
    c = substr(s, i, 1)
    if (q == "\\\"") {
      if (c == "\\") { if (substr(s, i + 1, 1) == "\"") return i + 2; i += 2; continue }
    } else {
      if (c == "\\" && q == "\"") { i += 2; continue }
      if (c == q) return i + 1
    }
    i++
  }
  return n + 1
}
function sep_len(s, i, json,   c) {
  # separator at i: blank or control character, punctuation , [ ] { }, and in JSON strings
  # (json = 1) the escapes \n \t \r \u0000-\u001f
  c = substr(s, i, 1)
  if (index(" ,[]{}", c) || index(CTL, c)) return 1
  if (json && c == "\\") {
    c = substr(s, i + 1, 1)
    if (c == "n" || c == "t" || c == "r") return 2
    if (c == "u" && substr(s, i + 2, 2) == "00" && index("01", substr(s, i + 4, 1))) return 6
  }
  return 0
}
function word_end(s, i, n, json) {  # index after the word starting at i (escapes kept whole)
  while (i <= n && !sep_len(s, i, json)) i += (substr(s, i, 1) == "\\") ? 2 : 1
  return i > n ? n + 1 : i
}
function value_end(s, i, n, json,   l) {  # index after an unquoted value: up to a blank only
  while (i <= n) {
    l = sep_len(s, i, json)
    if (l && !index(",[]{}", substr(s, i, 1))) break
    i += (substr(s, i, 1) == "\\") ? 2 : 1
  }
  return i > n ? n + 1 : i
}
function count_of(s, c,   a) { return split(s, a, c) - 1 }
function tail_q(t, before,   k, c, o, seen) {
  # closing quotes / parenthesis ending the masked word t, kept when they close one opened in
  # before (the text already output): sh -c (x --db_password S) -> sh -c (x --db_password ***)
  k = length(t); o = ""
  while (k > 0) {
    c = substr(t, k, 1)
    if (index(seen, c)) break
    if (c == ")" && index(before, "(")) { o = c o; seen = seen c; k--; continue }
    if ((c == SQ || c == "\"") && count_of(before, c) % 2 == 1) {
      if (c == "\"" && k > 1 && substr(t, k - 1, 1) == "\\") { o = "\\\"" o; k-- }
      else o = c o
      seen = seen c; k--; continue
    }
    break
  }
  return o
}
function unquote(t) {  # t without the quotes / brackets around it (for option tests)
  gsub("^[\\\\\"" SQ "(\\[{,]+", "", t); gsub("[\\\\\"" SQ ")\\]},]+$", "", t)
  return t
}
function is_digest(t) {  # image digest: sha256:<hex>... (algorithm:hex, 32 hex digits or more)
  return t ~ /^[a-z0-9]+:[0-9a-fA-F]+$/ && length(t) - index(t, ":") >= 32
}
function mask_userinfo(t,   a, k, st, ui) {  # user:password@host without scheme -> ***@host
  if (index(t, "://")) return t
  a = 0; for (k = length(t); k > 0; k--) if (substr(t, k, 1) == "@") { a = k; break }
  if (!a || is_digest(unquote(substr(t, a + 1)))) return t
  st = 1
  for (k = a - 1; k > 0; k--) if (index("=\"(,;" SQ, substr(t, k, 1))) { st = k + 1; break }
  ui = substr(t, st, a - st)
  if (ui ~ /^[A-Za-z0-9_.%+-]+:/) return substr(t, 1, st - 1) "***" substr(t, a)
  return t
}
function mask_text(s, json,   out, i, j, n, tok, bare, k, e, last, name, v, q, nxt, nxu) {
  # NAME=value / NAME=<quote>v<quote> (single, double, \" quotes) with a secret-like NAME at any
  # "=" of a word (ODOO_ARGS=--db_password=x); the word after a secret option (--db_password x,
  # -a x, ODOO_ARGS=--db_password x); everything after a secret key word (Authorization: x y,
  # DB_PASSWORD: x, Bearer x); -p<value>; user:password after -u / --user; user:password@host
  out = ""; n = length(s); i = 1; nxt = 0; nxu = 0
  while (i <= n) {
    if ((k = sep_len(s, i, json)) > 0) { out = out substr(s, i, k); i += k; continue }
    j = word_end(s, i, n, json); tok = substr(s, i, j - i); bare = unquote(tok)
    if (nxu) {
      nxu = 0
      if (index(bare, ":")) { out = out "***" tail_q(tok, out); i = j; continue }
    }
    if (nxt) {
      nxt = 0; q = quote_at(s, i)
      if (q != "") { out = out q "***" q; i = qend(s, i + length(q), q); continue }
      out = out "***" tail_q(tok, out); i = j; continue
    }
    if (is_flag(bare)) { out = out tok; nxt = 1; i = j; continue }
    if (user_flag(bare)) { out = out tok; nxu = 1; i = j; continue }
    if (secret_word(bare)) {
      out = out tok
      while (j <= n && (k = sep_len(s, j, json)) > 0) { out = out substr(s, j, k); j += k }
      if (j <= n) out = out "***"
      return out
    }
    if (bare ~ /^-p[^-=]/) {
      out = out substr(tok, 1, index(tok, "-p") + 1); k = value_end(s, i, n, json)
      out = out "***" tail_q(substr(s, i, k - i), out); i = k; continue
    }
    e = 0; last = 0
    for (k = 1; k <= length(tok); k++) {
      if (substr(tok, k, 1) == "\\") { k++; continue }
      if (substr(tok, k, 1) != "=") continue
      last = k
      name = substr(tok, 1, k - 1); sub(/.*[^A-Za-z0-9_.-]/, "", name)
      if (name != "" && secret_name(name)) { e = k; break }
    }
    if (e) {
      out = out substr(s, i, e); v = i + e; q = quote_at(s, v)
      if (q != "") { out = out q "***" q; i = qend(s, v + length(q), q); continue }
      k = value_end(s, v, n, json); out = out "***" tail_q(substr(s, v, k - v), out); i = k; continue
    }
    if (last && is_flag(unquote(substr(tok, last + 1)))) { out = out tok; nxt = 1; i = j; continue }
    out = out mask_userinfo(tok); i = j
  }
  return out
}
function mask_url(s,   out, k, r, e, m, a, c, h) {
  # scheme://userinfo@host -> scheme://***@host (token or user:password), up to the LAST @
  # before a blank or quote; a plain "git" user and image digests (x@sha256:...) are kept
  out = ""
  while ((k = index(s, "://")) > 0) {
    out = out substr(s, 1, k + 2); s = substr(s, k + 3)
    m = length(s); e = 1
    while (e <= m) { c = substr(s, e, 1); if (c == " " || c == "\t" || c == SQ || c == "\"" || c == "<" || c == ">") break; e++ }
    r = substr(s, 1, e - 1); a = 0
    for (k = length(r); k > 0; k--) if (substr(r, k, 1) == "@") { a = k; break }
    if (a > 1) {
      h = substr(r, a + 1); sub(/[^0-9A-Za-z:].*$/, "", h)
      if (substr(r, 1, a - 1) != "git" && !is_digest(h)) { out = out "***"; s = substr(s, a) }
    }
  }
  return out s
}
function env_item(s, json,   e, n) {  # NAME=value of an Env list: the value only for ENV_KEPT
  e = index(s, "="); if (!e) return s
  n = substr(s, 1, e - 1)
  if (n ~ ("^(" ENV_KEPT ")$")) return n "=" mask_url(mask_text(substr(s, e + 1), json))
  return n "=***"
}
function mask_str(s, prev, path) {  # a whole JSON string; prev = previous string of the list
  if (path ~ /^(Id|Image|Config\/Image|RepoTags\/#|RepoDigests\/#)$/) return s   # image refs, ids
  if (path == "Config/Env/#") return env_item(s, 1)
  if (is_flag(prev) || (user_flag(prev) && index(s, ":"))) return "***"
  if (whole_secret(s)) return substr(s, 1, index(s, "=")) "***"
  return mask_url(mask_text(s, 1))
}
function mask_arg(s, prev) {  # one raw value (argv item, URL, "remote ref"...); prev = the
                              # previous item of its list
  if (is_flag(unquote(prev)) || (user_flag(unquote(prev)) && index(s, ":"))) return "***"
  if (whole_secret(s)) return substr(s, 1, index(s, "=")) "***"
  return mask_url(mask_text(s, 0))
}'
str_mask() {  # str_mask STRING -> STRING with its secrets masked (each line as one value)
  printf '%s\n' "$1" | LC_ALL=C awk -v SQ="'" "$MASK_AWK"'{ print mask_arg($0, "") }'
}
json_pick() {  # json_pick PATTERNS < JSON -> compact JSON keeping only the members whose path
               # (keys joined by "/", array items "#") matches one of the regexes of PATTERNS
               # (one per line), every string masked (mask_str); exit 2 on a parse error
  PICK="$1" LC_ALL=C awk -v SQ="'" "$MASK_AWK"'
    BEGIN { RS = "\001"; np = split(ENVIRON["PICK"], P, "\n") }
    { s = s $0 }
    function keep(path,   i) { for (i = 1; i <= np; i++) if (P[i] != "" && path ~ P[i]) return 1; return 0 }
    function sp() { while (p <= n && index(" \t\r\n", substr(s, p, 1)) > 0) p++ }
    function fail() { bad = 1; p = n + 1 }
    function str(   start, c) {
      start = ++p
      while (p <= n) { c = substr(s, p, 1); if (c == "\\") p += 2; else if (c == "\"") break; else p++ }
      if (p > n) { fail(); return "" }
      p++
      return substr(s, start, p - 1 - start)
    }
    function val(path, whole, prev,   c, k) {
      sp(); c = substr(s, p, 1)
      if (!whole && keep(path)) whole = 1
      if (c == "{") return obj(path, whole)
      if (c == "[") return arr(path, whole)
      if (c == "\"") { k = str(); LAST = k; if (bad || !whole) return ""; return "\"" mask_str(k, prev, path) "\"" }
      k = p
      while (p <= n && index(",]} \t\r\n", substr(s, p, 1)) == 0) p++
      if (p == k) { fail(); return "" }
      return whole ? substr(s, k, p - k) : ""
    }
    function obj(path, whole,   out, k, v, c) {
      p++; sp(); out = ""
      if (substr(s, p, 1) == "}") { p++; return whole ? "{}" : "" }
      while (p <= n) {
        sp(); if (substr(s, p, 1) != "\"") { fail(); return "" }
        k = str(); sp()
        if (substr(s, p, 1) != ":") { fail(); return "" }
        p++; v = val(path == "" ? k : path "/" k, whole, ""); sp()
        if (v != "") out = out (out == "" ? "" : ",") "\"" k "\":" v
        c = substr(s, p, 1); p++
        if (c == "}") return (out == "" && !whole) ? "" : "{" out "}"
        if (c != ",") { fail(); return "" }
      }
      fail(); return ""
    }
    function arr(path, whole,   out, v, c, prev, isstr) {
      p++; sp(); out = ""; prev = ""
      if (substr(s, p, 1) == "]") { p++; return whole ? "[]" : "" }
      while (p <= n) {
        sp(); isstr = substr(s, p, 1) == "\""
        v = val(path "/#", whole, prev); prev = isstr ? LAST : ""
        if (v != "") out = out (out == "" ? "" : ",") v
        sp(); c = substr(s, p, 1); p++
        if (c == "]") return (out == "" && !whole) ? "" : "[" out "]"
        if (c != ",") { fail(); return "" }
      }
      fail(); return ""
    }
    END {
      n = length(s); p = 1; sp(); if (p > n) exit 2
      out = val("", 0, ""); sp()
      if (bad || p <= n) exit 2
      print (out == "" ? "null" : out)
    }'
}

# ----------------------------------------------------------------------------- YAML
# Conservative block-YAML reader (awk) for compose.yml and repos.yaml: no text of these files is
# output, only the few values the readers below pick from these records, masked one by one.
#   understood: "key:" (nested mapping), "key: scalar", "key: [flow, list]" on one line, block
#   list items "- scalar" (deeper than their key or at its indent), plain, "double" (escapes
#   \n \t \r \" \\ \/ \<blank>) and 'single' quoted scalars and keys, comments, "---";
#   not understood, counted in YW (parse_warnings) and skipped with every line nested below:
#   block scalars (| >), flow maps, nested flow lists, scalars or flow lists spanning lines,
#   anchors / aliases / tags, list items that are mappings or lists, other escapes, tab indents.
# Records 1..YN: YK kind ("m" key of a mapping, "v" key: scalar, "f" key: [flow list], "i" list
# item, "s" list item not understood, "c" comment, "x" key whose scalar or flow list spans lines,
# "d" item of such a flow list), YP path (keys joined by YS), YV value
# (decoded; comment text for "c", its path being the keys of the mappings around it).
YAML_AWK='BEGIN { YS = "\034"; SN = 0; SKIP = -1; CONT = -1; YN = 0; YW = 0 }
function yrec(kind, path, v) { YN++; YK[YN] = kind; YP[YN] = path; YV[YN] = v; return YN }
function ypath(k,   j, p) {  # path of the first k keys of the stack
  p = ""; for (j = 1; j <= k; j++) p = p (j > 1 ? YS : "") SK[j]
  return p
}
function yskip(ind) { YW++; SKIP = ind }
function ytrail(s, i,   n) {  # 1 when s from i on is blank or a comment
  n = length(s)
  while (i <= n && index(" \t", substr(s, i, 1))) i++
  return i > n || substr(s, i, 1) == "#"
}
function yq(s, i,   q, c, o, n, e) {  # quoted scalar starting at i: YQ = its value; returns the
                                      # index after the closing quote, 0 when not understood
  q = substr(s, i, 1); o = ""; n = length(s); i++
  while (i <= n) {
    c = substr(s, i, 1)
    if (q == SQ) {
      if (c != SQ) { o = o c; i++; continue }
      if (substr(s, i + 1, 1) != SQ) { YQ = o; return i + 1 }
      o = o SQ; i += 2; continue
    }
    if (c == "\"") { YQ = o; return i + 1 }
    if (c != "\\") { o = o c; i++; continue }
    e = substr(s, i + 1, 1)
    if (e == "n") o = o "\n"
    else if (e == "t" || e == "\t") o = o "\t"
    else if (e == "r") o = o "\r"
    else if (e == "\"" || e == "\\" || e == "/" || e == " ") o = o e
    else return 0
    i += 2
  }
  return 0
}
function yplain(s,   k, c) {  # plain scalar s (trimmed): YQ = its value without comment; 0 when
                              # not understood (indicator first, a mapping, a nested list...)
  c = substr(s, 1, 1)
  if (c == "" || index("[]{},#&*!|>%@`\"" SQ, c) || s ~ /^[-?:]([ \t]|$)/) return 0
  k = index(s, " #"); c = index(s, "\t#"); if (c && (!k || c < k)) k = c
  if (k) s = substr(s, 1, k - 1)
  sub(/[ \t]+$/, "", s)
  if (s ~ /:$/ || index(s, ": ") || index(s, ":\t")) return 0
  YQ = s; return 1
}
function yscalar(s,   c, e) {  # scalar s (trimmed, not empty): YQ = its value; 0 when not understood
  c = substr(s, 1, 1)
  if (c == "\"" || c == SQ) { e = yq(s, 1); return e > 0 && ytrail(s, e) }
  return yplain(s)
}
function yflow(s,   i, n, c, e, t) {  # flow list "[a, b]" on one line: YF[1..YFN]; 0 when not
                                      # understood (nested flow, flow map entry, spans lines)
  YFN = 0; n = length(s); i = 2
  while (1) {
    while (i <= n && index(" \t", substr(s, i, 1))) i++
    if (i > n) return 0
    c = substr(s, i, 1)
    if (c == "]") return ytrail(s, i + 1)
    if (c == "\"" || c == SQ) {
      e = yq(s, i); if (!e) return 0
    } else {
      e = i; while (e <= n && !index(",[]{}", substr(s, e, 1))) e++
      t = substr(s, i, e - i); sub(/[ \t]+$/, "", t)
      if (index(t, " #") || index(t, "\t#") || !yplain(t)) return 0
    }
    YF[++YFN] = YQ; i = e
    while (i <= n && index(" \t", substr(s, i, 1))) i++
    c = substr(s, i, 1)
    if (c == "]") return ytrail(s, i + 1)
    if (c != ",") return 0
    i++
  }
}
function ykey(s,   c, e, n, k) {  # "key: value" (s trimmed): YKEY, YREST = value; 0 when not one
  n = length(s); c = substr(s, 1, 1)
  if (c == "\"" || c == SQ) {
    e = yq(s, 1); if (!e) return 0
    YKEY = YQ
    while (e <= n && index(" \t", substr(s, e, 1))) e++
    if (substr(s, e, 1) != ":") return 0
    e++
    if (e <= n && !index(" \t", substr(s, e, 1))) return 0
  } else {
    if (index("[]{},#&*!|>%@`?", c)) return 0
    e = 0
    for (k = 1; k <= n; k++) {
      c = substr(s, k, 1)
      if (c == "#" && k > 1 && index(" \t", substr(s, k - 1, 1))) return 0
      if (c == ":" && (k == n || index(" \t", substr(s, k + 1, 1)))) { e = k; break }
    }
    if (!e) return 0
    YKEY = substr(s, 1, e - 1); sub(/[ \t]+$/, "", YKEY)
    if (YKEY == "") return 0
    e++
  }
  YREST = substr(s, e); sub(/^[ \t]+/, "", YREST); sub(/[ \t]+$/, "", YREST)
  return 1
}
function yline(line,   ind, s, k, p, v) {  # read one line
  sub(/\r$/, "", line)
  if (line ~ /^[ \t]*$/) return
  match(line, /^ */); ind = RLENGTH; s = substr(line, ind + 1)
  if (SKIP >= 0) { if (ind > SKIP) return; SKIP = -1 }
  if (s ~ /^[ \t]*#/) {
    sub(/^[ \t]+/, "", s)
    k = SN; while (k > 0 && SI[k] >= ind) k--
    yrec("c", ypath(k), s); return
  }
  if (CONT >= 0) {  # a deeper line after a scalar continues it: the scalar is dropped
    k = CONT; CONT = -1
    if (ind > k) {  # block item -> "s"; key: scalar or [flow] -> "x", its flow items -> "d"
      YK[CRA] = (YK[CRA] == "i") ? "s" : "x"; for (v = CRA + 1; v <= CRB; v++) YK[v] = "d"
      yskip(k); return
    }
  }
  if (substr(s, 1, 1) == "\t") { yskip(ind); return }
  if (s ~ /^(---|\.\.\.)([ \t]|$)/) { SN = 0; if (!ytrail(s, 4)) YW++; return }
  if (s ~ /^-([ \t]|$)/) {  # list item of the key above it (deeper, or at the same indent)
    while (SN > 0 && (SI[SN] > ind || (SI[SN] == ind && ST[SN] == "m"))) SN--
    if (SN == 0 || ST[SN] == "m") { yskip(ind); return }
    ST[SN] = "l"
    v = substr(s, 2); sub(/^[ \t]+/, "", v)
    if (v == "" || !yscalar(v)) { yrec("s", ypath(SN), ""); yskip(ind); return }
    CRA = CRB = yrec("i", ypath(SN), YQ); CONT = ind; return
  }
  if (!ykey(s)) { yskip(ind); return }
  while (SN > 0 && SI[SN] >= ind) SN--
  if (SN > 0) { if (ST[SN] == "l") { yskip(ind); return }; ST[SN] = "m" }
  p = ypath(SN); p = p (SN ? YS : "") YKEY
  v = YREST
  if (v == "" || substr(v, 1, 1) == "#") {
    SN++; SI[SN] = ind; SK[SN] = YKEY; ST[SN] = ""; yrec("m", p, ""); return
  }
  if (substr(v, 1, 1) == "[") {
    if (!yflow(v)) { yskip(ind); return }
    CRA = yrec("f", p, ""); for (k = 1; k <= YFN; k++) yrec("i", p, YF[k])
    CRB = YN; CONT = ind; return
  }
  if (!yscalar(v)) { yskip(ind); return }
  CRA = CRB = yrec("v", p, YQ); CONT = ind
}'
compose_services() {  # stdin compose.yml -> '"services": [...], "parse_warnings": N'
  # A service is a top-level mapping (its name is never taken for a secret); only its charm,
  # image, command and volumes are read, as <service>/<field> or <service>/docker-compose/<field>
  # (the first key found wins, a duplicate key is ignored with its items), every value masked
  # (command: item by item; after an item not understood, the next item is masked: it may be the
  # value of a secret option).
  LC_ALL=C awk -v SQ="'" "$MASK_AWK$YAML_AWK"'
    BEGIN { SKIPPED = "\001skipped" }
    { yline($0) }
    function jv(s, f) { return ((s, f) in F) ? jstr(mask_arg(F[s, f], "")) : "null" }
    END {
      ns = 0
      for (i = 1; i <= YN; i++) {
        np = split(YP[i], q, YS); k = YK[i]
        if (np == 1) { if (k == "m" && !(q[1] in SV)) { SV[q[1]] = ++ns; SNAME[ns] = q[1] }; continue }
        if (!(q[1] in SV) || k == "c") continue
        s = SV[q[1]]
        if (np == 2) f = q[2]; else if (np == 3 && q[2] == "docker-compose") f = q[3]; else continue
        if (f != "charm" && f != "image" && f != "command" && f != "volumes") continue
        list = f == "command" || f == "volumes"
        if (k == "m" || k == "f" || k == "v" || k == "x") {
          # key of the field: the first one is its source, a later one a duplicate (ignored, and
          # so are its items)
          if ((s, f) in SRC) { DONE[s, f] = 1; continue }
          SRC[s, f] = YP[i]
          if (k == "v") { if (list) L[s, f, ++LN[s, f]] = YV[i]; else F[s, f] = YV[i] }
          continue
        }
        if ((k != "i" && k != "s") || !list || ((s, f) in DONE) || !((s, f) in SRC) || SRC[s, f] != YP[i]) continue
        L[s, f, ++LN[s, f]] = (k == "i") ? YV[i] : SKIPPED
      }
      printf "\"services\": ["
      for (s = 1; s <= ns; s++) {
        printf "%s{\"name\": %s, \"charm\": %s, \"image\": %s, \"command\": [", (s > 1 ? ", " : ""), \
          jstr(SNAME[s]), jv(s, "charm"), jv(s, "image")
        prev = ""; sep = ""
        for (k = 1; k <= LN[s, "command"] + 0; k++) {
          v = L[s, "command", k]
          if (v == SKIPPED) { prev = "--pass"; continue }   # unknown item: mask the next one
          printf "%s%s", sep, jstr(mask_arg(v, prev)); prev = v; sep = ", "
        }
        printf "], \"volumes\": ["; sep = ""
        for (k = 1; k <= LN[s, "volumes"] + 0; k++) {
          v = L[s, "volumes", k]
          if (v != SKIPPED) { printf "%s%s", sep, jstr(mask_arg(v, "")); sep = ", " }
        }
        printf "]}"
      }
      printf "], \"parse_warnings\": %d", YW
    }'
}
repos_spec() {  # stdin repos.yaml (doodba) -> {"items": [...], "parse_warnings": N}
  # A repository is a top-level mapping (./name: path under /opt/odoo/custom/src); only its
  # target, remotes, merges (active items) and the "# # Automatically frozen:" comments of its
  # remotes (upstreams: the "# <remote>: <url>" lines right after) are read, every value masked.
  LC_ALL=C awk -v SQ="'" "$MASK_AWK$YAML_AWK"'
    { yline($0) }
    function is_repo_url(u) {  # URL (scheme://...) or scp-like git address (user@host:path, host.tld:path)
      return u ~ /^[A-Za-z][A-Za-z0-9+.-]*:\/\/[^ \t]+$/ \
        || u ~ /^([A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+|[A-Za-z0-9_-]+\.[A-Za-z0-9_.-]+):[^ \t]+$/
    }
    function madd(r, m, k, v) {
      if ((r, m, k) in MS) return
      MS[r, m, k] = 1; MK[r, m, ++MC[r, m]] = k; MV[r, m, MC[r, m]] = v
    }
    function jmap(r, m,   k, o) {
      o = ""
      for (k = 1; k <= MC[r, m] + 0; k++) o = o (k > 1 ? ", " : "") jstr(MK[r, m, k]) ": " jstr(mask_arg(MV[r, m, k], ""))
      return "{" o "}"
    }
    END {
      nr = 0; fz = 0
      for (i = 1; i <= YN; i++) {
        np = split(YP[i], q, YS)
        if (YK[i] == "c") {
          t = YV[i]; sub(/^#[ \t]*/, "", t)
          if (np == 2 && q[2] == "remotes" && (q[1] in R)) {
            if (t ~ /^#[ \t]*Automatically frozen/) { fz = 1; continue }
            if (fz && ykey(t) && YKEY ~ /^[A-Za-z0-9_.-]+$/ && YREST != "" && yscalar(YREST) && is_repo_url(YQ)) {
              madd(R[q[1]], "u", YKEY, YQ); continue
            }
          }
          fz = 0; continue
        }
        fz = 0
        if (np == 1) { if (YK[i] == "m" && !(q[1] in R)) { R[q[1]] = ++nr; RK[nr] = q[1] }; continue }
        if (!(q[1] in R)) continue
        r = R[q[1]]
        if (np == 3 && q[2] == "remotes" && YK[i] == "v") madd(r, "r", q[3], YV[i])
        else if (np == 2 && q[2] == "target" && YK[i] == "v" && !(r in TG)) TG[r] = YV[i]
        else if (np == 2 && q[2] == "merges" && YK[i] == "i") MG[r, ++MN[r]] = YV[i]
      }
      printf "{\"items\": ["
      for (r = 1; r <= nr; r++) {
        name = RK[r]; sub(/^\.\//, "", name); sub(/\/+$/, "", name)
        if (substr(name, 1, 1) == "/") { path = name; sub(/.*\//, "", name) }
        else path = "/opt/odoo/custom/src/" name
        tg = "null"
        if (r in TG) {
          t = mask_arg(TG[r], "")
          if (match(t, /[ \t]+/)) tg = "{\"remote\": " jstr(substr(t, 1, RSTART - 1)) ", \"ref\": " jstr(substr(t, RSTART + RLENGTH)) "}"
          else tg = "{\"remote\": " jstr(t) ", \"ref\": null}"
        }
        o = ""
        for (k = 1; k <= MN[r] + 0; k++) o = o (k > 1 ? ", " : "") jstr(mask_arg(MG[r, k], ""))
        printf "%s{\"name\": %s, \"path\": %s, \"target\": %s, \"remotes\": %s, \"upstreams\": %s, \"merges\": [%s]}", \
          (r > 1 ? ", " : ""), jstr(name), jstr(path), tg, jmap(r, "r"), jmap(r, "u"), o
      }
      printf "], \"parse_warnings\": %d}", YW
    }'
}

# ----------------------------------------------------------------------------- zerok
ZEROK_DIR=/opt/apps/myc-deploy
collect_zerok() {
  local f="$ZEROK_DIR/compose.yml" content rc
  fe "$f" || { echo "no 0k deployment ($f not found)"; return 3; }
  if [ -r "${ROOT}$f" ]; then
    content="$(rf "$f")"
  else
    content="$(priv cat "${ROOT}$f")"; rc=$?
    priv_denied $rc && { echo "$f not readable: $(priv_reason $rc)"; return 3; }
    [ $rc -eq 0 ] || { echo "cannot read $f (exit $rc)" >&2; return 1; }
  fi
  # No text of compose.yml is output: only the services parsed from it (compose_services).
  printf '{"path": %s, %s}' "$(json_str "$ZEROK_DIR")" "$(printf '%s\n' "$content" | compose_services)"
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
  if priv_denied $rc; then echo "cannot access the Docker daemon: $(priv_reason $rc)"; return 3; fi
  echo "cannot access the Docker daemon (docker ps exit $rc)" >&2; return 1
}
# What is kept of `docker inspect` / `docker image inspect` (json_pick paths): what the import
# needs, nothing else (no Healthcheck, health log, HostConfig details, image history, other labels).
LABELS_KEPT='(com\.docker\.compose\.[^/]*|compose\.[^/]*|isCloudronManaged|appId|fqdn|org\.opencontainers\.image\.(version|revision|source|title|created))'
INSPECT_KEPT="^(Id|Created|Path|Args|Name|Image|RestartCount|Platform|Driver)\$
^State/(Status|Running|Paused|Restarting|OOMKilled|Dead|Pid|ExitCode|Error|StartedAt|FinishedAt)\$
^Config/(Hostname|User|WorkingDir|Image|Cmd|Entrypoint|Env)\$
^Config/Labels/$LABELS_KEPT\$
^Mounts\$
^HostConfig/(NetworkMode|RestartPolicy)\$
^NetworkSettings/Networks/[^/]*/(Aliases|DNSNames|NetworkID|IPAddress|Gateway|MacAddress)\$"
IMAGE_KEPT="^(Id|RepoTags|RepoDigests|Created|Architecture|Os|Size)\$
^Config/Env\$
^Config/Labels/$LABELS_KEPT\$"
dk_object() {  # dk_object KEPT ARGS... -> the object of `docker ARGS` (an inspect array of one),
               # reduced to the KEPT paths, secrets masked; null when not one valid JSON object
  local kept="$1" out; shift
  out="$(trim "$(dk "$@")")"
  [[ $out == \[*\] ]] && out="$(trim "${out:1:${#out}-2}")"
  if [[ $out == \{*\} ]] && out="$(printf '%s' "$out" | json_pick "$kept")" \
     && [[ $out == \{*\} ]] && printf '%s' "$out" | json_flat >/dev/null; then
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
    obj="$(dk_object "$INSPECT_KEPT" inspect "$id")"
    name="$id" image="" iobj=null
    if [ "$obj" != null ]; then
      flat="$(printf '%s' "$obj" | json_flat)"
      name="$(jget "$flat" .Name)"; name="${name#/}"; [ -n "$name" ] || name="$id"
      image="$(jget "$flat" .Image)"
    fi
    [ -n "$image" ] && iobj="$(dk_object "$IMAGE_KEPT" image inspect "$image")"
    containers+="$sep{\"name\": $(json_str "$name"), \"inspect\": $obj, \"image_inspect\": $iobj}"
    sep=", "
  done
  printf '{"version": %s, "containers": [%s]}' "$(jnull "$(docker_version)")" "$containers"
}

# ----------------------------------------------------------------------------- odoo
# Shell snippets run in the Odoo container (`sh -c SNIPPET TAG ARGS...`; read only).
# release.py of the Odoo sources: its version_info line, read (no Python, no Odoo code is run)
VERSION_SH='for f in "$@" /opt/odoo/custom/src/odoo/odoo/release.py /usr/lib/python3/dist-packages/odoo/release.py /opt/odoo/odoo/release.py /odoo/odoo/release.py /usr/local/lib/python3*/*-packages/odoo/release.py; do [ -f "$f" ] && [ -r "$f" ] || continue; grep -m 1 -E "^version_info[[:space:]]*=" "$f" && exit 0; done; exit 1'
CONF_SH='for f in "$@"; do [ -r "$f" ] || continue; grep -E "^[[:space:]]*(addons_path|db_host|db_port|db_name|db_user|dbfilter|data_dir)[[:space:]]*=" "$f"; exit 0; done; exit 1'
ADDONS_SH='for d in "$@"; do for m in "$d"/*/__manifest__.py; do [ -f "$m" ] || continue; m="${m%/__manifest__.py}"; printf "%s\t%s\n" "$d" "${m##*/}"; done; done'
REPOS_SH='for d in /opt/odoo/custom/src/* "$@"; do [ -e "$d/.git" ] || continue; if command -v git >/dev/null 2>&1 && c=$(git -c safe.directory="*" -C "$d" rev-parse HEAD 2>/dev/null); then u=$(git -c safe.directory="*" -C "$d" config --get remote.origin.url 2>/dev/null); b=$(git -c safe.directory="*" -C "$d" rev-parse --abbrev-ref HEAD 2>/dev/null); printf "ok\t%s\t%s\t%s\t%s\n" "$d" "$u" "$b" "$c"; else printf "na\t%s\n" "$d"; fi; done'
LINKS_SH='cd /opt/odoo/auto/addons 2>/dev/null || exit 0; for l in *; do [ -L "$l" ] || continue; t=$(readlink -f "$l" 2>/dev/null) || t=$(readlink "$l"); printf "%s\t%s\n" "/opt/odoo/auto/addons/$l" "$t"; done'
# Run on the host (read only), as is or through priv: git dirs at or right under $1 ("." = $1).
# Exit 2 when the source does not exist; a file holds no checkout (exit 0, nothing listed).
GITDIRS_SH='[ -e "$1" ] || exit 2; [ -d "$1" ] || exit 0; if [ -e "$1/.git" ]; then echo .; exit 0; fi; for d in "$1"/*/; do [ -e "$d.git" ] || continue; d="${d%/}"; echo "${d##*/}"; done; exit 0'

is_odoo() {  # FLAT: the image name (last part of its repository), or the program run (Path,
            # Entrypoint[0], Cmd[0], base name) mentions odoo; not any argument (a proxy with
            # --upstream odoo:8069 is no Odoo)
  printf '%s\n' "$1" | LC_ALL=C awk -F'\t' '
    $1 == ".Config.Image" { v = $3; sub(/@.*/, "", v); sub(/.*\//, "", v); sub(/:.*/, "", v) }
    $1 == ".Path" || $1 == ".Config.Entrypoint[0]" || $1 == ".Config.Cmd[0]" { v = $3; sub(/.*\//, "", v) }
    $1 == ".Config.Image" || $1 == ".Path" || $1 == ".Config.Entrypoint[0]" || $1 == ".Config.Cmd[0]" {
      if (tolower(v) ~ /odoo/) found = 1
    }
    END { exit !found }'
}
release_version() {  # release_version "version_info = (18, 0, ...)" -> 18.0 (saas~17, 2 -> 17.2)
  local t="${1#*(}" major minor
  t="${t//[[:space:]\'\"]/}"
  major="${t%%,*}"; t="${t#*,}"; minor="${t%%,*}"
  major="${major##*~}"
  [[ $major =~ ^[0-9]+$ && $minor =~ ^[0-9]+$ ]] && printf '%s.%s' "$major" "$minor"
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
host_git_dirs() {  # host_git_dirs DIR -> git dirs at or right under host DIR (relative, "." = DIR);
                  # exit 2 when DIR does not exist (seen from a readable parent)
  if [ ! -e "${ROOT}$1" ] && host_readable "$(dirname "$1")"; then return 2; fi
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
  url="$(str_mask "$2")"
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
    # a database psql cannot read is listed in error: left out, it would be taken for gone
    if ! has="$(dk exec "$pg" psql -X -w -At -U "$user" -d "$db" -c "$q_has")"; then
      items+="$sep{\"name\": $(json_str "$db"), \"status\": \"error\"}"; sep=", "; continue
    fi
    [ "$(trim "$has")" = t ] || continue
    if ! out="$(dk exec "$pg" psql -X -w -At -U "$user" -d "$db" -c "$q_mods")"; then
      items+="$sep{\"name\": $(json_str "$db"), \"status\": \"error\"}"; sep=", "; continue
    fi
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
  local id="$1" flat="${FLAT[$1]}" name ver conf arg next="" path line d m t k
  local cmd_path="" cmd_conf="" cmd_host="" cmd_user=""
  local binds addons="" asep="" yaml spec repos="" rsep="" seen=" " st rest u b c hp rel
  local mrepos="" msep="" src dst links="" lsep="" config="" csep="" host user plist=""
  local alinks="" alsep="" mstatus="" mssep="" gdirs grc gst greason
  local -a paths=() confs=() releases=()
  local -A mods=()
  name="$(jget "$flat" .Name)"; name="${name#/}"
  # command line options (they win over odoo.conf)
  while IFS= read -r arg; do
    if [ -n "$next" ]; then printf -v "$next" '%s' "$arg"; next=""; continue; fi
    case "$arg" in
      --addons-path=*) cmd_path="${arg#*=}" ;;
      --addons-path) next=cmd_path ;;
      --config=*) cmd_conf="${arg#*=}" ;;
      -c|--config) next=cmd_conf ;;
      --db_host=*) cmd_host="${arg#*=}" ;;
      --db_host) next=cmd_host ;;
      --db_user=*) cmd_user="${arg#*=}" ;;
      -r|--db_user) next=cmd_user ;;
    esac
  done < <(jlist "$flat" .Args)
  # odoo.conf: only the whitelisted keys leave the container (and only 6 are output)
  [ -n "$cmd_conf" ] && confs+=("$cmd_conf")
  for k in OPENERP_SERVER ODOO_RC; do
    t="$(env_get "$flat" "$k")"; [ -n "$t" ] && confs+=("$t")
  done
  confs+=(/etc/odoo/odoo.conf /opt/odoo/auto/odoo.conf)
  conf="$(dk exec "$id" sh -c "$CONF_SH" discover-conf "${confs[@]}")"
  # addons_path: command line, else odoo.conf; trimmed, without duplicates
  [ -n "$cmd_path" ] || cmd_path="$(conf_get "$conf" addons_path)"
  while IFS= read -r -d , path; do
    path="$(trim "$path")"; [ -n "$path" ] || continue
    case "$seen" in *" $path "*) continue ;; esac
    seen+="$path "; paths+=("$path")
  done <<<"$cmd_path,"
  seen=" "
  # version: release.py (next to an addons_path directory .../odoo/addons, in the server sources
  # of the usual layouts), else ODOO_VERSION; `odoo --version` is never run (Odoo code)
  for d in "${paths[@]}"; do releases+=("${d%/}/../release.py" "${d%/}/../odoo/release.py"); done
  ver="$(release_version "$(dk exec "$id" sh -c "$VERSION_SH" discover-version "${releases[@]}")")"
  if [ -z "$ver" ]; then
    ver="$(env_get "$flat" ODOO_VERSION)"
    [[ $ver =~ ^([0-9]+\.[0-9]+) ]] && ver="${BASH_REMATCH[1]}"
  fi
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
  # repos.yaml: never output as text, only the repositories parsed from it (repos_spec)
  yaml="$(dk exec "$id" cat /opt/odoo/custom/src/repos.yaml)" || yaml=""
  spec=null
  if [ -n "$yaml" ]; then
    spec="$(printf '%s\n' "$yaml" | repos_spec)"
    printf '%s' "$spec" | json_flat >/dev/null || spec=null
  fi
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
  # git repositories of the bind mount sources (read on the host); mount_repos_status tells, per
  # bind mount, whether its source could be listed (an unread source is no empty one)
  while IFS=$'\t' read -r src dst; do
    [ -n "$src" ] || continue
    gdirs="$(host_git_dirs "$src")"; grc=$?
    if [ $grc -eq 0 ]; then gst=ok; greason=""
    elif priv_denied $grc; then gst=skipped; greason="$(priv_reason $grc)"
    elif [ $grc -eq 2 ]; then gst=error; greason="mount source not found on the host"
    else gst=error; greason="cannot list the mount source (exit $grc)"; fi
    mstatus+="$mssep{\"destination\": $(json_str "$dst"), \"status\": $(json_str "$gst"), \"reason\": $(jnull "$greason")}"
    mssep=", "
    [ $grc -eq 0 ] || continue
    while IFS= read -r rel; do
      [ -n "$rel" ] || continue
      if [ "$rel" = . ]; then mrepos+="$msep$(host_repo_json "$dst" "$src")"
      else mrepos+="$msep$(host_repo_json "${dst%/}/$rel" "${src%/}/$rel")"; fi
      msep=", "
    done <<<"$gdirs"
  done <<<"$binds"
  # links of /opt/odoo/auto/addons: all of them (addons_links: which repository provides each
  # module), and those outside the image sources (runtime_links)
  while IFS=$'\t' read -r d t; do
    [ -n "$d" ] || continue
    alinks+="$alsep{\"link\": $(json_str "$d"), \"target\": $(jnull "$t")}"; alsep=", "
    case "$t" in /opt/odoo/custom/src/*) continue ;; esac
    links+="$lsep{\"link\": $(json_str "$d"), \"target\": $(jnull "$t")}"; lsep=", "
  done < <(dk exec "$id" sh -c "$LINKS_SH" discover-links)
  for k in db_host db_port db_name dbfilter data_dir addons_path; do
    config+="$csep$(json_str "$k"): $(jnull "$(conf_get "$conf" "$k")")"; csep=", "
  done
  # databases: Postgres container of db_host (command line, odoo.conf, PGHOST, HOST); psql as
  # the Odoo user (command line, odoo.conf, PGUSER), else postgres
  host="$cmd_host"
  [ -n "$host" ] || host="$(conf_get "$conf" db_host)"
  case "$host" in False|false|None) host="" ;; esac
  [ -n "$host" ] || host="$(env_get "$flat" PGHOST)"
  [ -n "$host" ] || host="$(env_get "$flat" HOST)"
  user="$cmd_user"
  [ -n "$user" ] || user="$(conf_get "$conf" db_user)"
  case "$user" in False|false|None) user="" ;; esac
  [ -n "$user" ] || user="$(env_get "$flat" PGUSER)"
  [ -n "$user" ] || user=postgres
  for d in "${paths[@]}"; do plist+="${plist:+, }$(json_str "$d")"; done
  printf '{"container": %s, "version": %s, "addons_path": [%s], "addons": {%s}, "repos_spec": %s, "repos": [%s], "mount_repos": [%s], "mount_repos_status": [%s], "addons_links": [%s], "runtime_links": [%s], "config": {%s}, "databases": %s}' \
    "$(json_str "$name")" "$(jnull "$ver")" "$plist" \
    "$addons" "$spec" "$repos" "$mrepos" "$mstatus" "$alinks" "$links" "$config" \
    "$(odoo_databases "$id" "$host" "$user")"
}
collect_odoo() {
  local rc ids id obj instances="" sep="" ORDER=""
  local -A FLAT=()
  dk_init; rc=$?; [ $rc -eq 0 ] || return $rc
  ids="$(dk ps -q)" || { echo "docker ps failed" >&2; return 1; }
  for id in $ids; do
    obj="$(dk_object "$INSPECT_KEPT" inspect "$id")"
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
