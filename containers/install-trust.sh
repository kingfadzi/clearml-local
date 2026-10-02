#!/bin/sh
# Install the staged CA bundle zip into OS trust. An empty or missing zip means no private CA is required.
set -eu
BUNDLE=/tmp/tls-ca-bundle.zip
CERT_DIR=/tmp/tls-certs
if [ -s "$BUNDLE" ]; then
    mkdir -p "$CERT_DIR"
    python3 -m zipfile -e "$BUNDLE" "$CERT_DIR"
    count=0
    for cert in $(find "$CERT_DIR" -type f \( -name '*.pem' -o -name '*.crt' -o -name '*.cer' \)); do
        cp "$cert" "/etc/pki/ca-trust/source/anchors/site-$(basename "$cert").crt"
        count=$((count + 1))
    done
    [ "$count" -gt 0 ] || { echo "install-trust: bundle has no .pem/.crt/.cer certificates" >&2; exit 1; }
    rm -rf "$CERT_DIR"
    update-ca-trust extract
    echo "install-trust: installed $count certificate file(s)"
else
    update-ca-trust extract
    echo "install-trust: no CA bundle staged; using system trust"
fi
