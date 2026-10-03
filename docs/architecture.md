# Architecture

## Pulled (never built)

- `BASE_IMAGE`: EL9 runtime base.
- `PYTHON_BUILDER_IMAGE`, `NODE_BUILDER_IMAGE`, `DOCKER_CLI_IMAGE`: from `builder-images`.
- Elasticsearch and MongoDB vendor images (data-services repo).

## Built here from source

| Image | Stage | Contents |
|---|---|---|
| `SERVER_IMAGE` | `server` | API server, fileserver, async deletion worker (Python venv on the base) |
| `WEB_IMAGE` | `web` | Angular UI + report widgets compiled with the Node builder, served by nginx |
| `AGENT_IMAGE` | `agent` | clearml-agent services mode + Docker CLI guard |
| `TASK_IMAGE` | `task` | runtime for tasks the agent launches; contains the agent wheels |

- Python wheels resolved once into `wheelhouse/` with hashes; runtime installs with `--no-index`.
- CA bundle installed into every stage from `generated/trust/`.

## Services (Compose project `clearml`)

| Service | Image | Port | Notes |
|---|---|---|---|
| apiserver | server | 8008 | health `/debug.ping` |
| fileserver | server | 8081 | artifacts in `DATA_DIR` |
| async_delete | server | - | deletes files of deleted tasks |
| webserver | web | 8080 | proxies `/api` and `/files` |
| agent-services | agent | - | runs tasks as sibling containers via the host Docker socket |

## Data flow

- Browser → webserver (8080) → `/api` → apiserver; `/files` → fileserver.
- SDK and task containers → `CLEARML_API_URL`, `CLEARML_FILES_URL` directly.
- apiserver, fileserver, async_delete → MongoDB, Elasticsearch, Redis (data-services host).

## Secrets

- `generated/config/secure.conf`: generated once, reused; every upstream default credential replaced.
- Database passwords: from data-services `generated/clearml.env`.
- UI login (simple mode): `credentials.json` carries the webserver system credential; restrict network access to the web port.

## Offline behaviour

- No image pulls at runtime (`pull_policy: never`).
- Agent guard forces `--pull=never` and only `TASK_IMAGE`.
- UI update check redirected to a local 204; GitHub widget hidden.
