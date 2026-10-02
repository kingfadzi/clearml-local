# ClearML offline installer

Build ClearML application components from source ZIPs and deploy against network-hosted MongoDB, Elasticsearch and Redis. Runtime images use an internally mirrored AlmaLinux 9 base or UBI 9 base. Python 3.11 and Node 24/pnpm 10 builders are configurable.

**Implementation status:** local tests and Compose schema checks are available and passing. No source downloads, container builds, live database tests, UBI validation or GitLab publication were possible in the development session: shell DNS and Docker access were blocked. Treat the image/package versions as initial candidates until the acceptance matrix below passes. No claim of a validated offline deployment is made yet.

## Repository layout

- This directory: ClearML installer.
- `repositories/data-services/`: independent repository content for the requested GitLab `staging/data-services` project; custom EL9 database images and Compose deployment.
- `repositories/builder-images-additions/`: additions for the existing `staging/builder-images` repository. Existing builders are preserved; the new entrypoint builds only the offline EL9 images.

The sibling builder checkout was read-only in this session. Transfer its additions through a normal reviewed change. Creation/publishing of the remote data-services repository remains outstanding because GitLab was unreachable.

## Prerequisites and site settings

Use Linux with Python 3.11+, Docker Engine, BuildKit and Compose v2 (`--wait` support). Host engine installation is outside this installer. Use a preinstalled BuildKit implementation: no external Dockerfile frontend image is requested. The invoking user needs Docker access.

Copy `.env.example` to `.env`. Values are literal, including `$`; do not use shell substitutions or `${VARIABLE}` references. The parser never sources this file. CLI environment is read from the selected file only (`--env path`). Keep it mode 600. Fill in internal registry, package mirrors, database connection details, and browser-accessible URLs. Paths are relative to this repository unless absolute.

Copy `config/yum.repo.example` to `config/yum.repo` and supply `config/ca.pem` containing your trusted site CA certificates. Use your internal EL9 repositories, including vendor RPM repositories for databases. UBI requires the appropriate UBI/RHEL package repositories and signing keys; changing the base alone does not supply missing packages. Full AlmaLinux 9 / UBI 9 images with `dnf` or `microdnf` and CA tooling are expected; scratch/micro images are unsupported.

`ALLOWED_HOSTS` contains exact registry/repository hostnames. Preload all base and builder images; builds check that they exist locally. Set digest references after qualification. `PIP_CONFIG_FILE` and `NPM_CONFIG_FILE` optionally point to secret files for authentication. They are BuildKit secret mounts; do not put credentials in URLs. Scoped npm registries must also be internal. The YUM repo file is mounted as a secret and removed from the image after RPM installation.

**Network enforcement:** run builds and containers behind a host/network firewall allowing only your DNS, internal package/image repositories, Nexus and the configured application/data services. `BUILD_NETWORK` selects Docker's build network mode; it does not create a firewall. Repository validation rejects common public fallback sources, but arbitrary dependency install scripts and HTTP redirects require actual egress enforcement. Internal proxy caches must be pre-populated or disconnected from upstream. Browser network access must be checked separately.

## Build and install

1. Build the missing EL9 builders using `repositories/builder-images-additions/build-offline` (see its README). Load or publish them internally.
2. Configure and start `repositories/data-services/` if using the provided database stack. Copy the values from its private `generated/clearml.env` into the corresponding existing keys in ClearML `.env` (do not append duplicate keys).
3. Put source directories named `clearml-server`, `clearml-web`, `clearml-agent`, and `clearml` directly in this root, or put one `<name>.zip` / `<name>-<revision>.zip` per component here.
4. Run the following:

```sh
./clearmlctl prepare
./clearmlctl dependencies
./clearmlctl build
./clearmlctl configure
./clearmlctl preflight
./clearmlctl install
./clearmlctl verify
./clearmlctl status
```

