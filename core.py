"""Zápis značky AI do metadát obrázkov (JPEG, PNG, WebP) bez zásahu do obrazových dát.

Značka sa zapisuje do XMP:
  Iptc4xmpExt:DigitalSourceType  – strojová značka IPTC (čítajú ju Meta, Google…)
  dc:subject                      – kľúčové slovo, napr. „Generated AI“ (Windows: Značky)
  dc:description                  – popis „Generated AI“, ak obrázok ešte žiadny popis nemá
  Iptc4xmpExt:AISystemUsed        – názov AI nástroja (voliteľné)
Všetky ostatné bajty súboru (pixely, EXIF, farebný profil) ostávajú nezmenené.
"""
import io
import re
import struct
import xml.etree.ElementTree as ET
import zlib

NS = {
    "x": "adobe:ns:meta/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "Iptc4xmpExt": "http://iptc.org/std/Iptc4xmpExt/2008-02-29/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "photoshop": "http://ns.adobe.com/photoshop/1.0/",
    "tiff": "http://ns.adobe.com/tiff/1.0/",
    "exif": "http://ns.adobe.com/exif/1.0/",
    "xmpMM": "http://ns.adobe.com/xap/1.0/mm/",
    "stEvt": "http://ns.adobe.com/xap/1.0/sType/ResourceEvent#",
    "xmpRights": "http://ns.adobe.com/xap/1.0/rights/",
}
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
DST_BASE = "http://cv.iptc.org/newscodes/digitalsourcetype/"
TYPES = {
    "trainedAlgorithmicMedia": "Celý obrázok vygenerovala AI",
    "compositeWithTrainedAlgorithmicMedia": "Reálna fotka upravená pomocou AI",
}
DEFAULT_LABEL = "Generated AI"


def _q(prefix, name):
    return "{%s}%s" % (NS[prefix], name)


class MarkError(Exception):
    pass


# ---------------------------------------------------------------- XMP

for _p, _uri in NS.items():
    ET.register_namespace(_p, _uri)


def _register(xmp_text):
    """Zaregistruje prefixy z existujúceho XMP, aby zostali po zápise rovnaké."""
    try:
        for _, (prefix, uri) in ET.iterparse(io.StringIO(xmp_text), events=("start-ns",)):
            if prefix and not re.fullmatch(r"ns\d+", prefix) and uri not in NS.values():
                try:
                    ET.register_namespace(prefix, uri)
                except ValueError:
                    pass
    except ET.ParseError:
        pass


def _parse_xmp(xmp_text):
    """Vráti koreň x:xmpmeta (ElementTree) alebo None, ak sa XMP nedá prečítať."""
    if not xmp_text:
        return None
    _register(xmp_text)
    m = re.search(r"<(\w+:)?xmpmeta\b.*?</(\w+:)?xmpmeta>", xmp_text, re.S)
    body = m.group(0) if m else None
    if body is None:
        m = re.search(r"<rdf:RDF\b.*?</rdf:RDF>", xmp_text, re.S)
        if not m:
            return None
        body = '<x:xmpmeta xmlns:x="%s">%s</x:xmpmeta>' % (NS["x"], m.group(0))
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    if root.find(_q("rdf", "RDF")) is None:
        return None
    return root


def _new_root():
    root = ET.Element(_q("x", "xmpmeta"))
    ET.SubElement(root, _q("rdf", "RDF"))
    return root


def _descriptions(root):
    return root.find(_q("rdf", "RDF")).findall(_q("rdf", "Description"))


def _find_prop(root, prefix, name):
    """Nájde vlastnosť ako podelement; atribútovú formu prevedie na podelement."""
    tag = _q(prefix, name)
    for d in _descriptions(root):
        el = d.find(tag)
        if el is not None:
            return d, el
        if tag in d.attrib:
            val = d.attrib.pop(tag)
            el = ET.SubElement(d, tag)
            el.text = val
            return d, el
    return None, None


