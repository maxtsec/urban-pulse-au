# Tram source-field audit

Run this offline census before freezing `tram-normalized-v1`, following the [accepted contract](../architecture/normalized-tram-contract.md#one-day-source-field-audit-before-schema-freeze). It reports source-field presence and unknown wire fields; it does not implement the normalizer, approve schema completeness or authorize expiry.

## Inputs and isolation

Use a development checkout with locked dev dependencies. The running collector image does not need this tool or a dependency upgrade. Run a separate bounded process/container with the raw store mounted **read-only** and a private encrypted output directory mounted separately. Keep the live collector running; do not take its journal lock, use sudo to bypass store ownership, copy keys, restart its service or mount any credentials. No network is needed. Keep the operator's resource limits on the separate process/container; stop the audit if collection headroom is threatened.

The reader requires v3 and refuses any existing policy/expiry records. It reads control once, verifies its checksum and freezes the finalized high-water sequence, excluding pending capture state. Each sequence resolves through the immutable index, intent, manifest and receipt. Selected payload length/SHA-256 must match. It reads no unfinalized capture, writes no live-store file and uses no journal mutation API. It does not replace full store verification or prove that other processes have not been configured to delete raw; run only while the accepted disabled-expiry policy remains in force.

Supply an explicit inclusive sequence range covering the target day. At first collection, starting at sequence 1 is practical. For later days, choose a known range from retained operator inventory; this tool deliberately does not discover it by an unbounded archive scan or assume clocks always increase. Unsuccessful captures are selected by request time because they have no receipt; successful captures use receipt time. UTC interval selection is half-open. Include actual gaps and fixture/live counts in review.

## Command

Example paths refer to the read-only mount and separate encrypted export mount, not an instruction to change the collector service:

```text
uv run --locked --no-default-groups --group dev python -m scripts.tram_field_audit --store /raw --output /exports/audit-day-01 --start 2026-10-08T00:00:00Z --end 2026-10-09T00:00:00Z --first-sequence 1 --last-sequence 3600
```

Replace the example dates and sequence bound with real finalized inputs; 3,600 is not a measured high-water mark. For a Melbourne local day, supply its actual UTC bounds and record the local date/timezone alongside the report (DST days need not be 24 hours). A future end time or a one-day interval containing only a few samples is not a completed one-day audit. The report always leaves `schema_freeze_approved` and `mapping_completeness_evaluated` false.

Output must be a new directory outside the raw store. It contains one `report.json`, published after a bounded scan, with an input inventory/hash, descriptor hash, audit commit/dirty status/file hashes, per-feed capture outcomes/entity counts, receipt gaps including interval edges, sequence-order time regressions, and per-field presence/absence/explicit-default counts. Presence counts refer to parent message occurrences; `captures_present` counts distinct captures. Samples identify up to three captures per field, never field values. Nested absent messages do not invent leaf occurrences. An unknown enum may appear as an unknown field with a known tag; this is explicitly reported as `unknown_enum_or_wire`, not silently accepted. Registered extensions are flagged for review too.

Keep reports private: they contain source capture identities and acquisition timestamps. An interrupted write can leave `report.incomplete`; it is not success. Retain it and rerun into a new directory. Existing reports are never overwritten. An integrity/limit error returns exit 2 and no successful report. A completed census may contain unknown fields or malformed payload references and still returns 0: completion means the scan ran, not that the schema passed.

## Bounds and review

The current tool limits the interval to 26 hours, the sequence range to 10,000 captures, individual payloads to 8 MiB, total selected payloads to 2 GiB, field paths to 8,192, descriptor-field visits to 200 million, elapsed scan time to five minutes and the report to 16 MiB. Bounds fail explicitly, never return a truncated successful census. Before output, preserve at least 5 GiB plus report allowance and, on Linux, 100,010 free inodes. These are audit-only guards; they do not change collector settings. The larger traversal bound permits a feed-sized full-day scan while the independent five-minute deadline remains in force. Measure a real day before further changes; smaller exploratory runs do not satisfy the full-day schema-freeze gate.

Review every unknown path/enum/extension and observed field against the pinned spec and proposed mapping. Record affected capture counts, explicit disposition and retained-raw capacity impact. Add synthetic regression inputs for provider extensions before implementing their mapping. A clean unknown-field list only means the installed descriptor recognized the wire fields; it does not prove the proposed normalized columns preserve them all. No field values are automatically published, and no quality disposition is written back to the collector.

## Verification

`tests/test_tram_field_audit.py` covers deterministic reports, explicit zero versus absence, nested unknown fields and enums, incomplete capture exclusion, failures/gaps, clock rollback, corrupt payload/receipt/index/control, retention-state refusal, resource limits, separate output and no network. Linux cases hold the collector lock while reading a read-only tree and reject symlink inputs. Local Linux validation also runs as an unprivileged container user with a read-only root and network disabled. These synthetic tests do not constitute the real one-day audit or a cloud upload acceptance.

The default-limit regression processes 3,600 synthetic captures at the accepted 60/120/60 cadence, including 720 approximately 87 KB trip-updates payloads with 85 trips and 30 stop updates each. It traverses more than 30 million fields and verifies complete report counts. No clock or resource bound is mocked; existing small-bound tests retain fail-closed coverage. This is a capacity regression, not an audit of private live captures.
