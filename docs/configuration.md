# Configuration (`.env`)

- Copy `.env.example` to `.env`, mode 600. Literal values, no shell expansion.
- `CHANGE_ME` anywhere makes the installer stop with `Configure <KEY> in .env`.
- `<nexus>` below means your registry or repository host.

## Images

| Key | Required | What to put | Example |
|---|---|---|---|
| `BASE_IMAGE` | yes | blessed EL9 base, runtime of all images | `<nexus>/mirror/almalinux:9` |
| `PYTHON_BUILDER_IMAGE` | yes | builder-images Python 3.11 + compilers | `<nexus>/builder-images/almalinux9-python:3.11` |
| `NODE_BUILDER_IMAGE` | yes | builder-images Node 24 + pnpm 10 | `<nexus>/builder-images/almalinux9-node:24` |
| `DOCKER_CLI_IMAGE` | if `ENABLE_AGENT=true` | builder-images Docker CLI | `<nexus>/builder-images/almalinux9-docker-cli:1` |
| `SERVER_IMAGE`, `WEB_IMAGE`, `AGENT_IMAGE`, `TASK_IMAGE` | yes | tags for the images built here, never pushed | `clearml/server:local-1` |
| `PNPM_VERSION` | no | pnpm spec, used only if the Node builder lacks pnpm | `10` |

Pulled images need a versioned tag (`:latest` rejected). They are pulled when missing.

## Registries and proxy

| Key | Required | What to put |
|---|---|---|
| `PIP_INDEX_URL` | yes | Nexus PyPI simple index, e.g. `https://<nexus>/repository/pypi/simple` |
| `NPM_REGISTRY` | yes | Nexus npm registry, e.g. `https://<nexus>/repository/npm/` |
| `ALLOWED_HOSTS` | no | comma-separated hostnames builds may contact; blank disables the check |
| `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` | no | proxy for build downloads; blank means none |
| `PIP_CONFIG_FILE`, `NPM_CONFIG_FILE` | no | files with index credentials, mounted as build secrets |
| `PIP_VERSION` | no | pip pinned in images and task containers (`25.2`) |
| `BUILD_NETWORK` | no | Docker build network (`default`) |

## Trust

| Key | Required | What to put |
|---|---|---|
| `TLS_CA_BUNDLE_URL` | if internal CAs are used | URL of the zip with `.pem`/`.crt`/`.cer` files; blank means system trust only |

- Bootstrap when the zip host uses the private CA: `config/tls-ca-bundle.pem` placed by hand (same file as inside the zip).
- Manual alternative: copy the zip to `config/tls-ca-bundle.zip`.

## Sources

| Key | Required | What to put |
|---|---|---|
| `ALLOW_SOURCE_DOWNLOADS` | no | `true` only where GitHub is reachable; default `false` |
| `STRICT_SOURCES` | no | `true` refuses archives whose tree differs from `sources.lock.json`; default `false` |

- Archives go in the repo root: `<component>-<version>.zip` or `<component>-<commit>.zip`.
- Components: `clearml-server`, `clearml-web`, `clearml-agent`, `clearml`.

## Databases

Copy these lines from data-services `generated/clearml.env`; replace, do not append.

| Key | From data-services |
|---|---|
| `MONGO_BACKEND_URI`, `MONGO_AUTH_URI` | yes |
| `ELASTICSEARCH_URLS`, `ELASTICSEARCH_USERNAME`, `ELASTICSEARCH_PASSWORD` | yes |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_TLS` | yes |

## URLs and ports

| Key | What to put |
|---|---|
| `CLEARML_API_URL` | `http://<this host>:8008`; used by SDK, agent and tasks |
| `CLEARML_WEB_URL` | `http://<this host>:8080` |
| `CLEARML_FILES_URL` | `http://<this host>:8081` |
| `API_PORT`, `WEB_PORT`, `FILES_PORT` | published ports (8008, 8080, 8081) |
| `BIND_ADDRESS` | `0.0.0.0` or a specific interface |

`<this host>` must resolve from browsers, SDK clients and task containers. Not `localhost` unless everything runs on this host.

## Storage

| Key | What to put |
|---|---|
| `DATA_DIR` | uploaded artifacts, absolute path, writable by you |
| `LOG_DIR` | server logs (contain DB URIs with passwords; keep private) |
| `AGENT_WORK_DIR` | absolute host path for the services agent |

## Agent

| Key | What to put |
|---|---|
| `ENABLE_AGENT` | `true` for the services queue; `false` skips agent and task images |
| `DOCKER_SOCKET` | `/var/run/docker.sock` |
| `CLEARML_AGENT_ACCESS_KEY`, `CLEARML_AGENT_SECRET_KEY` | leave blank; generated and wired automatically. Set both or neither |
