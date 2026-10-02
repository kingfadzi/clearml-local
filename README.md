# ClearML offline installer

- Builds ClearML Server (API, fileserver, web UI, widgets, async deletion worker), the services agent and the SDK/agent Python packages from pinned GitHub source ZIPs.
- Deploys with Docker Compose against network-hosted MongoDB, Elasticsearch and Redis. No database containers in this stack.
- Companion database stack: the `data-services` repository (same group).
- One blessed EL9 base image (`BASE_IMAGE`) provides the runtime and, via its repositories, the Python and Node build toolchains. Verified on AlmaLinux 9; see "Verified" below for UBI 9.

## Layout

- `clearmlctl`: CLI wrapper for `scripts/installer.py`.
- `scripts/`: installer, source staging, config renderer, dependency policy, Docker CLI guard for the agent, acceptance scripts.
- `containers/Containerfile`: all image stages (python-resolve, python-build, web-build, python-runtime, server, agent, task, web).
- `sources.json`: pinned source refs. `sources.lock.json` is written by `prepare` and must ship with a release.
- `wheelhouse/`: resolved Python wheels plus `requirements.lock` with hashes. Created by `dependencies`.
- `tests/`: unit tests, no daemon needed. Run `python3 -m unittest discover -s tests -q`.

## Pinned sources

- clearml-server v2.4.0, clearml-web v2.5, clearml v2.1.12, clearml-agent v3.0.3.
- Downloads use GitHub ZIP archives resolved to a commit; never `git clone`.
- Existing root directories or `<name>-<hex revision>.zip` files are reused without network access.
- Symlinks inside an archive are kept only when they stay inside the source root.

## Prerequisites

- Linux host with Docker Engine, BuildKit and Compose v2 (`--wait`). Python 3.11+.
- `vm.max_map_count >= 262144` on the host that runs the database stack.
- `BASE_IMAGE` is pulled from its registry when not present locally. Tag must be versioned (`:latest` is rejected) and, when `ALLOWED_HOSTS` is set, from a listed registry.
- Its repositories must provide `python3.11`, `python3.11-devel`, `gcc`, `nginx`, `shadow-utils`, `util-linux-core`, the `NODE_PACKAGE` Node.js stream (22.12+) and `DOCKER_CLI_PACKAGE`.
- `TLS_CA_BUNDLE_URL`: URL of a zip holding the internally signed CA certificates (`.pem`/`.crt`/`.cer`, any folder layout). Blank means no private CA is required. `trust` or `build` downloads it to `config/tls-ca-bundle.zip`; every image stage installs it into OS trust.
- Bootstrap: if the download host itself uses the private CA, place the CA by hand as `config/tls-ca-bundle.pem` (the same file is inside the zip). It is used to verify the download and is installed into the images as well.
- Download failure: an already present `config/tls-ca-bundle.zip` is reused with a warning; otherwise the command stops and tells you to place the PEM or the zip. `./clearmlctl trust` stages and validates without building.

## Configuration

- Copy `.env.example` to `.env`. Values are literal; no shell expansion. Keep it mode 600.
- `ALLOWED_HOSTS`: optional allowlist of hostnames builds may contact (registries, package indexes). Blank disables the check. The only network switch in the installer.
- `PIP_INDEX_URL`, `NPM_REGISTRY`: package indexes. Public or mirrored, both must be listed in `ALLOWED_HOSTS`.
- `NODE_PACKAGE`: Node.js RPM spec installed in the build stage (default `@nodejs:22/common`). `PNPM_VERSION`: pnpm spec installed from `NPM_REGISTRY` (default `10`, the major the web lockfile needs).
- `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`: proxy for build-time downloads. Blank means no proxy. Passed to every build step in both letter cases.
- `PIP_VERSION`: pip installed in every runtime venv and pinned for task containers, so the agent's in-container pip upgrade is a no-op.
- Database keys: copy from the data-services `generated/clearml.env` into the matching keys (replace, do not append).
- `CLEARML_*_URL`: browser-reachable URLs. Task containers also use them.
- `ENABLE_AGENT`, `TASK_IMAGE`, `AGENT_WORK_DIR` (absolute host path), `DOCKER_SOCKET`, `DOCKER_CLI_PACKAGE`.

## Build and install

```sh
./clearmlctl prepare        # stage sources, write sources.lock.json
./clearmlctl trust          # download/validate the CA bundle into generated/trust (optional, build does it too)
./clearmlctl dependencies   # resolve wheels into wheelhouse/ (refuses to overwrite)
./clearmlctl build          # server, web, agent, task images
./clearmlctl configure      # generated/ (secrets, mode 600)
./clearmlctl preflight      # compose validation + authenticated DB checks inside the server image
./clearmlctl install
./clearmlctl verify
./clearmlctl status
```

