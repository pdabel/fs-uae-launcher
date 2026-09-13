# Netplay protocol fixtures

Real bytes from a captured two-player FSNP session, extracted for use as golden
test data when building `internal/fsnp` per [../netplay-go-server-design.md](../netplay-go-server-design.md).
The source pcap (loopback capture, ~7 MB, ~95k packets including unrelated
traffic) is not committed here; these files are the application-layer payload
only, extracted with `extract_fixtures.py`.

## Capture context

- Two `fs-uae` clients (`v3.1.66`) against `launcher/server/game.py`, both on
  `127.0.0.1`, password-protected, tags `P1` and `P2`.
- ~6,168 frames (~2 minutes at 20 ms/frame). No `ERROR` messages — the session
  ran to a clean end with no desync.
- Full details, invariants, and how these files were used are in
  [manifest.json](manifest.json) and in the "Verified against a captured
  session" section of the design doc.

## Files

| File | Contents |
|------|----------|
| `client1-handshake.bin`, `client2-handshake.bin` | The 28-byte `FSNP` handshake each client sent, verbatim |
| `client1-to-server.bin`, `client2-to-server.bin` | Everything each client sent after its handshake — the `RND_CHECK`/`MEM_CHECK`/frame-ack/input-event stream |
| `server-to-client1.bin`, `server-to-client2.bin` | Everything the server sent to each client, coalesced exactly as it was flushed on the wire |
| `manifest.json` | Per-connection metadata (tag, emulator version, byte counts, max frame) plus the cross-client checksum comparison: 6,164 common frames, zero `MEM_CHECK`/`RND_CHECK` mismatches |

## Regenerating from a new pcap

```
python3 extract_fixtures.py /path/to/capture.pcap ./out
```

Requires a loopback (`DLT_NULL`) capture of a two-client TCP session on the
netplay port — no external dependencies (no `dpkt`/`scapy`), stdlib only.

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
