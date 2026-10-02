#!/bin/sh
# Installs from the repositories baked into the base image.
set -eu
if command -v dnf >/dev/null; then
    dnf -y install "$@"
    dnf clean all
else
    microdnf -y install "$@"
    microdnf clean all
fi
