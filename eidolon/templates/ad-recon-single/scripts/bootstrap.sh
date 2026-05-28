#!/usr/bin/env bash
# Eidolon ad-recon-single bootstrap.
# Runs once after the cloned VM boots. Verifies expected tooling is present
# (it should already be baked into the Proxmox template) and writes a
# manifest into the workspace for the operator to inspect.
set -euo pipefail

required=(
  impacket-secretsdump
  impacket-GetUserSPNs
  impacket-GetNPUsers
  impacket-getTGT
  bloodhound-python
  kerbrute
  ldapdomaindump
  netexec
  nxc
  certipy
  nmap
  curl
  jq
)

missing=()
for bin in "${required[@]}"; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    missing+=("$bin")
  fi
done

mkdir -p /var/log/eidolon
{
  echo "ad-recon-single bootstrap: $(date -u +%FT%TZ)"
  echo "host: $(hostname)"
  echo "kernel: $(uname -r)"
  if (( ${#missing[@]} > 0 )); then
    echo "missing tools:"
    printf '  - %s\n' "${missing[@]}"
  else
    echo "all required tools present"
  fi
} > /var/log/eidolon/bootstrap.log

if (( ${#missing[@]} > 0 )); then
  echo "WARNING: missing tools (${missing[*]}). Re-prepare the Proxmox template." >&2
fi

echo "ad-recon-single bootstrap complete"
