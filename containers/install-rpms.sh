#!/bin/sh
set -eu
# A mounted repo file replaces every base-image repository; otherwise the base image's repositories are used.
if [ -f /run/secrets/yum_repo ]; then
    rm -f /etc/yum.repos.d/*.repo
    cp /run/secrets/yum_repo /etc/yum.repos.d/site.repo
fi
if command -v dnf >/dev/null; then
    dnf -y install "$@"
    dnf clean all
else
    microdnf -y install "$@"
    microdnf clean all
fi
rm -f /etc/yum.repos.d/site.repo
