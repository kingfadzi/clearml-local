# Status and limitations

Last verified: 2026-10-02, lab (AlmaLinux 9 base; UBI 9 earlier in the same day).

## Verified

- Full chain from source zips to running stack; four images built; unit tests green.
- Authenticated DB checks (plain and TLS); wrong password and untrusted CA rejected.
- SDK round trip (experiment, scalar, artifact); async deletion of artifacts.
- Services agent task with `TASK_IMAGE`, no downloads; public image rejected without pull.
- Headless browser: login and pages, only the ClearML host contacted.
- Restart and reinstall keep data and secrets; bundle/load with checksum refusal.
- Example projects import (`pre-populate/`).

## Known limitations

- No host firewall; egress enforcement is a site task.
- Simple login mode has no password (upstream default). Restrict access to the web port.
- UI help links and video embeds reference public hosts on click.
- Changing the CA bundle requires an image rebuild.
- Git-repository tasks are unsupported for the services agent; standalone scripts only.
- API server logs include DB URIs with passwords; keep `LOG_DIR` private.
- Build-time rewrite of the UI update check is a string substitution; re-check after a clearml-web upgrade.
