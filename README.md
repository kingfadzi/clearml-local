# ClearML offline installer

Builds ClearML Server, web UI, services agent and SDK from pinned source zips and runs them with Docker Compose against the `data-services` databases. Nothing is pulled from ClearML; only your base and builder images are pulled.

## Quickstart

```sh
git clone <gitlab>/staging/clearml-local.git && cd clearml-local
cp .env.example .env && chmod 600 .env
# edit .env: images, PIP_INDEX_URL, NPM_REGISTRY, TLS_CA_BUNDLE_URL, CLEARML_*_URL, DATA/LOG/AGENT dirs,
#           database keys from data-services generated/clearml.env
cp /path/to/clearml-*.zip .          # four release zips: server, web, agent, clearml
./clearmlctl install
./clearmlctl verify
```

Open `CLEARML_WEB_URL`, enter a name, START. Install data-services first.

## Docs

- [Install runbook](docs/install.md): both repos, step by step, with expected output.
- [Configuration](docs/configuration.md): every `.env` key.
- [Operations](docs/operations.md): changes, upgrades, backup, transfer, acceptance checks.
- [Troubleshooting](docs/troubleshooting.md): symptom, cause, fix.
- [Architecture](docs/architecture.md): what is pulled, what is built, how it connects.
- [Status](docs/status.md): verified behaviour and limitations.

## Commands

Chain (each runs every earlier step): `trust` `prepare` `dependencies` `build` `configure` `preflight` `install` `verify`.
Standalone: `examples` `status` `bundle` `load`. Options: `--env FILE`, `--from STEP`, `--archive PATH`.

## Tests

```sh
python3 -m unittest discover -s tests -q
```
