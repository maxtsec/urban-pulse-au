# CLOUD-01: Raw tram collection activation

Observed 8 October 2026. Progress belongs to the [delivery plan](../delivery-plan.md).

The architect authorized continuous raw-only capture after bounded live and notification acceptance. The operator started the existing reviewed runtime at 04:49 UTC. The service passed its encrypted-mount, volume identity, disabled-swap, pinned-image, exact collector identity and key-permission guards. A full v3 verification passed before activation; the retained store was continued without initialization or deletion.

Positions run every 60 seconds, trip updates every 120 seconds and service alerts every 60 seconds, under the existing shared spacing, backoff and startup delay. The initial observation recorded seven captures and new successes from every feed. Independent Cloud Monitoring readback at 04:54 UTC found all nine expected streams: heartbeat, success-known and success-age for each feed, free bytes and free inodes. Every stream had a point about 17 seconds old, all success-known values were 1 and capture ages were 0–104 seconds. This verifies initial operation, not uninterrupted future availability.

The seven production alert policies matched the accepted enrollment: six raw-only policies enabled, upload disabled. Earlier operator email acknowledgements cover heartbeat absence, three feeds' unknown/stalled-success alerts and both capacity thresholds. The isolated drill's last five-minute partial-stream observation did not finish before its bound; its terminal recovery/verification is not claimed complete. Healthy recovery after capacity phases was recorded, and actual production store verification plus fresh complete telemetry were checked for activation. Five isolated test policies were removed without changing the production policies. Existing automated partial-write tests remain distinct from cloud notification evidence.

## Operating scope

- Keep raw payloads, manifests, receipts and sequence indexes locally on the encrypted volume. No normalization, upload or expiry writer is activated by this change.
- Preserve every unconfirmed raw capture. Stop at the existing protected disk/inode reserve and retain the operator alert thresholds; do not silently delete data to extend collection.
- systemd supervises the collector independently of Docker and SSH. Closing the operator terminal does not stop capture. After reboot, manually unlock, mount and start as required by the accepted policy; no boot target or automatic unlock is added.
- The public day explorer remains synthetic. Collected positions are not yet a live map feed, and collection frequency is not a live animation delay policy.

Private operator records retain the exact host configuration, image ID, helper hashes, full verification output, cloud readback, key installation and policy-window audit. Host versions, addresses, credentials, account identifiers and financial details are not published. See the [continuous service runbook](../runbooks/collector-continuous.md) for stop/restart and recovery instructions.
