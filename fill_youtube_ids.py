#!/usr/bin/env python3
"""Fill the Fashion & Textile cards from a CSV with columns video_id,youtube_id.

Usage: python fill_youtube_ids.py youtube_ids.csv [--check]
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

CARD_RE = re.compile(rb'<div\b[^>]*>', re.IGNORECASE)
CLASS_RE = re.compile(rb'\bclass="([^"]*)"', re.IGNORECASE)
LABEL_RE = re.compile(rb'\baria-label="YouTube placeholder for (Y[0-9]+)"', re.IGNORECASE)
DATA_RE = re.compile(rb'\bdata-youtube-id="[^"]*"', re.IGNORECASE)
POSTER_RE = re.compile(rb'\bdata-poster="[^"]+"', re.IGNORECASE)
VIDEO_ID_RE = re.compile(r'^Y[0-9]+$')
YOUTUBE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{6,}$')


def load_mapping(path: Path) -> dict[str, str]:
    with path.open('r', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'video_id', 'youtube_id'}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError('CSV header must include video_id,youtube_id')
        mapping: dict[str, str] = {}
        for line, row in enumerate(reader, 2):
            video_id = (row.get('video_id') or '').strip().upper()
            youtube_id = (row.get('youtube_id') or '').strip()
            if not VIDEO_ID_RE.fullmatch(video_id):
                raise ValueError(f'line {line}: invalid video_id {video_id!r}')
            if not YOUTUBE_ID_RE.fullmatch(youtube_id):
                raise ValueError(f'line {line}: invalid or blank youtube_id for {video_id}')
            if video_id in mapping:
                raise ValueError(f'line {line}: duplicate video_id {video_id}')
            mapping[video_id] = youtube_id
    return mapping


def fill(html: bytes, mapping: dict[str, str]) -> tuple[bytes, set[str]]:
    found: set[str] = set()
    changed = 0
    parts: list[bytes] = []
    cursor = 0
    for match in CARD_RE.finditer(html):
        tag = match.group(0)
        class_match = CLASS_RE.search(tag)
        if not class_match or b'fashion-card__embed' not in class_match.group(1).split():
            continue
        label = LABEL_RE.search(tag)
        if not label:
            raise ValueError('found a fashion video placeholder without its Y-number aria-label')
        video_id = label.group(1).decode('ascii').upper()
        if video_id in found:
            raise ValueError(f'duplicate website card for {video_id}')
        found.add(video_id)
        if video_id not in mapping:
            continue
        if not DATA_RE.search(tag):
            raise ValueError(f'{video_id} placeholder has no data-youtube-id attribute')
        # Change only the YouTube ID. Keep data-poster intact as the local thumbnail fallback.
        poster = POSTER_RE.search(tag)
        updated_tag = DATA_RE.sub(b'data-youtube-id="' + mapping[video_id].encode('ascii') + b'"', tag, count=1)
        if poster is not None and (POSTER_RE.search(updated_tag) is None or POSTER_RE.search(updated_tag).group(0) != poster.group(0)):
            raise ValueError(f'{video_id} poster fallback was not preserved')
        if updated_tag != tag:
            changed += 1
        parts.extend((html[cursor:match.start()], updated_tag))
        cursor = match.end()
    if not found:
        raise ValueError('no Fashion & Textile video cards were found')
    missing = sorted(found - mapping.keys())
    unknown = sorted(mapping.keys() - found)
    if missing:
        raise ValueError('CSV is missing video IDs: ' + ', '.join(missing))
    if unknown:
        raise ValueError('CSV contains IDs with no website card: ' + ', '.join(unknown))
    parts.append(html[cursor:])
    return b''.join(parts), found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_file', type=Path, help='CSV with video_id,youtube_id columns')
    parser.add_argument('--html', type=Path, default=Path(__file__).with_name('index.html'), help='HTML file to update (default: index.html beside this script)')
    parser.add_argument('--check', action='store_true', help='Validate the mapping and report changes without writing')
    args = parser.parse_args(argv)
    try:
        mapping = load_mapping(args.csv_file)
        original = args.html.read_bytes()
        updated, found = fill(original, mapping)
        count = sum(1 for video_id in found if mapping[video_id])
        if args.check:
            print(f'CHECK OK: {count} YouTube IDs match {len(found)} fashion cards; file unchanged.')
        elif updated != original:
            args.html.write_bytes(updated)
            print(f'Updated {count} YouTube IDs in {args.html}.')
        else:
            print(f'No changes: {count} YouTube IDs already match {args.html}.')
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f'fill_youtube_ids: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
