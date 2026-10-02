# Handoff: offline ClearML installer

Last updated: 2026-10-02. Workspace: `/home/fadzi/tools/clearML`.

## State

- All three deliverables are published and end-to-end tested in the lab.
- Installer: `staging/clearml-local` (this directory, branch `main`).
- Database stack: `staging/data-services` (checkout at `repositories/data-services`, ignored by the installer repo).
- Builder images: `staging/builder-images` `main`, checkout at `/home/fadzi/tools/builder-images`. Added `almalinux9-node:24` (pnpm 10.11.0) and `almalinux9-python:3.11`, both pushed to the lab registry.
- `README.md` in each repository lists verified behaviour and limitations. Lab `.env`, `config/ca.pem`, `config/yum*.repo`, `.env.ubi9` and TLS files are untracked site configuration on this host.

## Lab decisions

- Public PyPI, npm and vendor YUM repos are used in the lab through `ALLOWED_HOSTS`. Air gap: point the same keys at mirrors.
- `YUM_REPO_FILE` is optional; the lab uses one only for `docker-ce-cli` and the database vendor repos.
- Redis 8.2 for EL9 comes from Remi's modular repo (`@redis:remi-8.2`); Redis's own repo has no EL9 Redis 8 RPM.
- UBI 9 variant: `.env.ubi9` with `mirror/ubi9:9.6` as base and a UBI repo file. Image tags end in `-ubi9`.

## Acceptance evidence (lab host, 2026-10-02)

- Unit tests: 31 passing.
- AlmaLinux 9 and UBI 9 ClearML images: preflight, verify, SDK smoke, services task (no downloads), public-image task rejected without pull, headless browser contacted only the ClearML host.
- Data-services: plain and TLS modes verified; wrong passwords and untrusted CA rejected.
- Restart and reinstall: tasks, logs and generated secrets persisted.
- Async deletion removed an artifact file after task deletion.
- Bundles exported and loaded in a clean directory; tampered checksum refused.
- Rebuilding the ClearML web image takes about 8 minutes; the CA bundle is baked at build time.

## Known gaps

- No host firewall is provisioned; egress enforcement is a site task.
- Simple login mode has no password (upstream default).
- Help links and video embeds in the UI still reference public hosts on click.
- No database backup automation or credential rotation tooling.
- Build-time stripping of the UI update check is a string substitution on the built bundle; re-check it after a clearml-web upgrade.

## Operating notes

- Lab state at handoff: both stacks on AlmaLinux 9 images, data-services in TLS mode, ClearML trusting the lab CA.
- Switching base images: `./clearmlctl --env <file> configure && install` recreates the containers; data lives in the databases and `DATA_DIR`.
- Rotating TLS files: restart the data-services containers, then rebuild ClearML with the updated CA.
