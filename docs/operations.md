# Operations

All commands from the `clearml-local` root. Chain commands run every earlier step; `--from STEP` starts later.

Chain: `trust` → `prepare` → `dependencies` → `build` → `configure` → `preflight` → `install` → `verify`.

## Change a `.env` value

| Changed | Run |
|---|---|
| URLs, ports, DB keys, agent keys | `./clearmlctl install --from configure` |
| `TLS_CA_BUNDLE_URL` or CA files | `./clearmlctl install --from trust` (rebuilds images) |
| Images, indexes, proxy | `./clearmlctl install` |

UI picks up `configuration.json` changes on reload; no restart needed.

## Upgrade ClearML sources

```sh
rm -rf clearml clearml-server clearml-web clearml-agent *.zip
cp /path/to/new/*.zip .
./clearmlctl install
```

- `prepare` records the new trees in `sources.lock.json` (note printed).
- `build` resolves a new wheelhouse automatically.
- Commit `sources.lock.json` after qualifying the release; set `STRICT_SOURCES=true` to freeze it.

## Example projects

```sh
./clearmlctl examples      # existing database; idempotent
```

Fresh installs import `pre-populate/*.zip` on first start. Delete the archives to disable.

## Restart / stop

```sh
docker compose --project-directory . -f generated/compose.json restart
docker compose --project-directory . -f generated/compose.json down     # keeps DATA_DIR and databases
./clearmlctl install --from install
```

## Back up

- `generated/config/secure.conf`: token signing secrets and system credentials. Losing it invalidates sessions and agent credentials.
- `.env`.
- `DATA_DIR` (artifacts). Databases: see data-services.

## Transfer to another host

Source host:

```sh
./clearmlctl bundle        # dist/images.tar, dist/installer.tar.gz, dist/checksums.json
```

Target host:

```sh
tar -xzf installer.tar.gz && cd clearml-local
cp /path/images.tar /path/checksums.json dist/
./clearmlctl load
cp /secure/.env .   # plus generated/config/secure.conf if migrating an existing instance
./clearmlctl install --from configure
```

## Acceptance checks

```sh
./clearmlctl verify
# SDK round trip (needs a clearml.conf with UI credentials):
docker run --rm -e CLEARML_CONFIG_FILE=/run/clearml.conf -v $PWD/clearml.conf:/run/clearml.conf:ro \
  -v $PWD/scripts/smoke.py:/smoke.py:ro <TASK_IMAGE> python /smoke.py
# Services task through the agent:
docker run --rm -e CLEARML_CONFIG_FILE=/run/clearml.conf -v $PWD/clearml.conf:/run/clearml.conf:ro \
  -v $PWD/scripts/services-task.py:/t.py:ro <TASK_IMAGE> python /t.py --image <TASK_IMAGE> --expect completed
```

## Logs

```sh
docker logs clearml-apiserver-1 --tail 100
docker logs clearml-agent-services-1 --tail 100
ls $LOG_DIR
```
