# Agent handoff: offline ClearML installer

Last updated: 2026-10-01. Workspace: `/home/fadzi/tools/clearML`.

## Problem statement and authorized outcome

The user wants a working, end-to-end-tested offline installer for ClearML Server, published to their GitLab. They explicitly authorized implementation, pushing to GitLab, and end-to-end testing. Work is incomplete: application code and deployment tooling have been written, but no application images have been built or deployed and nothing has been pushed.

Requirements agreed with the user:

- Build all ClearML application components from source: API, file server, web UI and report widgets, asynchronous deletion worker, services agent, and required ClearML SDK/agent Python packages.
- Obtain GitHub source using ZIP archives, never `git clone`. Reuse source already present in the project root; download only when absent. Downloads belong in explicit preparation outside the offline build/install workflow.
- ClearML connects to network-hosted Elasticsearch, MongoDB and Redis. Their endpoints, authentication and applicable TLS settings are configurable through `.env`.
- A separate new repository named `data-services` supplies a simple single-host Docker Compose stack for those three databases. ClearML itself must not deploy database containers.
- The user explicitly chose custom AlmaLinux 9 / UBI 9 database containers over mirrored upstream database images.
- Runtime base images are configurable: AlmaLinux 9 in the lab, RHEL UBI 9 in the air gap. Builder images are independently configurable EL9 Python 3.11 and Node 24 with pnpm 10.
- Inspect and extend the existing builder repository, adding missing images: `https://gitlab01.butterflycluster.com/staging/builder-images`.
- Builds/installations may access only approved internal YUM, PyPI, npm, image repositories and Nexus. No public fallbacks, public image pulls or automatic update downloads.
- Database vendor RPMs are allowed; the accepted plan does not require compiling database engines from source. Third-party application dependencies can come from internal package repositories.
- Docker Compose is the initial deployment target. Database clustering/HA and automatic destructive migrations are outside the initial scope.

## Current implementation and repository state

### ClearML installer

The workspace root holds the installer. Start with `README.md`, `.env.example`, `clearmlctl`, and `containers/Containerfile`.

Implemented code paths:

- `scripts/sources.py`: root directory/ZIP reuse, explicit optional GitHub archive downloads, commit resolution before downloading, archive/tree hashes, safe ZIP extraction, changed-source rejection. No Git clone commands. Submodule-bearing sources currently fail for explicit review rather than being resolved.
- `sources.json`: four source repositories (`clearml-server`, `clearml-web`, `clearml-agent`, `clearml`). **All currently select `master`; no compatible release set has been qualified.** First preparation creates `sources.lock.json`; there is no actual source lock or source checkout yet.
- `scripts/installer.py`: `prepare`, `dependencies`, `build`, `configure`, `preflight`, `install`, `status`, `verify`, `bundle`, `load` commands.
- `scripts/common.py`: literal `.env` parsing, private config writes, Compose interpolation escaping, internal repository/image validation, BuildKit and Compose helpers.
- `scripts/dependency_policy.py`: checks known dependency URL/Git bypasses. This is not comprehensive enforcement against arbitrary install scripts or redirects.
- Multi-stage image definitions for source-built Python packages, web UI/widgets, server, services agent and task runtime.
- `dependencies` resolves Python packages into a wheelhouse and hash lock. Subsequent builds reuse the wheelhouse and validate that its source lock matches.
- `scripts/render.py`: generates private ClearML configuration, stable system/agent secrets, frontend configuration, and Compose JSON with five services: API, fileserver, webserver, async deletion, agent-services.
- Root startup reads private configuration and initializes ownership, then API/fileserver/worker and nginx drop to UID 1000.
- `scripts/docker-policy.py`: agent Docker CLI guard rejects pulls and task images other than `TASK_IMAGE`. This is operational protection, not a security boundary against Docker-socket users.
- `scripts/check-databases.py`: authenticated database-client checks executed inside the server image.
- `scripts/smoke.py`: SDK experiment/metric/artifact round-trip test. Written, **not executed against ClearML**.
- Transfer bundles export images/source/wheels and checksums while excluding site credentials and data.

The root `.git` is an empty read-only directory supplied by this session. `git status` reports “not a git repository.” Root installer changes are **not committed**. Do not delete or modify protected metadata to work around restrictions. In a properly authorized writable environment, initialize the actual installer repository or import these files into its existing checkout after checking GitLab. The user did not specify the installer GitLab project path; discover whether one already exists before choosing/creating it.

