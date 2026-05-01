import argparse
import io
from pathlib import Path

import pikepdf
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

from _pdf_utils import font_program_stream

CELL = 96
LABEL_H = 22
COLS = 8
PAD = 4


UNI_PREFIX_LEN = 3  # length of the "uni" prefix in uniXXXX glyph names


def pua_codepoints(name: str) -> list[int] | None:
    """Codepoints encoded in an Adobe-style glyph name, if all are in the PUA.

    Recognizes uXXXX, uniXXXX, and multi-codepoint uniXXXXYYYY... ligatures.
    Returns None if the name isn't one of those forms or any codepoint falls
    outside the BMP PUA range.
    """
    if name.startswith("uni") and len(name) > UNI_PREFIX_LEN and (len(name) - UNI_PREFIX_LEN) % 4 == 0:
        try:
            cps = [int(name[i : i + 4], 16) for i in range(UNI_PREFIX_LEN, len(name), 4)]
        except ValueError:
            return None
    elif name.startswith("u") and 5 <= len(name) <= 7:
        try:
            cps = [int(name[1:], 16)]
        except ValueError:
            return None
    else:
        return None
    if not all(0xE000 <= cp <= 0xF8FF for cp in cps):
        return None
    return cps


def is_pua_name(name: str) -> bool:
    return pua_codepoints(name) is not None


def render_glyph(ttf_bytes: bytes, text: str, size: int = 64) -> Image.Image:
    cell = Image.new("RGB", (CELL, CELL), "white")
    draw = ImageDraw.Draw(cell)
    try:
        pil_font = ImageFont.truetype(io.BytesIO(ttf_bytes), size=size)
        bbox = draw.textbbox((0, 0), text, font=pil_font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (CELL - w) // 2 - bbox[0]
        y = (CELL - h) // 2 - bbox[1]
        draw.text((x, y), text, font=pil_font, fill="black")
    except Exception as exc:
        draw.text((4, 4), f"err\n{exc.__class__.__name__}", fill="red")
    return cell


def make_grid(font_name: str, items: list[tuple[int, str]], ttf_bytes: bytes) -> Image.Image:
    rows = (len(items) + COLS - 1) // COLS
    grid_w = COLS * (CELL + PAD) + PAD
    grid_h = rows * (CELL + LABEL_H + PAD) + PAD + 30
    img = Image.new("RGB", (grid_w, grid_h), "white")
    draw = ImageDraw.Draw(img)
    try:
        title_font = ImageFont.load_default()
    except Exception:
        title_font = None
    draw.text((PAD, 6), font_name, fill="black", font=title_font)

    for i, (gid, name) in enumerate(items):
        col = i % COLS
        row = i // COLS
        x = PAD + col * (CELL + PAD)
        y = 30 + row * (CELL + LABEL_H + PAD)
        cps = pua_codepoints(name)
        if cps:
            cell = render_glyph(ttf_bytes, "".join(chr(cp) for cp in cps))
        else:
            cell = Image.new("RGB", (CELL, CELL), "lightgray")
        img.paste(cell, (x, y))
        label = f"GID {gid:#06x}"
        draw.text((x + 4, y + CELL + 2), label, fill="black", font=title_font)

    return img


def main() -> None:
    parser = argparse.ArgumentParser(description="Render PUA-named glyphs from a PDF for visual identification.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, default=Path("pua_glyphs"), help="Output directory.")
    parser.add_argument("--mapping", type=Path, default=Path("pua_mapping.txt"), help="Output mapping template.")
    args = parser.parse_args()

    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")
    args.out.mkdir(parents=True, exist_ok=True)

    template_lines = [
        "# Fill in the letter (or letters) each PUA glyph represents.",
        "# Lines are: <font_name> <gid_hex> = <character>",
        "# Leave the right side empty to skip a glyph.",
        "# Open the rendered grid images in the pua_glyphs/ directory to identify each glyph.",
        "",
    ]

    seen: set[int] = set()
    with pikepdf.open(args.pdf) as pdf:
        for obj in pdf.objects:
            if not isinstance(obj, pikepdf.Dictionary):
                continue
            if obj.get("/Type") != "/Font":
                continue
            if obj.get("/Subtype") in ("/CIDFontType0", "/CIDFontType2"):
                continue
            obj_id = obj.objgen[0]
            if obj_id in seen:
                continue
            seen.add(obj_id)

            name = str(obj.get("/BaseFont") or obj.get("/FontName") or "<unnamed>").lstrip("/")
            stream, _ = font_program_stream(obj)
            if stream is None:
                continue
            ttf_bytes = stream.read_bytes()
            try:
                tt = TTFont(io.BytesIO(ttf_bytes))
            except Exception:
                continue

            glyph_order = tt.getGlyphOrder()
            pua_items = [(gid, gname) for gid, gname in enumerate(glyph_order) if is_pua_name(gname)]
            if not pua_items:
                continue

            grid = make_grid(name, pua_items, ttf_bytes)
            grid_path = args.out / f"{name}.png"
            grid.save(grid_path)
            print(f"  {name}: {len(pua_items)} PUA glyphs -> {grid_path}")

            template_lines.append(f"# {name} ({len(pua_items)} glyphs) - see {grid_path.name}")
            for gid, _ in pua_items:
                template_lines.append(f"{name} {gid:#06x} = ")
            template_lines.append("")

    args.mapping.write_text("\n".join(template_lines), encoding="utf-8")
    print(f"\nWrote mapping template to {args.mapping}")


if __name__ == "__main__":
    main()
