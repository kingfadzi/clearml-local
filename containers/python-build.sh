#!/bin/sh
set -eu
export PIP_CONFIG_FILE=/dev/null
if [ -f /run/secrets/pip_config ]; then export PIP_CONFIG_FILE=/run/secrets/pip_config; fi
export PIP_EXTRA_INDEX_URL= PIP_FIND_LINKS= PIP_INDEX_URL
# Pinned build tooling; the EL9 pip cannot build setup.py projects without wheel.
python3.11 -m pip install --upgrade "pip==${PIP_VERSION:-25.2}" "setuptools==${SETUPTOOLS_VERSION:-80.9.0}" "wheel==${WHEEL_VERSION:-0.45.1}"
# ClearML packages are always built from the staged sources.
mkdir -p /wheelhouse
python3.11 -m pip wheel --no-deps -w /wheelhouse /build/clearml /build/clearml-agent
python3.11 -m pip wheel --find-links=/wheelhouse -w /wheelhouse -r /build/clearml-server/apiserver/requirements.txt /wheelhouse/clearml-*.whl /wheelhouse/clearml_agent-*.whl
python3.11 - <<'PY'
from pathlib import Path
from hashlib import sha256
from zipfile import ZipFile
from email.parser import BytesParser
entries = {}
for path in Path('/wheelhouse').glob('*.whl'):
    with ZipFile(path) as z:
        metadata = [n for n in z.namelist() if n.endswith('.dist-info/METADATA')]
        m = BytesParser().parsebytes(z.read(metadata[0]))
    name = m['Name'].lower().replace('_', '-')
    if name in entries:
        raise SystemExit('Multiple wheel versions resolved: ' + name)
    entries[name] = f"{m['Name']}=={m['Version']} --hash=sha256:{sha256(path.read_bytes()).hexdigest()}"
Path('/wheelhouse/requirements.lock').write_text('\n'.join(entries[k] for k in sorted(entries)) + '\n')
PY
