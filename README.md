# pdf-cmap-fixer

Repairs broken `ToUnicode` CMaps in PDFs.

## The problem

A PDF stores text as two parallel things:

1. Glyph shapes and positions used to draw the page (this is what gets printed/displayed).
2. A `ToUnicode` CMap that tells text extractors which character each glyph represents (this is what `Ctrl+C`, search, screen readers, and "PDF to text" tools read).

When (2) is broken or missing — common with custom decorative fonts, small caps, ligatures, and certain export pipelines — the PDF looks correct but text extraction returns garbage like `Dif7iculty`, `C������� Y��� S�������`, or invisible characters.

This tool rebuilds correct `ToUnicode` CMaps by reading the glyph names from the embedded font files. Where glyph names alone aren't enough (typically Private Use Area glyphs used for stylistic variants like small caps), it renders the glyphs to images so a human can identify them, then merges those manual mappings into the fix.

## Install

Requires Python 3.12+. With [uv](https://docs.astral.sh/uv/):

```
uv sync
```

Or with pip:

```
pip install -e .
```

After install, the four scripts are also reachable as console commands:
`pdf-cmap-inspect`, `pdf-cmap-extract`, `pdf-cmap-render-pua`, `pdf-cmap-fix`.

## Workflow

### 1. Diagnose

See which fonts have broken extraction:

```
uv run inspect_fonts.py input.pdf
```

This walks every text span, looks for replacement characters and Private Use Area codepoints, and reports per-font how many spans extract incorrectly. Fonts with a high "Ratio" are your culprits.

Optionally inspect embedded font internals:

```
uv run extract_fonts.py input.pdf
```

Dumps each embedded font into `fonts/` and reports glyph-name coverage. Fonts where most glyphs have meaningful names (e.g. `'A'`, `'space'`, `'period'`) can be auto-fixed; glyphs named `uniE005` etc. live in Private Use Area and need manual identification.

### 2. Auto-fix

```
uv run fix_pdf_fonts.py input.pdf -o input_fixed.pdf
```

Builds a corrected `ToUnicode` CMap for each font from its glyph names and writes a new PDF. Reports `mapped X/Y glyphs` per font. This usually recovers most of the broken text immediately.

Use `--dry-run` to print the per-font summary without writing anything — useful for previewing a `--mapping` file before committing to it.

If `inspect_fonts.py` on `input_fixed.pdf` reports zero broken spans, you're done.

### 3. Manual identification (when needed)

If broken text remains, it's usually small caps or stylistic variants stored as Private Use Area glyphs. The fix always reads from the **original** PDF (the embedded fonts are the same in the original and the auto-fixed copy, and the fix builds CMaps from scratch — fixes don't get layered on top of each other). Generate identification grids from the original:

```
uv run render_pua_glyphs.py input.pdf
```

This produces:

- `pua_glyphs/<FontName>.png` — one image per font, with each unmapped glyph rendered at 64px and labeled with its GID.
- `pua_mapping.txt` — a fill-in-the-blank template, one line per glyph.

Open the PNG grids, identify each glyph, and edit `pua_mapping.txt`:

```
ABCDEF+SomeFont 0x0002 = n
ABCDEF+SomeFont 0x0003 = t
ABCDEF+SomeFont 0x0004 = r
```

For symbol fonts (Wingdings etc.) you can map to any Unicode character you'd like, e.g. `= ◆`.

### 4. Re-fix with the manual mapping

Run the fix again on the original PDF — the manual mapping is merged in alongside the auto-derived entries in a single pass:

```
uv run fix_pdf_fonts.py input.pdf -o input_fixed.pdf --mapping pua_mapping.txt
```

The output reports `mapped X/Y glyphs (+N manual)` for fonts that received manual entries. Re-run `inspect_fonts.py input_fixed.pdf` to verify.

## Notes

- The original PDF is never modified. The fix is written to a new file.
- Visual rendering of the PDF is not affected — only the text-extraction layer changes.
- Fonts that fail to load (e.g. CFF/OpenType variants fontTools can't parse) are left untouched. Their original CMaps remain in place.
- Glyphs without a usable mapping (no name and no manual entry) are omitted from the new CMap. Some readers will display the raw character codes for those; others will skip them. Adding them to `pua_mapping.txt` is the fix.
