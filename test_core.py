"""Test: značka AI sa zapíše, pixely a EXIF ostanú nezmenené. Voliteľne overí exiftoolom."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

import core

tmp = tempfile.mkdtemp()
a = (np.random.default_rng(1).random((120, 90, 3)) * 255).astype("uint8")
im = Image.fromarray(a)
exif = Image.Exif()
exif[0x010F] = "Canon"
xmp = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
       b'<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator><rdf:Seq>'
       b'<rdf:li>Tomas</rdf:li></rdf:Seq></dc:creator></rdf:Description></rdf:RDF></x:xmpmeta>')
im.save(f"{tmp}/a.jpg", quality=90, exif=exif.tobytes())
im.save(f"{tmp}/b.jpg", quality=90, xmp=xmp)
im.save(f"{tmp}/c.png")
im.save(f"{tmp}/d.webp", quality=80)
im.save(f"{tmp}/e.webp", lossless=True)
Image.fromarray(np.dstack([a, a[:, :, 0]])).save(f"{tmp}/f.webp", lossless=True)

has_exiftool = shutil.which("exiftool") is not None
failed = False
for name in sorted(os.listdir(tmp)):
    src = open(f"{tmp}/{name}", "rb").read()
    out = core.mark(src, tool="Midjourney")
    dst = f"{tmp}/out_{name}"
    open(dst, "wb").write(out)
    orig, new = Image.open(io.BytesIO(src)), Image.open(io.BytesIO(out))
    checks = {
        "pixely": np.array_equal(np.array(orig), np.array(new)),
        "exif": dict(orig.getexif()) == dict(new.getexif()),
        "znacka": core.ai_label(out) == "vygenerované AI",
        "idempotentne": core.mark(out, tool="Midjourney") == out,
    }
    if has_exiftool:
        meta = json.loads(subprocess.check_output(["exiftool", "-j", "-XMP:all", dst]))[0]
        print(f"  exiftool {name}: " + ", ".join(f"{k}={meta.get(k)}" for k in
              ("DigitalSourceType", "Subject", "Description", "AISystemUsed", "Creator")))
        checks["exiftool"] = (meta.get("Subject") == "Generated AI" and meta.get("Description") == "Generated AI"
                              and "trainedalgorithmicmedia" in str(meta.get("DigitalSourceType")).lower().replace(" ", ""))
    ok = all(checks.values())
    failed |= not ok
    print(("OK   " if ok else "CHYBA"), name, checks)
sys.exit(1 if failed else 0)
