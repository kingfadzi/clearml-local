#!/bin/sh
# Install staged CA material into OS trust: a bundle zip and/or a bootstrap PEM. Empty files mean nothing to add.
set -eu
ZIP=/tmp/trust/tls-ca-bundle.zip
PEM=/tmp/trust/tls-ca-bundle.pem
CERT_DIR=/tmp/tls-certs
ANCHORS=/etc/pki/ca-trust/source/anchors
count=0
if [ -s "$ZIP" ]; then
    mkdir -p "$CERT_DIR"
    python3 -m zipfile -e "$ZIP" "$CERT_DIR"
    for cert in $(find "$CERT_DIR" -type f \( -name '*.pem' -o -name '*.crt' -o -name '*.cer' \)); do
        cp "$cert" "$ANCHORS/site-$(basename "$cert").crt"
        count=$((count + 1))
    done
    [ "$count" -gt 0 ] || { echo "install-trust: bundle has no .pem/.crt/.cer certificates" >&2; exit 1; }
    rm -rf "$CERT_DIR"
fi
if [ -s "$PEM" ]; then
    cp "$PEM" "$ANCHORS/site-bootstrap.crt"
    count=$((count + 1))
fi
update-ca-trust extract
if [ "$count" -gt 0 ]; then
    echo "install-trust: installed $count certificate file(s)"
else
    echo "install-trust: no CA material staged; using system trust"
fi
