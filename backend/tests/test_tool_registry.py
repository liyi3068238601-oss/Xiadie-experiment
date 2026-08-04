from __future__ import annotations

import pytest

from app.tool_registry import ToolManifest, ToolRegistry, ToolRegistryError


def test_register_validate_and_reject_unknown() -> None:
    registry = ToolRegistry()
    registry.register(ToolManifest(
        id="workspace.read_file", name="读取文件", description="read",
        input_schema={"type": "object",
                      "properties": {"path": {"type": "string", "maxLength": 400}},
                      "required": ["path"]},
        output_schema={}, side_effect=False, risk_level="S0",
        declared_permissions=[{"kind": "path_prefix", "target": "workspace/"}],
    ), lambda args: {"content": "x"})
    assert registry.validate_input("workspace.read_file", {"path": "a.txt"})["path"] == "a.txt"
    with pytest.raises(ToolRegistryError):
        registry.validate_input("ghost", {})
    with pytest.raises(ToolRegistryError):
        registry.validate_input("workspace.read_file", {"path": 1})
    with pytest.raises(ToolRegistryError):
        registry.validate_input("workspace.read_file", {})  # 缺 required
    assert len(registry.list()) == 1
    assert registry.get("workspace.read_file").risk_level == "S0"
    with pytest.raises(ToolRegistryError):
        registry.register(ToolManifest(
            id="workspace.read_file", name="重复", description="dup",
            input_schema={}, output_schema={}, side_effect=False,
            risk_level="S0", declared_permissions=[],
        ), lambda args: {})


def test_validate_respects_enum_and_length_limits() -> None:
    registry = ToolRegistry()
    registry.register(ToolManifest(
        id="t1", name="t1", description="",
        input_schema={"type": "object",
                      "properties": {
                          "mode": {"type": "string", "enum": ["a", "b"]},
                          "items": {"type": "array", "maxItems": 3},
                      },
                      "required": ["mode"]},
        output_schema={}, side_effect=False, risk_level="S1", declared_permissions=[],
    ), lambda args: {})
    assert registry.validate_input("t1", {"mode": "a", "items": [1, 2]})["mode"] == "a"
    with pytest.raises(ToolRegistryError):
        registry.validate_input("t1", {"mode": "z"})
    with pytest.raises(ToolRegistryError):
        registry.validate_input("t1", {"mode": "a", "items": [1, 2, 3, 4]})