### New data-services repository

Location: `repositories/data-services/`.

This is a real local Git repository on branch `main`, with a clean working tree at last inspection. Initial commit:

```text
dabe82f165600da2910e31f4435f43702551265b
Add offline EL9 Elasticsearch MongoDB and Redis deployment
```

Configured origin: `https://gitlab01.butterflycluster.com/staging/data-services.git`.

**The remote project has not been created or verified; the configured origin is only the intended destination. The commit has not been pushed.**

Implemented:

- `datactl`: configure/build/preflight/install/status/verify/bundle/load.
- Custom EL9 RPM-based Elasticsearch, MongoDB and Redis image targets.
- Generated Compose JSON with named persistent volumes, health checks, configurable ports, authentication and optional TLS.
- Stable generated credentials in private `generated/credentials.json` and exported ClearML connection values in `generated/clearml.env`.
- MongoDB initializes users on loopback before network startup; existing data without an initialization marker fails closed. Interrupted initialization needs operator recovery, never automatic data deletion.
- TLS certificates are supplied by the site and copied to service-readable paths at startup.
- Initial package candidates: Elasticsearch 8.19.9, MongoDB 8.0.15, Redis 8.2.3; mongosh 2.5.8 is independently configurable. **These are not a tested release combination on these custom images.** Confirm exact RPM availability, dependencies, signing keys and vendor service-account assumptions.

### Existing builder-images repository

Existing checkout: `/home/fadzi/tools/builder-images` (read-only in this session).

Inspected facts from that checkout:

- Python 3.11 builder uses AlmaLinux 8.
- Node 22 builder uses AlmaLinux 9 and public NodeSource/npm downloads.
- No Node 24 definition was present.
- `build-and-push.sh` and `builder-images.yml` exist; no `.gitlab-ci.yml` was present in the inspected checkout. Inspect the remote before assuming its CI state.

Prepared additions: `repositories/builder-images-additions/`.

- Python 3.11 EL9 builder with native compilation tools/headers.
- Node 24 EL9 builder with configurable node/npm RPM specs and pinned pnpm 10 (initial pnpm candidate: 10.11.0).
- Internal YUM/npm configuration, CA support and secret mounts.
- `build-offline` builds only these additions; `--push` publishes configured images.
- `offline-builders.yml` supplies additional GitLab variable names.

Copy this entire additions directory under `offline/` in the builder repository to avoid overwriting existing top-level files. Integrate it with the repository's real publishing process. Original builder files have not been modified, committed or pushed. `builder-images.original.yml` is a reference copy, not a new authoritative configuration.

## Verified evidence and access blockers

Most recent local test run:

```sh
python3 -m unittest discover -s tests -q
# Ran 23 tests ... OK
```

Coverage includes source reuse without downloading, offline missing-source failure, source changes, unsafe ZIP members, ambiguous archives, `.env` parsing, internal-source/image checks, stable/private credentials, database separation, missing TLS inputs, Docker task-image restrictions, and Compose schema validation. Compose validation uses the CLI and does not require the daemon. Python compilation and shell syntax checks also passed in the implementation turn.

The latest fix attaches Elasticsearch CA/TLS options only to HTTPS nodes, preserves URL path prefixes, and rejects query strings/fragments. Previously plain HTTP endpoints would receive invalid TLS options. Regression tests cover this correction. This root change is not committed because root Git metadata is unavailable.

**No end-to-end test has run. No Docker image has been built. No source ZIP has been downloaded. No real site `.env`, CA bundle, or YUM repo file has been supplied.** Example registry URLs, package paths and DNS names must not be treated as discovered working infrastructure.

Observed blockers on the latest retry:

- `docker info`: connecting to `/var/run/docker.sock` returns `operation not permitted`.
- `getent hosts` returned no addresses for GitLab, GitHub, Nexus or the image registry.
- `curl --head https://gitlab01.butterflycluster.com`: exit 6, `Could not resolve host`.
- Root `.git` and sibling builder checkout are read-only.
- This session disables sandbox/rules/skill approval escalation. Repeated user authorization does not change those enforced permissions.

Environment-variable names for existing GitLab credentials were observed, but credentials were not printed or copied into project files. Use authorized environment credentials in the next session without exposing them in logs or URLs. Do not disable TLS verification as a permanent solution; use the site's trust configuration.

