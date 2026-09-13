# Netplay protocol fixtures

Documentation and metadata for a captured two-player FSNP session used as
golden test data for `internal/fsnp`, per
[../netplay-go-server-design.md](../netplay-go-server-design.md).

**The actual fixture bytes live at
[`fsnp-server/internal/fsnp/testdata/`](../../fsnp-server/internal/fsnp/testdata/),
not here.** That's the only copy — Go's `testdata/` convention means the
build tooling ignores it, tests find it via a relative path from the test
file, and the Go module stays self-contained if `fsnp-server/` is ever split
into its own repository (see "Repository layout" in the design doc). This
directory used to hold a second copy of the same `.bin` files; that was
unnecessary duplication with nothing keeping the two in sync, so it was
removed — see [manifest.json](../../fsnp-server/internal/fsnp/testdata/manifest.json)
for what's in the canonical copy without needing to check out the Go module.

The source pcap itself (loopback capture, ~7 MB, ~95k packets including
unrelated traffic) is not committed anywhere; the testdata files are the
application-layer payload only, extracted with `extract_fixtures.py`.

## Capture context

- Two `fs-uae` clients (`v3.1.66`) against `launcher/server/game.py`, both on
  `127.0.0.1`, password-protected, tags `P1` and `P2`.
- ~6,168 frames (~2 minutes at 20 ms/frame). No `ERROR` messages — the session
  ran to a clean end with no desync.
- Full details, invariants, and how these files were used are in
  [manifest.json](../../fsnp-server/internal/fsnp/testdata/manifest.json) and in the "Verified against a captured
  session" section of the design doc.

## Files in `fsnp-server/internal/fsnp/testdata/`

| File | Contents |
|------|----------|
| `client1-handshake.bin`, `client2-handshake.bin` | The 28-byte `FSNP` handshake each client sent, verbatim |
| `client1-to-server.bin`, `client2-to-server.bin` | Everything each client sent after its handshake — the `RND_CHECK`/`MEM_CHECK`/frame-ack/input-event stream |
| `server-to-client1.bin`, `server-to-client2.bin` | Everything the server sent to each client, coalesced exactly as it was flushed on the wire |
| `manifest.json` | Per-connection metadata (tag, emulator version, byte counts, max frame) plus the cross-client checksum comparison: 6,164 common frames, zero `MEM_CHECK`/`RND_CHECK` mismatches |

## Regenerating from a new pcap

```
python3 extract_fixtures.py /path/to/capture.pcap ../../fsnp-server/internal/fsnp/testdata
```

Requires a loopback (`DLT_NULL`) capture of a two-client TCP session on the
netplay port — no external dependencies (no `dpkt`/`scapy`), stdlib only.
Writing straight into `fsnp-server/internal/fsnp/testdata/` keeps there being
exactly one copy of every file it produces, `manifest.json` included.

## What these are good for

- **Golden decode tests**: word-by-word decode of `server-to-client*.bin` and
  `*-to-server.bin` against the command table in the design doc.
- **Handshake round-trip tests**: parse `client*-handshake.bin`, re-encode,
  compare bit-for-bit.
- **The sync-check invariant**: attribute each `MEM_CHECK`/`RND_CHECK` to the
  previously-acked frame (see the design doc) and confirm the Go
  implementation reproduces zero mismatches across all 6,164 common frames,
  matching `manifest.json`'s `cross_client_check`.

## What these are not good for

This is one healthy session on loopback — it has no error paths, no dropped
connections, no oversized `TEXT` messages, and (being loopback) never splits a
4-byte word across a TCP segment. Fixtures for those cases still need to be
constructed by hand or from `game.py`'s functions directly, as described in
the design doc's "Protocol package with golden tests" section.
