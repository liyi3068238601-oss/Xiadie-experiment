from __future__ import annotations

import pytest

from app.tool_handlers import (
    ToolExecutionError,
    code_inspect,
    document_parse,
    list_dir,
    read_file,
    search,
)


def test_read_file_respects_workspace_boundary(tmp_path) -> None:
    target = tmp_path / "ok.txt"
    target.write_text("hello", encoding="utf-8")
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("no", encoding="utf-8")
    handler = read_file()
    assert handler({"path": "ok.txt"}, workspace=tmp_path)["content"] == "hello"
    with pytest.raises(ToolExecutionError):
        handler({"path": str(outside)}, workspace=tmp_path)  # 越界
    with pytest.raises(ToolExecutionError):
        handler({"path": "../secret.txt"}, workspace=tmp_path)  # 规范化逃逸


def test_read_file_bounds_lines(tmp_path) -> None:
    big = tmp_path / "big.txt"
    big.write_text("\n".join(f"line {i}" for i in range(30000)), encoding="utf-8")
    with pytest.raises(ToolExecutionError):
        read_file()({"path": "big.txt"}, workspace=tmp_path)


def test_search_finds_matches_bounded(tmp_path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n# TODO fix\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("y = 2\n# TODO later\n", encoding="utf-8")
    result = search()({"query": "TODO"}, workspace=tmp_path)
    assert len(result["matches"]) == 2
    assert result["matches"][0]["path"].endswith("a.py")


def test_list_dir_single_level(tmp_path) -> None:
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    (tmp_path / "d").mkdir()
    result = list_dir()({"path": "."}, workspace=tmp_path)
    names = {item["name"] for item in result["items"]}
    assert names == {"f.txt", "d"}


def test_document_parse_text_and_markdown(tmp_path) -> None:
    md = tmp_path / "note.md"
    md.write_text("# 标题\n正文内容", encoding="utf-8")
    result = document_parse()({"path": "note.md"}, workspace=tmp_path)
    assert "标题" in result["summary"]
    assert result["headings"][0]["title"] == "标题"


def test_code_inspect_detects_syntax_error(tmp_path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(:\n", encoding="utf-8")
    result = code_inspect()({"path": "bad.py"}, workspace=tmp_path)
    assert result["ok"] is False
    assert "syntax" in result["error"].lower()
    good = tmp_path / "good.py"
    good.write_text("def f():\n    return 1\n", encoding="utf-8")
    ok = code_inspect()({"path": "good.py"}, workspace=tmp_path)
    assert ok["ok"] is True
    assert "f" in ok["symbols"]
