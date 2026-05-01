import argparse
import io
from collections import defaultdict
from pathlib import Path

import pikepdf
from fontTools import agl
from fontTools.ttLib import TTFont

from _pdf_utils import font_program_stream


def name_to_unicode(name: str) -> str | None:
    if not name or name in {".notdef", ".null"} or name.startswith("glyph"):
        return None
    if name.startswith("uni") and len(name) > 3 and (len(name) - 3) % 4 == 0:
        try:
            return "".join(chr(int(name[i : i + 4], 16)) for i in range(3, len(name), 4))
        except ValueError:
            return None
    if name.startswith("u") and 5 <= len(name) <= 7:
        try:
            return chr(int(name[1:], 16))
        except ValueError:
            return None
    return agl.toUnicode(name) or None


def is_all_pua(s: str) -> bool:
    return bool(s) and all(0xE000 <= ord(c) <= 0xF8FF for c in s)


def parse_mapping_file(path: Path) -> dict[str, dict[int, str]]:
    result: dict[str, dict[int, str]] = defaultdict(dict)
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        left, right = line.split("=", 1)
        ch = right.strip()
        if not ch:
            continue
        parts = left.split()
        if len(parts) < 2:
            continue
        font_name = parts[0]
        try:
            gid = int(parts[1], 0)
        except ValueError:
            continue
        result[font_name][gid] = ch
    return result


def build_cmap(glyph_names: list[str], overrides: dict[int, str] | None = None) -> tuple[str, int, int]:
    overrides = overrides or {}
    entries: list[tuple[str, str]] = []
    override_count = 0
    for gid, name in enumerate(glyph_names):
        is_override = gid in overrides
        if is_override:
            u = overrides[gid]
        else:
            u = name_to_unicode(name)
            if not u or is_all_pua(u):
                continue
        if not u:
            continue
        if is_override:
            override_count += 1
        cid_hex = f"{gid:04X}"
        unicode_hex = "".join(f"{ord(c):04X}" for c in u)
        entries.append((cid_hex, unicode_hex))

    lines = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo",
        "<< /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        "/CMapName /Adobe-Identity-UCS def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<0000> <FFFF>",
        "endcodespacerange",
    ]
    for i in range(0, len(entries), 100):
        chunk = entries[i : i + 100]
        lines.append(f"{len(chunk)} beginbfchar")
        for cid, u in chunk:
            lines.append(f"<{cid}> <{u}>")
        lines.append("endbfchar")
    lines += [
        "endcmap",
        "CMapName currentdict /CMap defineresource pop",
        "end",
        "end",
    ]
    return "\n".join(lines), len(entries), override_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject corrected ToUnicode CMaps from glyph names.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="Output PDF path. Required unless --dry-run.")
    parser.add_argument("--mapping", type=Path, default=None, help="Manual PUA-glyph mapping file.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the per-font summary without writing an output PDF.",
    )
    args = parser.parse_args()

    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")
    if not args.dry_run and args.output is None:
        parser.error("-o/--output is required unless --dry-run is set")

    manual: dict[str, dict[int, str]] = {}
    if args.mapping and args.mapping.is_file():
        manual = parse_mapping_file(args.mapping)
        total = sum(len(v) for v in manual.values())
        print(f"Loaded {total} manual glyph mappings across {len(manual)} fonts.\n")

    seen: set[int] = set()
    with pikepdf.open(args.pdf) as pdf:
        for obj in pdf.objects:
            if not isinstance(obj, pikepdf.Dictionary):
                continue
            if obj.get("/Type") != "/Font":
                continue
            subtype = obj.get("/Subtype")
            # Skip CIDFont descendants: ToUnicode lives on the Type0 wrapper that
            # references them, and we'll process that wrapper on its own iteration.
            if subtype in ("/CIDFontType0", "/CIDFontType2"):
                continue
            obj_id = obj.objgen[0]
            if obj_id in seen:
                continue
            seen.add(obj_id)

            name = str(obj.get("/BaseFont") or obj.get("/FontName") or "<unnamed>").lstrip("/")
            stream, _ = font_program_stream(obj)
            if stream is None:
                print(f"  {name}: skipped (no embedded program)")
                continue

            try:
                tt = TTFont(io.BytesIO(stream.read_bytes()))
            except Exception as exc:
                print(f"  {name}: skipped ({exc})")
                continue

            glyph_names = tt.getGlyphOrder()
            overrides = manual.get(name, {})
            cmap_content, mapped, manual_used = build_cmap(glyph_names, overrides)
            if mapped == 0:
                print(f"  {name}: no mappable glyph names — left untouched")
                continue

            if not args.dry_run:
                # CMap syntax is pure ASCII (PDF spec §10.8); encode as ascii to
                # catch any accidental non-ASCII content early rather than silently.
                new_stream = pdf.make_stream(cmap_content.encode("ascii"))
                obj["/ToUnicode"] = new_stream
            extra = f" (+{manual_used} manual)" if manual_used else ""
            print(f"  {name}: mapped {mapped}/{len(glyph_names)} glyphs{extra}")

        if args.dry_run:
            print("\nDry run — no output written.")
        else:
            pdf.save(args.output)
            print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
