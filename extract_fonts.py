import argparse
import io
from pathlib import Path

import pikepdf
from fontTools.ttLib import TTFont


def font_program_stream(font_obj: pikepdf.Object) -> tuple[pikepdf.Object | None, str]:
    descriptor = font_obj.get("/FontDescriptor")
    if descriptor is None and font_obj.get("/Subtype") == "/Type0":
        descendants = font_obj.get("/DescendantFonts")
        if descendants:
            descriptor = descendants[0].get("/FontDescriptor")

    if descriptor is None:
        return None, "no /FontDescriptor"

    for key, kind in (("/FontFile2", "TrueType"), ("/FontFile3", "CFF/OpenType"), ("/FontFile", "Type1")):
        if key in descriptor:
            return descriptor[key], kind
    return None, "no embedded font program"


def font_name(font_obj: pikepdf.Object) -> str:
    name = font_obj.get("/BaseFont") or font_obj.get("/FontName") or "<unnamed>"
    return str(name).lstrip("/")


def inspect_font(name: str, stream: pikepdf.Object, kind: str, dump_dir: Path) -> None:
    raw = stream.read_bytes()
    suffix = {"TrueType": "ttf", "CFF/OpenType": "otf", "Type1": "pfb"}.get(kind, "bin")
    out_path = dump_dir / f"{name}.{suffix}"
    out_path.write_bytes(raw)

    if kind == "Type1":
        print(f"  saved {out_path.name} ({len(raw)} bytes) — Type1 inspection skipped")
        return

    try:
        tt = TTFont(io.BytesIO(raw))
    except Exception as exc:
        print(f"  saved {out_path.name} ({len(raw)} bytes) — fontTools failed: {exc}")
        return

    glyph_order = tt.getGlyphOrder()
    total = len(glyph_order)
    generic = sum(1 for g in glyph_order if g.startswith("glyph") or g in {".notdef", ".null"})
    named = total - generic
    has_post = "post" in tt
    has_cff = "CFF " in tt or "CFF2" in tt
    has_cmap = "cmap" in tt

    sample = [g for g in glyph_order if not (g.startswith("glyph") or g in {".notdef", ".null"})][:10]

    print(f"  saved {out_path.name} ({len(raw)} bytes)")
    print(
        f"    glyphs: {total}, named: {named} ({named/total:.0%}), "
        f"post: {has_post}, cmap: {has_cmap}, CFF: {has_cff}"
    )
    if sample:
        print(f"    sample names: {sample}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract embedded fonts and report glyph-name coverage.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, default=Path("fonts"), help="Where to dump font files (default: fonts/).")
    args = parser.parse_args()

    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")
    args.out.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    with pikepdf.open(args.pdf) as pdf:
        for obj in pdf.objects:
            if not isinstance(obj, pikepdf.Dictionary):
                continue
            if obj.get("/Type") != "/Font":
                continue
            name = font_name(obj)
            if name in seen:
                continue
            seen.add(name)

            stream, kind = font_program_stream(obj)
            print(f"\n{name}  [{kind}]")
            if stream is None:
                continue
            inspect_font(name, stream, kind, args.out)


if __name__ == "__main__":
    main()