def read_ai_info(xmp_text):
    """Prečíta AI polia z XMP – výsledok pre zobrazenie (ako exiftool)."""
    info = {}
    root = _parse_xmp(xmp_text)
    if root is None:
        if xmp_text:
            m = re.search(r"DigitalSourceType\s*=\s*[\"']([^\"']+)", xmp_text) or \
                re.search(r"DigitalSourceType[^>]*>\s*([^<\s]+)", xmp_text)
            if m:
                info["DigitalSourceType"] = m.group(1)
        return info
    for d in _descriptions(root):
        for k, v in d.attrib.items():
            if k == _q("Iptc4xmpExt", "DigitalSourceType"):
                info["DigitalSourceType"] = v
            if k == _q("Iptc4xmpExt", "AISystemUsed"):
                info["AISystemUsed"] = v
        for el in d:
            if el.tag == _q("Iptc4xmpExt", "DigitalSourceType"):
                info["DigitalSourceType"] = (el.text or el.get(_q("rdf", "resource")) or "").strip()
            elif el.tag == _q("Iptc4xmpExt", "AISystemUsed"):
                info["AISystemUsed"] = (el.text or "").strip()
            elif el.tag == _q("dc", "subject"):
                info["Subject"] = [li.text or "" for li in el.iter(_q("rdf", "li"))]
            elif el.tag == _q("dc", "description"):
                lis = [li.text or "" for li in el.iter(_q("rdf", "li"))]
                info["Description"] = lis[0] if lis else (el.text or "")
    return info


def build_xmp(old_xmp, ai_type, label=DEFAULT_LABEL, tool=""):
    root = _parse_xmp(old_xmp) or _new_root()
    rdf = root.find(_q("rdf", "RDF"))
    ours = ET.SubElement(rdf, _q("rdf", "Description"), {_q("rdf", "about"): ""})

    # DigitalSourceType – nastaviť / prepísať
    d, el = _find_prop(root, "Iptc4xmpExt", "DigitalSourceType")
    if el is None:
        el = ET.SubElement(ours, _q("Iptc4xmpExt", "DigitalSourceType"))
    for ch in list(el):
        el.remove(ch)
    el.attrib.pop(_q("rdf", "resource"), None)
    el.text = DST_BASE + ai_type

    if label:
        # dc:subject (Bag) – pridať kľúčové slovo, ak tam ešte nie je
        d, subj = _find_prop(root, "dc", "subject")
        if subj is None:
            subj = ET.SubElement(ours, _q("dc", "subject"))
        bag = subj.find(_q("rdf", "Bag"))
        if bag is None:
            bag = ET.SubElement(subj, _q("rdf", "Bag"))
            if subj.text and subj.text.strip():
                ET.SubElement(bag, _q("rdf", "li")).text = subj.text.strip()
            subj.text = None
        if label not in [li.text for li in bag.findall(_q("rdf", "li"))]:
            ET.SubElement(bag, _q("rdf", "li")).text = label

        # dc:description – len ak chýba (existujúci popis neprepisujeme)
        d, desc = _find_prop(root, "dc", "description")
        if desc is None:
            desc = ET.SubElement(ours, _q("dc", "description"))
            alt = ET.SubElement(desc, _q("rdf", "Alt"))
            ET.SubElement(alt, _q("rdf", "li"), {XML_LANG: "x-default"}).text = label

    if tool:
        d, el = _find_prop(root, "Iptc4xmpExt", "AISystemUsed")
        if el is None:
            el = ET.SubElement(ours, _q("Iptc4xmpExt", "AISystemUsed"))
        el.text = tool

    if len(ours) == 0:
        rdf.remove(ours)
    ET.indent(root, space=" ")
    body = ET.tostring(root, encoding="unicode")
    return ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
            + body + '\n<?xpacket end="w"?>')


# ---------------------------------------------------------------- JPEG

JPEG_XMP_HDR = b"http://ns.adobe.com/xap/1.0/\x00"


