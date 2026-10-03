# Install runbook

Order: data-services first, then ClearML. All commands run from the repo root named in each step.

## 0. Prerequisites

- Two hosts (or one): data-services host (bash, coreutils, docker), ClearML host (Python 3.11, docker, Compose v2).
- Registry (Nexus) holding: blessed EL9 base, `builder-images/almalinux9-python:3.11`, `builder-images/almalinux9-node:24`, `builder-images/almalinux9-docker-cli:1`, `elasticsearch/elasticsearch:8.17.2`, `library/mongo:8.0.11`.
- Nexus PyPI and npm proxies.
- CA bundle zip URL (internal CAs). Optional if everything is signed by public CAs.
- Source zips from GitHub Releases, downloaded elsewhere: `clearml-server-2.4.0.zip`, `clearml-web-2.5.zip`, `clearml-agent-3.0.3.zip`, `clearml-2.1.12.zip`.

## 1. data-services

```sh
git clone <gitlab>/staging/data-services.git
cd data-services
cp .env.example .env && chmod 600 .env
```

Edit `.env` (details: [configuration](configuration.md) in that repo):

```sh
ELASTIC_IMAGE=<nexus>/elasticsearch/elasticsearch:8.17.2
MONGO_IMAGE=<nexus>/library/mongo:8.0.11
BASE_IMAGE=<nexus>/mirror/almalinux:9
DATA_HOST=<this host's hostname or IP, reachable from the ClearML host>
```

Optional TLS: `TLS_ENABLED=true` and put `ca.pem`, `server.crt`, `server.key`, `mongo.pem` in `config/tls/`.

```sh
./datactl install
./datactl verify
```

Expected:

```
elasticsearch: healthy
mongo: healthy
redis: healthy
```

Keep this output for step 2:

```sh
cat generated/clearml.env
```

## 2. ClearML

```sh
git clone <gitlab>/staging/clearml-local.git
cd clearml-local
cp .env.example .env && chmod 600 .env
```

Place the four source zips in the repo root (any `<component>-<version>.zip` name).

Edit `.env`:

```sh
BASE_IMAGE=<nexus>/mirror/almalinux:9
PYTHON_BUILDER_IMAGE=<nexus>/builder-images/almalinux9-python:3.11
NODE_BUILDER_IMAGE=<nexus>/builder-images/almalinux9-node:24
DOCKER_CLI_IMAGE=<nexus>/builder-images/almalinux9-docker-cli:1
PIP_INDEX_URL=https://<nexus>/repository/pypi/simple
NPM_REGISTRY=https://<nexus>/repository/npm/
TLS_CA_BUNDLE_URL=https://<host>/tls-ca-bundle.zip    # blank if no private CA
ALLOWED_HOSTS=                                        # blank, or exact hostnames to allow
CLEARML_API_URL=http://<this host>:8008
CLEARML_WEB_URL=http://<this host>:8080
CLEARML_FILES_URL=http://<this host>:8081
DATA_DIR=/srv/clearml/data
LOG_DIR=/srv/clearml/log
AGENT_WORK_DIR=/srv/clearml/agent
```

Paste the lines from data-services `generated/clearml.env` over the matching keys (`MONGO_*`, `ELASTICSEARCH_*`, `REDIS_*`).

If the CA zip host itself uses the private CA:

```sh
cp /path/to/ca.pem config/tls-ca-bundle.pem
```

Create the directories:

```sh
mkdir -p /srv/clearml/data /srv/clearml/log /srv/clearml/agent
```

Run:

```sh
./clearmlctl install
./clearmlctl verify
```

Expected at the end:

```
CLEARML_API_URL: healthy
CLEARML_WEB_URL: healthy
CLEARML_FILES_URL: healthy
```

First run takes 15 to 25 minutes (wheel resolution, web build).

## 3. First login

- Open `CLEARML_WEB_URL`, enter any name, click START.
- Example projects appear on first start of an empty database. On an existing one: `./clearmlctl examples`.

## 4. SDK credentials

- UI: Settings, Workspace, Create new credentials. Copy the block.
- On the client: `pip install clearml`, `clearml-init`, paste.
- `api_server` in the block must be `CLEARML_API_URL`. If `clearml-init` reports "could not verify credentials", see [troubleshooting](troubleshooting.md).

## 5. Optional checks

```sh
./clearmlctl status
docker logs clearml-apiserver-1 --tail 50
```

Acceptance scripts: see [operations](operations.md).
