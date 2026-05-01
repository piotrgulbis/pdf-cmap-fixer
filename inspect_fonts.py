import argparse
from collections import defaultdict
from pathlib import Path

import pymupdf


def is_suspicious(char: str) -> bool:
    code = ord(char)
    if char == "�":
        return True
    if 0xE000 <= code <= 0xF8FF:
        return True
    if 0xF0000 <= code <= 0xFFFFD:
        return True
    if 0x100000 <= code <= 0x10FFFD:
        return True
    return False


def span_is_broken(text: str) -> bool:
    return any(is_suspicious(c) for c in text)


def inspect(pdf_path: Path, examples_per_font: int) -> None:
    broken_counts: dict[str, int] = defaultdict(int)
    total_counts: dict[str, int] = defaultdict(int)
    examples: dict[str, list[tuple[int, str]]] = defaultdict(list)

    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        font = span.get("font", "<unknown>")
                        text = span.get("text", "")
                        if not text.strip():
                            continue
                        total_counts[font] += 1
                        if span_is_broken(text):
                            broken_counts[font] += 1
                            if len(examples[font]) < examples_per_font:
                                examples[font].append((page.number, text))

    print(f"{'Font':<45} {'Broken':>8} {'Total':>8} {'Ratio':>8}")
    print("-" * 71)
    fonts = sorted(total_counts, key=lambda f: broken_counts[f], reverse=True)
    for font in fonts:
        broken = broken_counts[font]
        total = total_counts[font]
        ratio = broken / total if total else 0
        print(f"{font:<45} {broken:>8} {total:>8} {ratio:>7.1%}")

    print()
    for font in fonts:
        if not examples[font]:
            continue
        print(f"=== {font} ===")
        for page_num, text in examples[font]:
            print(f"  page {page_num}: {text!r}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Find fonts with broken ToUnicode mappings.")
    parser.add_argument("pdf", type=Path, help="Path to the input PDF file.")
    parser.add_argument(
        "--examples",
        type=int,
        default=3,
        help="Number of example broken spans to show per font (default: 3).",
    )
    args = parser.parse_args()

    if not args.pdf.is_file():
        parser.error(f"PDF not found: {args.pdf}")

    inspect(args.pdf, args.examples)


if __name__ == "__main__":
    main()