def _scan_jpeg(b):
    if b[:2] != b"\xff\xd8":
        raise MarkError("Súbor nie je platný JPEG.")
    pos, insert_at, leading, seg = 2, 2, True, None
    n = len(b)
    while pos + 4 <= n:
        if b[pos] != 0xFF:
            raise MarkError("JPEG má poškodenú štruktúru hlavičiek.")
        m = b[pos + 1]
        while m == 0xFF and pos + 2 < n:
            pos += 1
            m = b[pos + 1]
        if m in (0xDA, 0xD9):
            break
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            pos += 2
            continue
        length = struct.unpack(">H", b[pos + 2:pos + 4])[0]
        end = pos + 2 + length
        if m == 0xE1 and seg is None and b.startswith(JPEG_XMP_HDR, pos + 4):
            seg = (pos, end)
        if leading and m in (0xE0, 0xE1):
            insert_at = end
        else:
            leading = False
        pos = end
    xmp = b[seg[0] + 4 + len(JPEG_XMP_HDR):seg[1]].decode("utf-8", "replace") if seg else None
    return {"fmt": "JPEG", "xmp": xmp, "seg": seg, "insert_at": insert_at}


def _write_jpeg(b, info, xmp):
    payload = JPEG_XMP_HDR + xmp.encode("utf-8")
    if len(payload) + 2 > 0xFFFF:
        raise MarkError("XMP metadáta sú príliš veľké pre JPEG segment.")
    seg = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    if info["seg"]:
        s, e = info["seg"]
        return b[:s] + seg + b[e:]
    i = info["insert_at"]
    return b[:i] + seg + b[i:]


# ---------------------------------------------------------------- PNG

PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_XMP_KEY = b"XML:com.adobe.xmp"


def _scan_png(b):
    if not b.startswith(PNG_SIG):
        raise MarkError("Súbor nie je platný PNG.")
    pos, ihdr_end, chunk, xmp = 8, None, None, None
    while pos + 12 <= len(b):
        length = struct.unpack(">I", b[pos:pos + 4])[0]
        ctype = b[pos + 4:pos + 8]
        end = pos + 12 + length
        if ctype == b"IHDR":
            ihdr_end = end
        if ctype == b"iTXt" and chunk is None:
            d = b[pos + 8:pos + 8 + length]
            z0 = d.find(b"\x00")
            if d[:z0] == PNG_XMP_KEY:
                comp = d[z0 + 1]
                z1 = d.find(b"\x00", z0 + 3)
                z2 = d.find(b"\x00", z1 + 1)
                text = d[z2 + 1:]
                chunk = (pos, end)
                try:
                    xmp = (zlib.decompress(text) if comp else text).decode("utf-8", "replace")
                except zlib.error:
                    xmp = None
        if ctype == b"IEND":
            break
        pos = end
    if ihdr_end is None:
        raise MarkError("PNG nemá hlavičku IHDR.")
    return {"fmt": "PNG", "xmp": xmp, "chunk": chunk, "insert_at": ihdr_end}


def _write_png(b, info, xmp):
    data = PNG_XMP_KEY + b"\x00\x00\x00\x00\x00" + xmp.encode("utf-8")
    body = b"iTXt" + data
    chunk = struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    if info["chunk"]:
        s, e = info["chunk"]
        return b[:s] + chunk + b[e:]
    i = info["insert_at"]
    return b[:i] + chunk + b[i:]


# ---------------------------------------------------------------- WebP

def _scan_webp(b):
    if b[:4] != b"RIFF" or b[8:12] != b"WEBP":
        raise MarkError("Súbor nie je platný WebP.")
    riff_end = min(len(b), 8 + struct.unpack("<I", b[4:8])[0])
    chunks, pos = [], 12
    while pos + 8 <= riff_end:
        cid = b[pos:pos + 4]
        size = struct.unpack("<I", b[pos + 4:pos + 8])[0]
        end = min(riff_end, pos + 8 + size + (size & 1))
        chunks.append({"id": cid, "start": pos, "end": end, "data": pos + 8, "size": size})
        pos = end
    if not chunks:
        raise MarkError("WebP neobsahuje žiadne dáta.")
    x = next((c for c in chunks if c["id"] == b"XMP "), None)
    xmp = b[x["data"]:x["data"] + x["size"]].decode("utf-8", "replace") if x else None
    return {"fmt": "WEBP", "xmp": xmp, "chunks": chunks, "riff_end": riff_end}


