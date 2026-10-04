#!/usr/bin/env python3
"""Compile a small Qt .ts translation into a .qm file, like lrelease:
  ts2qm.py IN.ts OUT.qm [--base BASE.qm]

With --base, the messages of an existing .qm are kept unless IN.ts translates them too.
Only what QTranslator needs to look messages up: the hash table, the messages and the
language's plural rule (English when there is no base)."""
import struct
import sys
import xml.etree.ElementTree as ET

MAGIC = bytes([0x3C, 0xB8, 0x64, 0x18, 0xCA, 0xEF, 0x9C, 0x95, 0xCD, 0x21, 0x1C, 0xBF, 0x60, 0xA1, 0xBD, 0xDD])
TAG_HASHES, TAG_MESSAGES, TAG_NUMERUS_RULES, TAG_LANGUAGE = 0x42, 0x69, 0x88, 0xA7
TAG_END, TAG_TRANSLATION, TAG_OBSOLETE1, TAG_SOURCE, TAG_CONTEXT, TAG_COMMENT = 1, 3, 5, 6, 7, 8
ENGLISH_PLURALS = bytes([0x01, 0x01])  # form 0 when n == 1, otherwise form 1


def elf_hash(data):
    h = 0
    for c in data:
        h = ((h << 4) + c) & 0xFFFFFFFF
        g = h & 0xF0000000
        if g:
            h ^= g >> 24
        h &= ~g & 0xFFFFFFFF
    return h or 1


def field(tag, data):
    return bytes([tag]) + struct.pack(">I", len(data)) + data


def read_ts(path):
    """(hash, (context, source, comment), record) for every message in a .ts file."""
    root = ET.parse(path).getroot()
    out = []
    for ctx in root.findall("context"):
        context = (ctx.findtext("name") or "").encode()
        for msg in ctx.findall("message"):
            source = (msg.findtext("source") or "").encode()
            comment = (msg.findtext("comment") or "").encode()
            tr = msg.find("translation")
            forms = [f.text or "" for f in tr.findall("numerusform")] if msg.get("numerus") == "yes" \
                else [tr.text or ""]
            record = b"".join(field(TAG_TRANSLATION, text.encode("utf-16-be")) for text in forms)
            record += field(TAG_SOURCE, source) + field(TAG_CONTEXT, context)
            record += field(TAG_COMMENT, comment) + bytes([TAG_END])
            out.append((elf_hash(source + comment), (context, source, comment), record))
    return root.get("language") or "en", out


def read_qm(path):
    """The sections of a compiled .qm and its messages, in the same form as read_ts."""
    data = open(path, "rb").read()
    if data[:16] != MAGIC:
        raise SystemExit(f"{path}: not a .qm file")
    sections, pos = {}, 16
    while pos < len(data):
        (n,) = struct.unpack(">I", data[pos + 1:pos + 5])
        sections[data[pos]] = data[pos + 5:pos + 5 + n]
        pos += 5 + n
    msgs, table, out = sections.get(TAG_MESSAGES, b""), sections.get(TAG_HASHES, b""), []
    for i in range(0, len(table), 8):
        h, start = struct.unpack(">II", table[i:i + 8])
        p, fields = start, {}
        while msgs[p] != TAG_END:
            if msgs[p] == TAG_OBSOLETE1:
                p += 5
                continue
            (n,) = struct.unpack(">I", msgs[p + 1:p + 5])
            fields.setdefault(msgs[p], msgs[p + 5:p + 5 + n])
            p += 5 + n
        key = (fields.get(TAG_CONTEXT, b""), fields.get(TAG_SOURCE, b""), fields.get(TAG_COMMENT, b""))
        out.append((h, key, msgs[start:p + 1]))
    return sections, out


def main():
    args = sys.argv[1:]
    base = None
    if "--base" in args:
        i = args.index("--base")
        base = args[i + 1]
        del args[i:i + 2]
    src, out = args
    language, entries = read_ts(src)
    language, numerus = language.encode(), ENGLISH_PLURALS
    if base:
        sections, kept = read_qm(base)
        language = sections.get(TAG_LANGUAGE, language)
        numerus = sections.get(TAG_NUMERUS_RULES, numerus)
        ours = {key for _, key, _ in entries}
        entries += [e for e in kept if e[1] not in ours]
    messages = bytearray()
    hashes = []
    for h, _, record in entries:
        hashes.append((h, len(messages)))
        messages += record
    hashes.sort()
    table = b"".join(struct.pack(">II", h, o) for h, o in hashes)
    with open(out, "wb") as f:
        f.write(MAGIC + field(TAG_LANGUAGE, language) + field(TAG_NUMERUS_RULES, numerus)
                + field(TAG_HASHES, table) + field(TAG_MESSAGES, bytes(messages)))


if __name__ == "__main__":
    main()
