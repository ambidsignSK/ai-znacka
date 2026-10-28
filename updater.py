"""Kontrola a inštalácia novej verzie z GitHub Releases (verejný repozitár)."""
import json
import os
import subprocess
import sys
import urllib.request

REPO = "ambidsignSK/ai-znacka"
ASSET = "AI-znacka.exe"
API = f"https://api.github.com/repos/{REPO}/releases/latest"


def is_exe():
    return getattr(sys, "frozen", False)


def latest():
    """Vráti (číslo verzie, URL na stiahnutie) najnovšieho vydania."""
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "AI-znacka"})
    with urllib.request.urlopen(req, timeout=15) as r:
        rel = json.load(r)
    num = int("".join(ch for ch in rel.get("tag_name", "") if ch.isdigit()) or 0)
    url = next((a["browser_download_url"] for a in rel.get("assets", []) if a["name"] == ASSET), None)
    return num, url


def download(url, progress=None):
    """Stiahne novú verziu vedľa bežiaceho .exe a vráti jej cestu."""
    target = sys.executable + ".new"
    req = urllib.request.Request(url, headers={"User-Agent": "AI-znacka"})
    with urllib.request.urlopen(req, timeout=60) as r, open(target, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(256 * 1024):
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done * 100 // total)
    with open(target, "rb") as f:
        if f.read(2) != b"MZ":
            os.remove(target)
            raise RuntimeError("Stiahnutý súbor nie je platný program.")
    return target


def install_and_restart(new_path):
    """Bežiaci .exe sa nedá prepísať, ale dá sa premenovať – starý odložíme a spustíme nový."""
    exe = sys.executable
    old = exe + ".old"
    if os.path.exists(old):
        os.remove(old)
    os.replace(exe, old)
    os.replace(new_path, exe)
    subprocess.Popen([exe], close_fds=True)


def cleanup():
    """Po reštarte zmaže odloženú starú verziu."""
    if is_exe():
        for suffix in (".old", ".new"):
            try:
                os.remove(sys.executable + suffix)
            except OSError:
                pass
