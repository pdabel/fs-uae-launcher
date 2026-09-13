"""Extract FSNP application-layer byte streams from a pcap for use as
protocol golden-test fixtures. Source pcap is not committed; this script
regenerates the fixtures from any similarly-captured session.

Usage: python3 extract_fixtures.py <path-to-pcap> <output-dir>
"""
import struct
import sys
import json
from collections import defaultdict


def parse_pcap(path):
    data = open(path, "rb").read()
    endian = "<" if data[:4] == b"\xd4\xc3\xb2\xa1" else ">"
    network = struct.unpack(endian + "IHHiIII", data[:24])[6]

    off = 24
    streams = defaultdict(list)
    while off < len(data):
        if off + 16 > len(data):
            break
        ts_sec, ts_usec, incl_len, orig_len = struct.unpack(
            endian + "IIII", data[off:off + 16]
        )
        off += 16
        pkt = data[off:off + incl_len]
        off += incl_len

        # network == 0: BSD loopback (NULL), 4-byte address-family header
        ip = pkt[4:] if network == 0 else pkt
        if len(ip) < 20:
            continue
        ihl = (ip[0] & 0x0F) * 4
        if ip[9] != 6:  # TCP only
            continue
        total_len = struct.unpack(">H", ip[2:4])[0]
        tcp = ip[ihl:]
        if len(tcp) < 20:
            continue
        srcport, dstport, seq, ack, offres, flags = struct.unpack(
            ">HHIIBB", tcp[:14]
        )
        data_off = (offres >> 4) * 4
        payload = tcp[data_off: total_len - ihl] if total_len >= ihl else tcp[data_off:]
        if not payload:
            continue
        streams[(srcport, dstport)].append((seq, bytes(payload)))
    return streams


def reassemble(streams, key):
    pkts = sorted(streams[key], key=lambda x: x[0])
    out = bytearray()
    expected = None
    for seq, payload in pkts:
        if expected is None:
            expected = seq
        if seq < expected:
            overlap = expected - seq
            if overlap >= len(payload):
                continue
            payload = payload[overlap:]
            seq = expected
        if seq > expected:
            raise ValueError(f"gap in stream {key}: expected {expected}, got {seq}")
        out += payload
        expected = seq + len(payload)
    return bytes(out)


def find_netplay_connections(streams):
    """Identify (client_port, server_port) pairs carrying the FSNP handshake."""
    found = []
    for (src, dst), pkts in streams.items():
        pkts_sorted = sorted(pkts, key=lambda x: x[0])
        if not pkts_sorted:
            continue
        if pkts_sorted[0][1][:4] == b"FSNP":
            found.append((src, dst))
    return found


def attribute_checks(stream):
    """Tag each MEM_CHECK/RND_CHECK with the previously-acked frame, matching
    the server's attribution rule (checks for frame f arrive before the ack
    for f, see docs/netplay-go-server-design.md)."""
    n = len(stream) // 4
    words = struct.unpack(">%dI" % n, stream[:n * 4])
    current_frame = -1
    mem, rnd = {}, {}
    for w in words:
        if w & 0x80000000:
            cmd = (w & 0x7F000000) >> 24
            d = w & 0x00FFFFFF
            if cmd == 5:
                mem[current_frame] = d
            elif cmd == 6:
                rnd[current_frame] = d
        elif w & (1 << 30):
            current_frame = w & 0x3FFFFFFF
    return mem, rnd


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    pcap_path, out_dir = sys.argv[1], sys.argv[2]
    streams = parse_pcap(pcap_path)
    handshakes = sorted(find_netplay_connections(streams))
    if len(handshakes) != 2:
        print(f"expected 2 client connections, found {len(handshakes)}: {handshakes}")

    import os
    os.makedirs(out_dir, exist_ok=True)

    manifest = {"connections": []}
    for i, (client_port, server_port) in enumerate(handshakes, start=1):
        c2s = reassemble(streams, (client_port, server_port))
        s2c = reassemble(streams, (server_port, client_port))
        handshake = c2s[:28]
        body_c2s = c2s[28:]

        open(f"{out_dir}/client{i}-handshake.bin", "wb").write(handshake)
        open(f"{out_dir}/client{i}-to-server.bin", "wb").write(body_c2s)
        open(f"{out_dir}/server-to-client{i}.bin", "wb").write(s2c)

        mem, rnd = attribute_checks(body_c2s)
        manifest["connections"].append({
            "index": i,
            "client_port": client_port,
            "server_port": server_port,
            "tag": handshake[21:24].rstrip(b"\x00").decode("ascii", "replace"),
            "player_byte": handshake[20],
            "emulator_version": {
                "name": handshake[9:14].decode("ascii", "replace"),
                "major": handshake[14],
                "minor": handshake[15],
                "revision": handshake[16],
            },
            "resume_from_packet": struct.unpack(">I", handshake[24:28])[0],
            "client_to_server_bytes": len(body_c2s),
            "server_to_client_bytes": len(s2c),
            "max_frame": max(mem.keys()) if mem else None,
            "zero_mem_check_frames": sorted(f for f, v in mem.items() if v == 0),
        })

    if len(handshakes) == 2:
        (p1, s1), (p2, s2) = handshakes
        c2s1 = reassemble(streams, (p1, s1))[28:]
        c2s2 = reassemble(streams, (p2, s2))[28:]
        mem1, rnd1 = attribute_checks(c2s1)
        mem2, rnd2 = attribute_checks(c2s2)
        common = sorted(set(mem1) & set(mem2))
        mismatches = [f for f in common if mem1[f] != mem2[f]]
        rnd_common = sorted(set(rnd1) & set(rnd2))
        rnd_mismatches = [f for f in rnd_common if rnd1[f] != rnd2[f]]
        manifest["cross_client_check"] = {
            "common_frames": len(common),
            "mem_check_mismatches": len(mismatches),
            "rnd_check_mismatches": len(rnd_mismatches),
        }

    with open(f"{out_dir}/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"wrote fixtures to {out_dir}")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
