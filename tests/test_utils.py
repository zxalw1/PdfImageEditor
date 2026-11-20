# -*- coding: utf-8 -*-
import os

import pytest

from app.core.utils import parse_ranges, human, unique_path, collect_files, out_path, with_ext


def test_parse_ranges():
    assert parse_ranges("1-3,5,7-", 9) == [[0, 1, 2], [4], [6, 7, 8]]
    assert parse_ranges("-2", 5) == [[0, 1]]
    assert parse_ranges("2 4", 5) == [[1], [3]]
    assert parse_ranges("1-100", 3) == [[0, 1, 2]]


@pytest.mark.parametrize("bad", ["abc", "5-2", "9"])
def test_parse_ranges_invalid(bad):
    with pytest.raises(ValueError):
        parse_ranges(bad, 5)


def test_human():
    assert human(500) == "500B"
    assert human(2048) == "2.0KB"
    assert human(5 * 1024 * 1024) == "5.0MB"


def test_unique_path(tmp_path):
    p = tmp_path / "a.pdf"
    assert unique_path(str(p)) == str(p)
    p.write_bytes(b"x")
    assert unique_path(str(p)) == str(tmp_path / "a_1.pdf")


def test_collect_files(tmp_path):
    (tmp_path / "b.jpg").write_bytes(b"")
    (tmp_path / "a.png").write_bytes(b"")
    (tmp_path / "c.txt").write_bytes(b"")
    got = collect_files([str(tmp_path)], {'.jpg', '.png'})
    assert [os.path.basename(x) for x in got] == ["a.png", "b.jpg"]


def test_out_path_and_ext(tmp_path):
    src = tmp_path / "doc.xlsx"
    src.write_bytes(b"")
    d = out_path(str(src), "", ".pdf")
    assert d == str(tmp_path / "변환" / "doc.pdf")
    assert os.path.isdir(tmp_path / "변환")
    assert with_ext("a", ".pdf") == "a.pdf"
    assert with_ext("a.PDF", ".pdf") == "a.PDF"
