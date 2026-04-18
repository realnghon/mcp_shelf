from __future__ import annotations

from typing import Any

from app.repositories.capability_repo import CapabilityRepo
from app.services.registry_service import RegistryService


class CapabilityValidationService:
    def __init__(self):
        self.registry = RegistryService()
        self.repo = CapabilityRepo()

    async def validate_definition(self, capability: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []

        if not capability.get("name"):
            errors.append("name is required")
        if not capability.get("slug"):
            errors.append("slug is required")
        if not capability.get("type"):
            errors.append("type is required")
        if not capability.get("source_type"):
            errors.append("source_type is required")

        self._validate_schema_field("input_schema", capability.get("input_schema"), errors)
        self._validate_schema_field("output_schema", capability.get("output_schema"), errors)
        self._validate_schema_field("config_schema", capability.get("config_schema"), errors, allow_empty=True)

        if capability.get("source_type") == "mcp_server":
            connection_config = capability.get("connection_config") or {}
            transport = str(connection_config.get("transport") or "streamable_http").lower()

            if transport in {"http", "streamable_http", "streamablehttp", "sse"}:
                endpoint = connection_config.get("endpoint_url")
                if not endpoint:
                    errors.append("connection_config.endpoint_url is required for http/sse mcp_server capabilities")
            elif transport == "stdio":
                command = connection_config.get("command")
                if not command:
                    errors.append("connection_config.command is required for stdio mcp_server capabilities")
            else:
                errors.append(f"connection_config.transport '{transport}' is not supported for mcp_server capabilities")

        return {
            "valid": len(errors) == 0,
            "schema_status": "valid" if not errors else "invalid",
            "errors": errors,
        }

    async def validate_capability(self, payload: dict[str, Any]) -> dict[str, Any]:
        capability_id = payload.get("capability_id")
        capability = payload.get("capability")

        if capability_id:
            capability = await self.registry.get_capability(capability_id)
            if capability is None:
                raise ValueError(f"Capability {capability_id} not found")
        elif capability is None:
            capability = payload

        result = await self.validate_definition(capability)
        result["capability_id"] = capability.get("id")

        capability_id = capability.get("id")
        if capability_id and not capability.get("is_builtin"):
            await self.repo.update(capability_id, {"schema_status": result["schema_status"]})

        return result

    @staticmethod
    def _validate_schema_field(
        field_name: str,
        schema: Any,
        errors: list[str],
        allow_empty: bool = False,
    ) -> None:
        if schema is None:
            if allow_empty:
                return
            errors.append(f"{field_name} is required")
            return

        if not isinstance(schema, dict):
            errors.append(f"{field_name} must be an object")
            return

        if allow_empty and schema == {}:
            return

        schema_type = schema.get("type")
        if not schema_type:
            errors.append(f"{field_name}.type is required")