`prepare` alone can download missing GitHub archives when `ALLOW_SOURCE_DOWNLOADS=true`. Keep it false in the air gap. Existing root directories or ZIPs are reused without network access, even when downloads are enabled. Multiple matching ZIPs fail rather than choose arbitrarily. Downloaded refs are resolved to commit IDs before downloading ZIPs; no Git commands are used. `sources.json` initially requests upstream master because no release combination has yet been qualified. Before release, replace those selectors with your tested tags/commits and preserve `sources.lock.json` in the release bundle. Local inputs are trusted on first import and then checked using tree/archive hashes. Their provenance needs separate review. Submodules fail with a clear error rather than silently producing incomplete builds.

`dependencies` resolves the ClearML SDK/agent from local source and third-party Python packages through internal PyPI, producing `wheelhouse/requirements.lock` with wheel hashes. It refuses to replace an existing wheelhouse. `build` reuses those wheels without Python package downloads. The UI uses the source's frozen pnpm lock and internal npm. Preserve the wheelhouse and source lock together; changing sources requires explicit dependency requalification. Never remove locks as an automatic retry.

The server image runs API, file server and async deletion worker as separate services. The web image builds both webapp and widgets. The agent and task images contain the source-built SDK and agent. A root startup phase reads private mounted configuration and initializes ownership, then server/web processes drop to UID 1000. Installation changes ownership of the configured data/log directory itself to UID 1000; use dedicated directories. Existing nested data must already have suitable ownership. SELinux shared bind mounts use `:z`.

Generated configuration contains secrets and is not included in portable bundles. Keep `generated/config/secure.conf` backed up: it contains persistent token signing keys and system/agent credentials. Do not delete generated credentials when upgrading. This initial deployment retains upstream's default web login behavior; customize ClearML authentication before exposing it beyond the intended lab/network.

## Services agent

The agent requires the host Docker socket and a locally available Docker CLI RPM. `DOCKER_CLI_PACKAGE` selects that package. Set `AGENT_WORK_DIR` to an absolute, dedicated host path. Task containers reach the browser/API/file URLs from `.env`, so these must resolve from the host network used by task containers.

A Docker CLI guard permits only the configured `TASK_IMAGE` for task creation and rejects pulls. That image must be preloaded. Bootstrap downloads, OpenCV OS installation, PyTorch alternate indexes and default image rules are disabled in generated agent configuration. Internal pip settings are passed to task containers. Submit standalone-code tasks or prepackaged code; Git repository tasks are unsupported. A task needing another image must first have it qualified and set as `TASK_IMAGE`. The guard is operational protection, not a sandbox against malicious code with Docker socket access; host egress policy remains required.

## Transfer, verification and upgrades

`./clearmlctl bundle` saves runtime images, installer, source and Python wheels to `dist/`, with SHA-256 checksums. It excludes `.env`, generated configuration, credentials and database data. Transfer site secrets/CA/repository settings separately. On the target, verify checksums, extract `installer.tar.gz`, place `images.tar` and `checksums.json` together, then use `./clearmlctl load --archive /path/images.tar`, configure and install. Base/builder images are needed only if rebuilding; transfer those separately. npm artifacts must remain available in the target internal registry for rebuilding.

Acceptance matrix (required for both AlmaLinux 9 and UBI 9):

- Build with public egress blocked and empty package caches; verify internal mirrors serve all artifacts, including RPM signing keys and build dependencies.
- Run `preflight` and `verify` against the chosen external database versions; these exercise authenticated clients. They report versions but do not claim arbitrary database versions are supported.
- Run `scripts/smoke.py` with the built SDK and an authenticated ClearML configuration to create an experiment, log metrics, and round-trip an artifact. Check it in the UI.
- Enqueue a standalone services task using `TASK_IMAGE`; verify completion, then attempt a public image and confirm rejection.
- Delete a test artifact/task through the UI and verify the async worker deletes its stored file.
- Check browser developer tools for failed/external requests (including fonts, charts, help/video embeds); automated browser qualification remains outstanding.
- Restart both stacks and verify records and artifacts persist. Repeat install and confirm credentials do not change.
- Enable database TLS with trusted certificates and repeat client checks; test bad credentials and untrusted CA rejection.

Run local checks with `python3 -m unittest discover -s tests -v`. They use temporary source fixtures and need no daemon or external services. Back up external databases, file storage, and generated signing credentials before an upgrade; this installer does not automate destructive migrations or database rollback. Keep the previous image bundle until the new version is accepted.
