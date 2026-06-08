from pathlib import Path

from fix_pdf_fonts import build_cmap, is_all_pua, name_to_unicode, parse_mapping_file


def test_name_to_unicode_handles_common_glyph_name_formats() -> None:
    assert name_to_unicode("uni00410042") == "AB"
    assert name_to_unicode("u1F600") == "\U0001f600"
    assert name_to_unicode("f_f_i") == "ffi"
    assert name_to_unicode("space") == " "


def test_name_to_unicode_rejects_unusable_or_malformed_names() -> None:
    assert name_to_unicode("") is None
    assert name_to_unicode(".notdef") is None
    assert name_to_unicode("glyph00001") is None
    assert name_to_unicode("uni004Z") is None
    assert name_to_unicode("uXYZ") is None


def test_is_all_pua_only_accepts_non_empty_private_use_strings() -> None:
    assert is_all_pua("\ue000\uf8ff")
    assert not is_all_pua("")
    assert not is_all_pua("\ue000A")


def test_parse_mapping_file_ignores_comments_blanks_and_malformed_rows(tmp_path: Path) -> None:
    mapping_file = tmp_path / "pua_mapping.txt"
    mapping_file.write_text(
        "\n".join(
            [
                "# Font GID mappings",
                "",
                "ABCDEF+SomeFont 0x0002 = n",
                "ABCDEF+SomeFont 3 = t",
                "ABCDEF+SomeFont not-a-gid = x",
                "ABCDEF+SomeFont 4 = ",
                "missing-gid = y",
                "not a mapping line",
            ]
        ),
        encoding="utf-8",
    )

    assert parse_mapping_file(mapping_file) == {
        "ABCDEF+SomeFont": {
            2: "n",
            3: "t",
        }
    }


def test_build_cmap_filters_pua_names_and_counts_overrides() -> None:
    cmap, mapped, override_count = build_cmap(
        [".notdef", "A", "uniE000", "glyph00003", "f_f_i"],
        overrides={2: "B", 3: ""},
    )

    assert mapped == 3
    assert override_count == 1
    assert "<0001> <0041>" in cmap
    assert "<0002> <0042>" in cmap
    assert "<0004> <006600660069>" in cmap
    assert "<0003>" not in cmap
    assert "beginbfchar" in cmap
    assert cmap.endswith("end")


def test_build_cmap_splits_large_outputs_into_100_entry_chunks() -> None:
    glyph_names = ["A"] * 101

    cmap, mapped, override_count = build_cmap(glyph_names)

    assert mapped == 101
    assert override_count == 0
    assert "100 beginbfchar" in cmap
    assert "1 beginbfchar" in cmap
    assert "<0064> <0041>" in cmap
