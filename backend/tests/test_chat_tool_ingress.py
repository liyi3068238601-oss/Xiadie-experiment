from __future__ import annotations

from pathlib import Path

from app.chat_tool_ingress import match_tool_intent, run_readonly


def test_match_read_and_search_intents() -> None:
    assert match_tool_intent("帮我读一下 README.md") == ("workspace.read_file", {"path": "README.md"})
    assert match_tool_intent("搜索一下 TODO 在哪") == ("workspace.search", {"query": "TODO"})
    assert match_tool_intent("今天天气如何") is None
    assert match_tool_intent("读 README.md 给我看看") == ("workspace.read_file", {"path": "README.md"})


def test_run_readonly_executes_via_registry(tmp_path) -> None:
    target = tmp_path / "note.txt"
    target.write_text("hello tools", encoding="utf-8")
    result = run_readonly("帮我读一下 note.txt", workspace=tmp_path)
    assert result is not None
    assert "hello tools" in result["summary"]


def test_run_readonly_returns_none_on_unknown_intent() -> None:
    assert run_readonly("今天聊点什么", workspace=Path(".")) is None
