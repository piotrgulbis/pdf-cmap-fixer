import pikepdf

FONT_PROGRAM_KEYS: tuple[tuple[str, str], ...] = (
    ("/FontFile2", "TrueType"),
    ("/FontFile3", "CFF/OpenType"),
    ("/FontFile", "Type1"),
)


def font_program_stream(font_obj: pikepdf.Object) -> tuple[pikepdf.Object | None, str | None]:
    # Type0 composite fonts wrap a CIDFont descendant; the descriptor and embedded
    # program live on the descendant, not the wrapper.
    descriptor = font_obj.get("/FontDescriptor")
    if descriptor is None and font_obj.get("/Subtype") == "/Type0":
        descendants = font_obj.get("/DescendantFonts")
        if descendants:
            descriptor = descendants[0].get("/FontDescriptor")
    if descriptor is None:
        return None, None
    for key, kind in FONT_PROGRAM_KEYS:
        if key in descriptor:
            return descriptor[key], kind
    return None, None
