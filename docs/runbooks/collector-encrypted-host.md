# Encrypted collector host preparation

Implements the manual-unlock host decision in [ADR 0018](../adr/0018-capture-delivery-and-expiry.md#host-encryption-and-rollout). Use a dedicated, supported Ubuntu LTS host with Docker Engine and local ext4. Exact host versions, paths, UUIDs, capacity, maintenance schedule and recovery material belong in private operator records. [Delivery status](../delivery-plan.md) owns progress.

This slice supplies a **finite, offline fixture service**. Continuous restart, heartbeat and live activation follow separately. A merged PR does not authorize formatting, changing host settings or installing keys. Review the concrete private host plan first; execute provisioning from the operator's interactive terminal. Never send passphrases, Ubuntu Pro tokens or cloud keys to chat, commands recorded in history, or source control.

## Before host changes

Record a backup/recovery plan and inspect `lsblk -f`, `findmnt`, `df -h`, `df -i`, `free -h`, `swapon --show`, time synchronization, running containers and existing services. Stop any capture/probe sharing the quota. Preserve the v2 rehearsal and its image. Choose a new regular-file LUKS container on a persistent local filesystem with enough physical space for preallocation **and** root filesystem headroom; do not use a partition or overwrite an existing file. Account for continuing metadata/inode growth even after payload expiry.

Install `cryptsetup`, `e2fsprogs`, `util-linux` and Python 3 through Ubuntu's package manager after host-plan approval. Docker must already work. The deployment templates use `/srv/urbanpulse` and mapper name `urbanpulse-data`; these are example service paths, not published host inventory. If changing them, update the launcher and unit names together and repeat acceptance.

## Create and unlock the new volume

In a root interactive Bash terminal, set `VOLUME_FILE` to the reviewed **new absolute file path** and `VOLUME_BYTES` to the approved preallocation size. Keep its parent root-owned, mode 0700 and free of symlinks. Verify the proposed file, mapper and mount do not already exist. Do not repeat formatting after interruption: inspect and preserve partial work first.

```bash
set -eu
: "${VOLUME_FILE:?set the reviewed new file path}"
: "${VOLUME_BYTES:?set the reviewed size in bytes}"
test ! -e "$VOLUME_FILE" && test ! -L "$VOLUME_FILE"
test ! -e /dev/mapper/urbanpulse-data
test ! -e /srv/urbanpulse && test ! -L /srv/urbanpulse
python3 - "$VOLUME_FILE" "$VOLUME_BYTES" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
size = int(sys.argv[2])
if not path.is_absolute() or path.parent.resolve(strict=True) != path.parent or size <= 0:
    raise SystemExit("invalid reviewed path or size")
fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
try:
    os.posix_fallocate(fd, 0, size)
    os.fsync(fd)
finally:
    os.close(fd)
PY
stat "$VOLUME_FILE"
cryptsetup luksFormat --type luks2 --verify-passphrase "$VOLUME_FILE"
cryptsetup open --type luks2 "$VOLUME_FILE" urbanpulse-data
cryptsetup status urbanpulse-data
```

Before formatting the mapping, compare its backing device/loop file with `VOLUME_FILE` (`losetup --list` if necessary). Stop on any mismatch. Only the mapping just created in this procedure may be formatted. Do not use `-F` or suppress format confirmations.

```bash
mkfs.ext4 /dev/mapper/urbanpulse-data
install -d -m 0000 -o root -g root /srv/urbanpulse
mount -t ext4 -o rw,nodev,nosuid,noexec /dev/mapper/urbanpulse-data /srv/urbanpulse
chown root:root /srv/urbanpulse
chmod 0755 /srv/urbanpulse
install -d -m 0700 -o 10001 -g 10001 /srv/urbanpulse/store-v3 /srv/urbanpulse/exports /srv/urbanpulse/keys
cryptsetup luksUUID "$VOLUME_FILE"
blkid -s UUID -o value /dev/mapper/urbanpulse-data
```

Record the LUKS and ext4 UUIDs privately. Add/test a recovery passphrase using `cryptsetup luksAddKey` in the interactive terminal. Keep a LUKS header backup and recovery material in a separate protected, offline backup destination; do not leave them on unencrypted root or inside the only volume they recover. Test recovery before storing real data. Losing all passphrases/header access loses local history.

No `/etc/crypttab` auto-unlock entry, plaintext key file, automount or boot-time prompt is installed. After each reboot, the operator opens the existing container, starts the mount, then starts the service. Never run `luksFormat`, `mkfs` or `init` as part of reboot recovery.

## Swap, dumps and security maintenance

The selected implementation **disables swap**, rather than adding another encryption/unlock mechanism. Check available memory and stop unnecessary work first. Back up `/etc/fstab` privately, disable the specific reviewed swap entry with `sudoedit`, then `swapoff` that entry. Check other swap units, zram generators and resume configuration; disable any mechanism that recreates swap and verify again after reboot. Do not delete the old swap file as part of this PR. Empty `swapon --show` output and a header-only `/proc/swaps` are required; the launcher refuses any active swap.

Keep suspend, hibernate, hybrid sleep and suspend-then-hibernate disabled on the dedicated host. Disable host core/crash dumps (including any configured kernel crash dump service) before secrets are installed. Set systemd coredump `Storage=none` and `ProcessSizeMax=0`, check Ubuntu Apport separately, and keep `LimitCORE=0` plus the container core limit in the supplied service. Docker's equal memory and memory-swap limits prevent container swap use; they do not replace the host swap check.

Install [99urbanpulse-no-reboot](../../ops/collector/99urbanpulse-no-reboot) in `/etc/apt/apt.conf.d/` as root, mode 0644. Keep the existing Ubuntu security origins and enabled unattended-upgrades/APT timers. Inspect the **effective** `apt-config dump`: periodic updates and unattended upgrades must be enabled, and `Unattended-Upgrade::Automatic-Reboot` must be false. Later configuration files can override these values. Inspect any other reboot scheduler too; this APT setting does not cancel independently scheduled reboots. [Ubuntu documents these controls](https://ubuntu.com/server/docs/how-to/software/automatic-updates/).

For Livepatch, first inspect `pro status`, the running kernel and the [supported kernel matrix](https://ubuntu.com/security/livepatch/docs/client/reference/platform/supported-kernels/). If eligible and the operator chooses to attach/enable Ubuntu Pro, use the private interactive authentication flow, then `sudo pro enable livepatch` and `canonical-livepatch status --verbose`. Record unsupported/unattached status honestly; never treat it as patched. Livepatch [does not replace userspace updates or required kernel reboots](https://ubuntu.com/security/livepatch/docs/client/explanation/troubleshooting/do-i-need-to-reboot/). Keep a scheduled maintenance check for `/run/reboot-required`, package failures and Livepatch status, with a named operator and due time in private notes.

For maintenance: stop capture/downstream services, wait for clean container shutdown, preserve evidence, unmount, close the mapping, apply updates and reboot. Manually unlock/mount afterwards, inspect bounded status, and finish any verification/expiry recovery before restarting. Record the gap. An external heartbeat-loss alert must cover offline/locked periods before unattended live activation.

## Install the fixture service after review

From the reviewed checkout, build the capture **runtime** image and record its local immutable image ID (`docker image inspect --format '{{.Id}}' <reviewed-image>`). The launcher accepts only `sha256:<64 hex>` IDs and uses `--pull=never`; a missing local image fails instead of fetching a replacement. This local ID is for host rehearsal, not an OCI registry release manifest.

Install files as root-owned files in root-owned directories:

```bash
sudo install -d -m 0755 /usr/local/lib/urbanpulse
sudo install -d -m 0700 /etc/urbanpulse
sudo install -m 0644 scripts/collector_host.py /usr/local/lib/urbanpulse/collector_host.py
sudo install -m 0600 ops/collector/collector-host.example.json /etc/urbanpulse/collector-host.json
sudoedit /etc/urbanpulse/collector-host.json
sudo install -m 0644 ops/collector/srv-urbanpulse.mount /etc/systemd/system/
sudo install -m 0644 ops/collector/urbanpulse-capture-rehearsal.service /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/srv-urbanpulse.mount /etc/systemd/system/urbanpulse-capture-rehearsal.service
sudo systemctl daemon-reload
sudo python3 /usr/local/lib/urbanpulse/collector_host.py check
sudo python3 /usr/local/lib/urbanpulse/collector_host.py init
sudo systemctl start urbanpulse-capture-rehearsal.service
```

Replace the three config placeholders with the private recorded UUIDs and image ID; no secrets belong in this file. `init` is a one-time explicit action on the fresh empty v3 directory. Subsequent starts use `run`, never `init`. Check `systemctl show ... -p Result -p ExecMainStatus` and the journal after the finite run; success is six synthetic captures, not a continuously active service.

The launcher verifies exact ext4 mount/UUID, filesystem root, LUKS2 device-mapper identity, mapper major/minor, required mount options, private store permissions, no symlink/shadow store mount and no swap. It binds only the store, with network disabled and no keys. It checks before any Docker command. **Root/Docker-group operators remain trusted**: they can bypass the service, change configuration or unmount storage, so this does not defend against a malicious administrator.

The service runs the Docker supervisor as root; capture inside Docker runs as 10001. `BindsTo` plus `After` ties service lifetime to the mount and Docker ([systemd semantics](https://github.com/systemd/systemd/blob/main/man/systemd.unit.xml)). Starting while locked may attempt the mount and fail; it cannot unlock the volume. `ExecStop` stops the named container before unmount, including during shutdown. No restart policy, timer or enable-at-boot target is supplied. Unexpected stale containers are an error: inspect their ownership before cleanup; no blind force removal occurs.

## Continuous-service handoff

The finite rehearsal deliberately stays stopped after Docker stops or restarts, including a Docker/containerd package update that restarts the daemon. The operator must restart an interrupted rehearsal after checking its outcome. This is not acceptable behavior for the later continuous service.

Before unattended activation, that slice must test Docker stop/start and restart (including the package-update path): once Docker returns and the volume remains correctly unlocked/mounted, capture automatically resumes with the same store and without duplicate writers. A locked, missing or mismatching mount still refuses capture; deliberate maintenance stop must stay stopped. A process `Restart=` setting alone is not proof of recovery from a dependency-driven stop: explicitly wire and test daemon-recovery activation.

External heartbeat-loss monitoring must detect this interruption even when no local process can send a failure report. Test alert delivery for a prolonged daemon outage, recovery after restart, and continued refusal/alerting while locked. Record capture gaps. The next continuous-service/heartbeat PR owns this restart strategy and its integration tests; these are activation gates, not behavior implemented by the rehearsal unit.

## Locked-volume and reboot acceptance

Use fixture data only. Keep exact commands/results privately; public evidence describes behavior without host inventory.

1. **Locked refusal:** stop the service and confirm no rehearsal container remains. Stop the mount and close `urbanpulse-data`. Verify the underlying mountpoint is empty, root-owned mode 0000; never create `store-v3` under it. Attempt both the launcher and service start. Expect nonzero/refused or failed dependency, no new container/capture and no new underlying files.
2. **Wrong identity:** with the volume mounted, temporarily put a different test filesystem UUID in the private config. Both direct launcher and service must refuse without creating a session. Restore the recorded value. Unit tests cover plain/tmpfs/overlay and shadow mounts; test alternate real mounts only on a separate disposable test host.
3. **Unlocked capture:** open the existing LUKS file interactively; `systemctl start srv-urbanpulse.mount`. Run guard check, bounded status, finite service and `verify` through the launcher. Expect six additional captures and verified retained bytes. Existing v2 evidence must remain unchanged.
4. **Mount lifetime:** during a fixture run, `systemctl stop srv-urbanpulse.mount` must stop the service/container before unmount. Do not force/lazy-unmount or detach backing loops. Unlock/start again and verify checkpoint recovery.
5. **Controlled reboot:** stop cleanly, reboot in the agreed window. Confirm the volume is locked, no service/container started, swap remains disabled, security updates enabled and automatic reboot false. Repeat locked refusal, then manually unlock/mount, status and fixture run. Record the gap.
6. **Failure handling:** a failed verification, partial expiry, missing image, wrong mount or nonzero run is a failure, not permission to reinitialize. Follow [local capture recovery](local-capture.md#incomplete-expiry-recovery-order), keep evidence and investigate.

The automated tests exercise guard decisions with synthetic kernel responses. They do not certify LUKS provisioning, boot ordering, real mount loss or this host's swap/reboot configuration. Complete the above drill after separate host-plan approval. Provider/upload keys, continuous operation, external alerts and raw expiry remain subsequent gates.


## Development validation

On 2026-10-08, all 31 guard tests passed on Windows and in the isolated Linux capture test image. Run `uv run pytest -q tests/test_collector_host.py` from the checkout. Cases include wrong/plain/temporary/shadow mounts, wrong crypto identity, swap, mutable image tags malformed mount JSON, and a failed mount lookup proving Docker is never invoked. The Linux run used a read-only checkout, no network and disposable temporary storage.

Both units passed `systemd-analyze verify --man=no` in a disposable container with the files at their documented install paths/modes. Docker was a stub for this syntax check; it did not exercise service lifetime or mounting. Ruff lint/format and the existing application mypy scope passed. The guard is now separately checked in CI with `uv run --locked mypy --strict --platform linux scripts/collector_host.py`; the original 81-file application check did not include it. Real encrypted-volume, reboot and mount-loss acceptance remains the operator drill above; no host settings or secrets were changed during development.