def _webp_chunk(cid, data):
    return cid + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) & 1 else b"")


def _write_webp(b, info, xmp):
    chunks = info["chunks"]
    raw = lambda c: b[c["start"]:c["end"]]
    parts = []
    first = chunks[0]
    if first["id"] == b"VP8X":
        v = bytearray(raw(first))
        v[8] |= 0x04  # príznak XMP
        parts.append(bytes(v))
    else:
        d = b[first["data"]:first["data"] + first["size"]]
        flags = 0x04
        if first["id"] == b"VP8L":
            bits = struct.unpack("<I", d[1:5])[0]
            w, h = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            if (bits >> 28) & 1:
                flags |= 0x10
        elif first["id"] == b"VP8 ":
            w = struct.unpack("<H", d[6:8])[0] & 0x3FFF
            h = struct.unpack("<H", d[8:10])[0] & 0x3FFF
        else:
            raise MarkError("Neznámy formát WebP.")
        vx = bytes([flags, 0, 0, 0]) + (w - 1).to_bytes(3, "little") + (h - 1).to_bytes(3, "little")
        parts.append(_webp_chunk(b"VP8X", vx))
        parts.append(raw(first))
    parts += [raw(c) for c in chunks[1:] if c["id"] != b"XMP "]
    parts.append(_webp_chunk(b"XMP ", xmp.encode("utf-8")))
    body = b"".join(parts)
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WEBP" + body + b[info["riff_end"]:]


# ---------------------------------------------------------------- verejné API

def scan(data):
    if data[:2] == b"\xff\xd8":
        return _scan_jpeg(data)
    if data.startswith(PNG_SIG):
        return _scan_png(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _scan_webp(data)
    raise MarkError("Nepodporovaný formát. Podporované sú JPG, PNG a WebP.")


def mark(data, ai_type="trainedAlgorithmicMedia", label=DEFAULT_LABEL, tool=""):
    """Vráti bajty obrázka so zapísanou značkou AI."""
    if ai_type not in TYPES:
        raise MarkError("Neznámy typ označenia.")
    info = scan(data)
    xmp = build_xmp(info["xmp"], ai_type, label.strip(), tool.strip())
    if info["fmt"] == "JPEG":
        return _write_jpeg(data, info, xmp)
    if info["fmt"] == "PNG":
        return _write_png(data, info, xmp)
    return _write_webp(data, info, xmp)


def describe(data):
    """Prehľad AI metadát v štýle exiftool: zoznam (názov poľa, hodnota)."""
    info = scan(data)
    ai = read_ai_info(info["xmp"])
    rows = [("File Type", info["fmt"])]
    if "DigitalSourceType" in ai:
        rows.append(("Digital Source Type", ai["DigitalSourceType"]))
    if ai.get("Subject"):
        rows.append(("Subject", ", ".join(ai["Subject"])))
    if ai.get("Description"):
        rows.append(("Description", ai["Description"]))
    if ai.get("AISystemUsed"):
        rows.append(("AI System Used", ai["AISystemUsed"]))
    return rows, info["xmp"] or ""


def ai_label(data):
    """Krátky popis stavu značky AI v súbore, alebo None."""
    ai = read_ai_info(scan(data)["xmp"])
    dst = ai.get("DigitalSourceType", "")
    if not dst:
        return None
    key = dst.rsplit("/", 1)[-1]
    return {"trainedAlgorithmicMedia": "vygenerované AI",
            "compositeWithTrainedAlgorithmicMedia": "upravené AI"}.get(key, key)
