# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Configure CLEARML_API_URL in .env` | Placeholder `CHANGE_ME` still in `.env` | Set the real host, rerun |
| `clearml-init`: "could not verify credentials" | Pasted block has `api_server` with a host the client cannot resolve (`clearml-host`, wrong name) | Set `CLEARML_API_URL` to a reachable host, `./clearmlctl install --from configure`, hard-reload UI, recreate credentials |
| UI still shows old API URL after `configure` | Browser cache | Hard reload (Ctrl+F5) |
| `Image registry is not in ALLOWED_HOSTS` | Pulled image registry not listed | Add the registry hostname to `ALLOWED_HOSTS`, or leave `ALLOWED_HOSTS` blank |
| `Use a versioned image tag or digest` | `:latest` or untagged image reference | Use an explicit tag |
| `Could not pull base image` | Wrong reference, no registry access, no `docker login` | Check `docker pull <ref>` by hand |
| `Could not download TLS_CA_BUNDLE_URL` | Download host uses the private CA | `cp ca.pem config/tls-ca-bundle.pem`, rerun. Or copy the zip to `config/tls-ca-bundle.zip` |
| Build: `cp: cannot stat '/tmp/tls-certs/...'` | Old `install-trust.sh` with spaces in cert names | `git pull`, rebuild |
| WSL: `error mounting ... to rootfs at "/etc/clearml.conf"` | Docker Desktop cannot bind single files | `git pull` (directory mounts since a74d804), `./clearmlctl install --from build` |
| `wheelhouse/ belongs to other sources; resolving again` | Sources changed since last build | Normal; wait |
| `prepare`: `multiple root ZIPs` | Two archives for one component in the root | Keep one |
| `prepare`: `source differs from lock` | `STRICT_SOURCES=true` and a different release | Use the locked release or set `STRICT_SOURCES=false` |
| `preflight`: `Elasticsearch ... TlsError` | ClearML images do not trust the DB CA | Include the CA in the bundle zip, `./clearmlctl install --from trust` (rebuilds) |
| `preflight`: `ServerSelectionTimeoutError` / `ConnectionError` | Wrong DB host or TLS mismatch | Compare `.env` DB keys with data-services `generated/clearml.env` |
| `preflight`: `AuthenticationException` / `OperationFailure` | Wrong DB password | Re-copy `generated/clearml.env` values |
| API logs: `Failed initializing mongodb: not authorized ... getParameter` | Old data-services Mongo user without `clusterMonitor` | Update data-services, recreate the Mongo user |
| Agent: `Could not find queue "services"` | Old render without `--create-queue` | `git pull`, `./clearmlctl install --from configure` |
| Agent task fails: `Offline Docker policy: Task must use the configured TASK_IMAGE` | Task requested another image | Expected; only `TASK_IMAGE` runs |
| No example projects | Database was not empty on first start | `./clearmlctl examples` |
| Web container restarting: `host not found in upstream` | Old nginx config | `git pull`, rebuild |

## Useful commands

```sh
./clearmlctl status
docker logs clearml-apiserver-1 --tail 100
docker logs clearml-agent-services-1 --tail 50
docker compose --project-directory . -f generated/compose.json config
curl -s http://<api host>:8008/debug.ping
curl -s -u '<key>:<secret>' http://<api host>:8008/auth.login | head -c 200
```

## Where things are

- `.env`: site settings (never committed).
- `generated/config/secure.conf`: signing secrets and system credentials (back up).
- `generated/compose.json`: rendered Compose model.
- `generated/trust/`: staged CA material for builds.
- `wheelhouse/`: resolved Python wheels.
- `DATA_DIR`: uploaded artifacts.
