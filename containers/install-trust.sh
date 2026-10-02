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
    # File names may contain spaces; copy via find -exec and give each anchor a safe name.
    find "$CERT_DIR" -type f \( -name '*.pem' -o -name '*.crt' -o -name '*.cer' \) -exec sh -c '
        for cert do
            name=$(basename "$cert" | tr -c "A-Za-z0-9._\n-" "_")
            cp "$cert" "/etc/pki/ca-trust/source/anchors/site-$name.crt"
        done' sh {} +
    count=$(find "$ANCHORS" -name 'site-*.crt' ! -name 'site-bootstrap.crt' | wc -l)
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