The next agent needs a session with working internal DNS/network, authorized Docker access, and writable repository metadata/checkouts. Do not attempt to bypass current restrictions with alternate sockets, IP routing or credentials.

## Remaining work, in execution order

1. **Verify access and discover real site configuration.** Check Docker Engine/Compose/BuildKit, internal GitLab/registry/Nexus connectivity, CPU architecture, registry authentication, CA certificates, internal repository URLs and existing projects. Inspect applicable AGENTS instructions and remote builder history. Preserve unrelated changes.
2. **Finish repository setup.** Create/verify `staging/data-services`, establish the intended ClearML installer project, and bring the prepared builder additions into the real builder checkout. The user has authorized pushes; further generic confirmation is unnecessary.
3. **Select and stage a compatible source set.** Download ZIPs only when missing from the root, resolve immutable revisions, and qualify server/UI/SDK/agent compatibility. Preserve source and dependency locks. Handle any actual submodules or omitted generated assets explicitly. Current `master` selectors are provisional, not a release pin.
4. **Build the builder images.** Confirm internal RPMs for Node 24, npm, Python 3.11 and native headers. Ensure pnpm 10 supports the chosen web lockfile. Build with public egress blocked, validate versions, publish internally and record immutable image digests.
5. **Build and start data-services.** Verify vendor package versions/users/directories, initialization, permissions, Elasticsearch bootstrap authentication and `vm.max_map_count`, Redis AOF, and MongoDB auth. Correct issues revealed by real builds/startup. Export its connection settings into ClearML `.env` without duplicate keys.
6. **Build ClearML and fix actual integration issues.** Run prepare/dependency/build commands against internal mirrors. Check Python wheel reproducibility/ABI, web build outputs/widgets, app entrypoints/config schemas, file/API authentication, API error generation and readiness. The existing code is an unqualified first implementation; review it rather than assuming tests prove runtime correctness.
7. **Validate the services agent carefully.** Check actual CLI flags and Docker command shapes for the pinned agent. Verify no bootstrap script reinstalls the SDK/agent from another package version or downloads public artifacts. Confirm task env/CA propagation, host mount mapping, standalone-code jobs without Git, services queue processing, and rejected public pulls. The CLI guard may need compatibility fixes. Do not weaken offline constraints just to make a task pass.
8. **Run real end-to-end acceptance.** See the matrix below. Add automated integration tests where practical, retaining concrete logs/results and image/source identifiers. Local fixture tests must not be reported as deployment tests.
9. **Repeat on UBI 9.** Change base/builder/repository settings as appropriate, validate package availability and native libraries, and rerun acceptance. Do not claim portability based on configurable `FROM` alone.
10. **Publish and document results.** Commit all repositories, push to GitLab, verify remote commit IDs and any CI result, publish versioned images, and export/test transfer bundles. Update READMEs to distinguish verified behavior from remaining limitations. Report the actual GitLab links, revisions, image digests, tests and unresolved issues to the user.

## Required end-to-end acceptance

Run with public egress blocked and internal mirrors already populated. `BUILD_NETWORK` merely selects a Docker build network mode; the current code does not provision a firewall. Package/source validation cannot prevent arbitrary install-script traffic or HTTP redirects by itself.

- Build from staged ZIPs and internal repositories using clean caches; verify only allowed services are contacted.
- Install the independent data-services stack and ClearML stack. Confirm ClearML Compose has no database containers.
- Verify authenticated DB connections and server/UI/file-server readiness.
- Log in through the UI; create an experiment, record metrics and round-trip an uploaded artifact using the source-built SDK.
- Complete a standalone services-agent task using the approved EL9 task image. Confirm an unapproved/public image fails without pulling.
- Delete test data and confirm asynchronous file deletion works.
- Check browser network traffic for external fonts/scripts/charts/telemetry/video requests. Current hide-update/survey settings are not proof of browser offline operation.
- Restart/reinstall both stacks; confirm credentials, experiments, artifacts and database contents persist.
- Enable trusted TLS and repeat. Verify incorrect credentials and untrusted certificates are rejected.
- Transfer runtime bundles to a clean target, verify checksums, load images without pulling, and install using separately supplied site configuration.
- Repeat the relevant matrix for AlmaLinux 9 and UBI 9, recording failures and fixes.

`README.md` contains the command sequence and operational details; each prepared repository has its own README. Keep site secrets and database volumes out of Git, public logs and portable source bundles. Preserve generated signing credentials and database backups before upgrades. There is no completed tested release to roll back to yet.
