#!/usr/bin/env python3
"""Compile a small Qt .ts translation into a .qm file, like lrelease: ts2qm.py IN.ts OUT.qm

Only what QTranslator needs to look messages up: the hash table, the messages and the
English plural rule."""
import struct
import sys
import xml.etree.ElementTree as ET

MAGIC = bytes([0x3C, 0xB8, 0x64, 0x18, 0xCA, 0xEF, 0x9C, 0x95, 0xCD, 0x21, 0x1C, 0xBF, 0x60, 0xA1, 0xBD, 0xDD])
TAG_HASHES, TAG_MESSAGES, TAG_NUMERUS_RULES, TAG_LANGUAGE = 0x42, 0x69, 0x88, 0xA7
TAG_END, TAG_TRANSLATION, TAG_SOURCE, TAG_CONTEXT, TAG_COMMENT = 1, 3, 6, 7, 8
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


def main():
    src, out = sys.argv[1:3]
    root = ET.parse(src).getroot()
    messages = bytearray()
    hashes = []
    for ctx in root.findall("context"):
        context = (ctx.findtext("name") or "").encode()
        for msg in ctx.findall("message"):
            source = (msg.findtext("source") or "").encode()
            comment = (msg.findtext("comment") or "").encode()
            tr = msg.find("translation")
            forms = [f.text or "" for f in tr.findall("numerusform")] if msg.get("numerus") == "yes" \
                else [tr.text or ""]
            hashes.append((elf_hash(source + comment), len(messages)))
            for text in forms:
                messages += field(TAG_TRANSLATION, text.encode("utf-16-be"))
            messages += field(TAG_SOURCE, source) + field(TAG_CONTEXT, context)
            messages += field(TAG_COMMENT, comment) + bytes([TAG_END])
    hashes.sort()
    table = b"".join(struct.pack(">II", h, o) for h, o in hashes)
    language = (root.get("language") or "en").encode()
    with open(out, "wb") as f:
        f.write(MAGIC + field(TAG_LANGUAGE, language) + field(TAG_NUMERUS_RULES, ENGLISH_PLURALS)
                + field(TAG_HASHES, table) + field(TAG_MESSAGES, bytes(messages)))


if __name__ == "__main__":
    main()
