#!/usr/bin/env bash
# Eidolon blank-kali bootstrap.
# Runs once after container start to install a small baseline of packages.
# Operators are expected to extend this for engagement-specific tooling.
set -euo pipefail

apt-get update
apt-get install -y --no-install-recommends \
  curl \
  ca-certificates \
  iproute2 \
  iputils-ping \
  dnsutils \
  net-tools \
  jq \
  vim-tiny \
  openssh-client

apt-get clean
rm -rf /var/lib/apt/lists/*

echo "blank-kali bootstrap complete: $(date -u +%FT%TZ)"
