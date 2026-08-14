#!/usr/bin/env python3
"""Heuristic privacy/secret check for files intended for the public repository."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
from pathlib import Path

TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".js", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"
}
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}
PRIVATE_FILENAMES = {
    "wohnmobil_tours.private.json",
    "secrets.yaml",
    "paj_sync_state.json",
    "wohnmobil_tour_stats.json",
}
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
IP_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
PASSWORD_JSON_RE = re.compile(r'"password"\s*:\s*"([^"]*)"', re.I)
USERNAME_JSON_RE = re.compile(r'"username"\s*:\s*"([^"]*)"', re.I)
COORD_KEY_RE = re.compile(r'"home_(?:latitude|longitude)"\s*:\s*([^,\n}]+)', re.I)


def iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"LICENSE", ".gitignore", ".editorconfig"}:
            yield path


def is_private_ipv4(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
        return isinstance(ip, ipaddress.IPv4Address) and (ip.is_private or ip.is_loopback)
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    findings = []

    for path in root.rglob("*"):
        if path.is_file() and path.name in PRIVATE_FILENAMES:
            findings.append((path, "private/runtime filename is present"))

    for path in iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for email in EMAIL_RE.findall(text):
            if email.lower().endswith("@example.com"):
                continue
            findings.append((path, f"email-like value: {email}"))

        for candidate in IP_RE.findall(text):
            if is_private_ipv4(candidate):
                findings.append((path, f"private/loopback IPv4 address: {candidate}"))

        if path.suffix.lower() == ".json":
            for match in PASSWORD_JSON_RE.finditer(text):
                value = match.group(1).strip()
                if value not in {"", "CHANGE_ME"}:
                    findings.append((path, "non-placeholder JSON password value"))
            for match in USERNAME_JSON_RE.finditer(text):
                value = match.group(1).strip()
                if value not in {"", "CHANGE_ME"}:
                    findings.append((path, "non-placeholder JSON username value"))
            for match in COORD_KEY_RE.finditer(text):
                value = match.group(1).strip().strip('"')
                if value not in {"", "CHANGE_ME", "null"}:
                    findings.append((path, "non-placeholder home coordinate"))

    if findings:
        print("Potential private data found:")
        for path, reason in findings:
            print(f"- {path.relative_to(root)}: {reason}")
        return 1

    print("OK: no obvious private data or credentials found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
