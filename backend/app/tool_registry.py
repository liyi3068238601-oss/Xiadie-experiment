"""CYR.3 tool registry: manifests, lightweight schema validation, dispatch."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


class ToolRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class ToolManifest:
    id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    side_effect: bool
    risk_level: str
    declared_permissions: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "input_schema": self.input_schema, "output_schema": self.output_schema,
            "side_effect": self.side_effect, "risk_level": self.risk_level,
            "declared_permissions": self.declared_permissions,
        }


Handler = Callable[..., dict[str, Any]]


def _check_value(value: Any, spec: dict[str, Any], path: str) -> None:
    expected = spec.get("type")
    if expected == "string":
        if not isinstance(value, str):
            raise ToolRegistryError(f"{path} 必须是字符串")
        if "maxLength" in spec and len(value) > spec["maxLength"]:
            raise ToolRegistryError(f"{path} 超过最大长度 {spec['maxLength']}")
        if "minLength" in spec and len(value) < spec["minLength"]:
            raise ToolRegistryError(f"{path} 短于最小长度 {spec['minLength']}")
        if "enum" in spec and value not in spec["enum"]:
            raise ToolRegistryError(f"{path} 不在允许枚举内")
    elif expected == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ToolRegistryError(f"{path} 必须是整数")
    elif expected == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ToolRegistryError(f"{path} 必须是数字")
    elif expected == "boolean":
        if not isinstance(value, bool):
            raise ToolRegistryError(f"{path} 必须是布尔值")
    elif expected == "array":
        if not isinstance(value, list):
            raise ToolRegistryError(f"{path} 必须是数组")
        if "maxItems" in spec and len(value) > spec["maxItems"]:
            raise ToolRegistryError(f"{path} 超过最大条目 {spec['maxItems']}")
        item_spec = spec.get("items")
        if isinstance(item_spec, dict):
            for index, item in enumerate(value):
                _check_value(item, item_spec, f"{path}[{index}]")
    elif expected == "object":
        if not isinstance(value, dict):
            raise ToolRegistryError(f"{path} 必须是对象")
        properties = spec.get("properties") or {}
        for name, prop_spec in properties.items():
            if name in value:
                _check_value(value[name], prop_spec, f"{path}.{name}")
        for required in spec.get("required") or []:
            if required not in value:
                raise ToolRegistryError(f"{path} 缺少必填字段 {required}")
    elif expected is None:
        return
    else:
        raise ToolRegistryError(f"{path} 不支持的类型 {expected}")


class ToolRegistry:
    def __init__(self) -> None:
        self._manifests: dict[str, ToolManifest] = {}
        self._handlers: dict[str, Handler] = {}

    def register(self, manifest: ToolManifest, handler: Handler) -> None:
        if manifest.id in self._manifests:
            raise ToolRegistryError(f"tool already registered: {manifest.id}")
        if manifest.risk_level not in {"S0", "S1", "S2", "S3", "S4"}:
            raise ToolRegistryError("risk_level 必须是 S0..S4")
        self._manifests[manifest.id] = manifest
        self._handlers[manifest.id] = handler

    def list(self) -> list[dict[str, Any]]:
        return [manifest.to_dict() for manifest in self._manifests.values()]

    def get(self, tool_id: str) -> ToolManifest:
        try:
            return self._manifests[tool_id]
        except KeyError as exc:
            raise ToolRegistryError(f"tool not found: {tool_id}") from exc

    def handler_for(self, tool_id: str) -> Handler:
        self.get(tool_id)
        return self._handlers[tool_id]

    def validate_input(self, tool_id: str, args: dict[str, Any]) -> dict[str, Any]:
        manifest = self.get(tool_id)
        if not isinstance(args, dict):
            raise ToolRegistryError("工具参数必须是对象")
        _check_value(args, manifest.input_schema, "args")
        return args