- `--env <file>` selects another env file, for example a UBI 9 variant with different image tags.
- `generated/config/secure.conf` holds token signing secrets and every system credential. Back it up; it is reused on re-render.
- Every upstream default credential (apiserver, fileserver, webserver, tests) is replaced by a generated one.
- The UI receives the webserver credential through `credentials.json` (simple login mode, as upstream). Anyone reaching the web port can create users; put the UI behind your access control.
- Elasticsearch TLS options are client arguments; all nodes of a cluster must share one scheme.
- API server logs print database URIs including passwords (upstream behaviour). Keep `LOG_DIR` private.

## Services agent

- Runs `clearml-agent daemon --services-mode --cpu-only --queue services --create-queue --docker TASK_IMAGE`.
- `/usr/local/bin/docker` in the agent image is a guard: only `TASK_IMAGE` may be run, `--pull=never` is forced, pulls are refused, unknown flags fail closed. Operational protection only, not a sandbox.
- Task containers reinstall the agent from `/opt/wheels` inside the task image with `--no-index`; pip is already at `PIP_VERSION`. No downloads occur for standalone tasks.
- Task containers skip venv creation (`CLEARML_AGENT_SKIP_PIP_VENV_INSTALL`) and requirement installation (`CLEARML_AGENT_SKIP_PYTHON_ENV_INSTALL`). Submit standalone scripts; Git repository tasks are unsupported.
- `CLEARML_AGENT_DOCKER_HOST_MOUNT` maps `AGENT_WORK_DIR` to `/root/.clearml` so sibling containers can mount the agent's files.

## Web UI offline behaviour

- `configuration.json`: `hideUpdateNotice`, `showSurvey=false`, `GTM_ID=null`, `displayTips=false`, `enterpriseServer=true` (hides the GitHub star widget, which calls api.github.com).
- The UI's hardcoded update check (`updates.clear.ml`) is rewritten at image build time to a local nginx endpoint returning 204.
- nginx resolves `apiserver` and `fileserver` at request time; a restarting backend does not stop the UI.
- Help links and video embeds still reference public hosts; they load only on click.

## Acceptance scripts

- `scripts/smoke.py`: SDK experiment, scalar and artifact round trip. Run inside the task image with a `clearml.conf`.
- `scripts/services-task.py --image IMG --expect completed|failed`: enqueue a standalone task on the services queue and wait.
- `scripts/browser-check.py WEB_URL ALLOWED_HOST`: headless Chromium login and page visits; fails if any other host is contacted. Runs in a Playwright container.
- `check-databases` (inside the server image, via `preflight`/`verify`): authenticated MongoDB, Elasticsearch and Redis clients.

## Transfer

- `./clearmlctl bundle`: `dist/images.tar`, `dist/installer.tar.gz` (installer, sources, wheelhouse), `dist/checksums.json`.
- Excluded: `.env`, `generated/`, `config/`, data volumes. Transfer site configuration separately.
- Target: extract `installer.tar.gz`, place `images.tar` and `checksums.json` together, `./clearmlctl load --archive <path>`. A checksum mismatch refuses the archive.

## Verified (2026-10-02, lab)

- Lab used public PyPI and npm through `ALLOWED_HOSTS`; the lab base image carried the vendor YUM repos; the lab registry held base, builder and output images.
- Built from pinned ZIPs; all four images built on AlmaLinux 9 from the single base image.
- `preflight` and `verify` passed against data-services (MongoDB 8.0.15, Elasticsearch 8.19.9, Redis 8.2.10) in plain and TLS modes.
- Wrong passwords and an untrusted CA were rejected for all three databases.
- SDK smoke test passed from the source-built task image; artifact landed in `DATA_DIR`; async deletion removed it after task deletion.
- Services task with `TASK_IMAGE` completed with no downloads; a task requesting a public image failed under the guard with no pull.
- Headless browser: login, dashboard, projects, workers and settings pages loaded; only the ClearML host was contacted.
- Restart of both stacks and reinstall kept tasks, logs and generated secrets.
- Bundle exported, loaded in a clean directory, tampered checksum refused.
- UBI 9: ClearML and data-services images built from `ubi9/ubi:9.6` with a UBI repo file. Same acceptance passed: preflight, verify, SDK smoke, services task, browser check; database images ran on the existing volumes with all data visible.

## Limitations

- No firewall is provisioned. `BUILD_NETWORK` only selects a Docker build network. Enforce egress on the host.
- Dependency policy checks declared sources (requirements, lockfiles, npmrc); it cannot stop arbitrary install scripts.
- Changing the CA bundle requires an image rebuild (trust is installed at build time).
- Rotating database credentials or TLS files needs container restarts; this installer does not automate rotation or destructive migrations.
- Upstream simple login mode has no password. Restrict network access to the UI or configure fixed users yourself.
