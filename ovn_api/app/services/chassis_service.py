from __future__ import annotations

from fastapi import HTTPException

from ..core.ovn_sb import get_ovn_sb_client
from ..models.chassis import ChassisBinding, ChassisBindingsResponse, ChassisSummary


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, list):
        if not value:
            return None
        return bool(value[0])
    if isinstance(value, bool):
        return value
    return None


def _row_uuid(value: object) -> str | None:
    if value is None:
        return None
    uuid_value = getattr(value, "uuid", None)
    if uuid_value is not None:
        return str(uuid_value)
    return str(value)


def _row_name(value: object) -> str | None:
    if value is None:
        return None
    return getattr(value, "name", None) or _row_uuid(value)


class ChassisService:
    def __init__(self) -> None:
        self.sb_client = get_ovn_sb_client()

    def list_chassis(self) -> list[ChassisSummary]:
        idl = self.sb_client.get_idl()
        binding_counts = self._binding_counts(idl)
        chassis_rows = idl.tables["Chassis"].rows.values()

        results = [
            ChassisSummary(
                uuid=str(row.uuid),
                name=getattr(row, "name", ""),
                hostname=getattr(row, "hostname", ""),
                nb_cfg=getattr(row, "nb_cfg", None),
                transport_types=sorted(
                    {str(getattr(encap, "type", "")) for encap in getattr(row, "encaps", []) if getattr(encap, "type", "")}
                ),
                encap_ips=sorted(
                    {str(getattr(encap, "ip", "")) for encap in getattr(row, "encaps", []) if getattr(encap, "ip", "")}
                ),
                port_binding_count=binding_counts.get(str(row.uuid), 0),
                other_config=dict(getattr(row, "other_config", {})),
                external_ids=dict(getattr(row, "external_ids", {})),
            )
            for row in chassis_rows
        ]
        return sorted(results, key=lambda item: item.name)

    def get_chassis_bindings(self, chassis_ref: str) -> ChassisBindingsResponse:
        idl = self.sb_client.get_idl()
        chassis_row = self._find_chassis(idl, chassis_ref)
        chassis_uuid = str(chassis_row.uuid)
        chassis_name = getattr(chassis_row, "name", chassis_uuid)

        bindings: list[ChassisBinding] = []
        for row in idl.tables["Port_Binding"].rows.values():
            primary = getattr(row, "chassis", None)
            additional = list(getattr(row, "additional_chassis", []))

            if _row_uuid(primary) != chassis_uuid and all(_row_uuid(item) != chassis_uuid for item in additional):
                continue

            bindings.append(
                ChassisBinding(
                    logical_port=getattr(row, "logical_port", ""),
                    type=getattr(row, "type", ""),
                    datapath_uuid=_row_uuid(getattr(row, "datapath", None)),
                    tunnel_key=getattr(row, "tunnel_key", None),
                    up=_bool_or_none(getattr(row, "up", None)),
                    parent_port=self._single_optional_string(getattr(row, "parent_port", None)),
                    chassis=_row_name(primary),
                    additional_chassis=sorted(
                        name for name in (_row_name(item) for item in additional) if name
                    ),
                    options=dict(getattr(row, "options", {})),
                    external_ids=dict(getattr(row, "external_ids", {})),
                )
            )

        bindings.sort(key=lambda item: item.logical_port)
        return ChassisBindingsResponse(
            chassis=chassis_name,
            binding_count=len(bindings),
            bindings=bindings,
        )

    def _find_chassis(self, idl, chassis_ref: str):
        for row in idl.tables["Chassis"].rows.values():
            if str(row.uuid) == chassis_ref or getattr(row, "name", None) == chassis_ref:
                return row
        raise HTTPException(status_code=404, detail=f"Chassis {chassis_ref!r} not found.")

    def _binding_counts(self, idl) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in idl.tables["Port_Binding"].rows.values():
            primary = getattr(row, "chassis", None)
            additional = list(getattr(row, "additional_chassis", []))
            for chassis in [primary, *additional]:
                chassis_uuid = _row_uuid(chassis)
                if not chassis_uuid:
                    continue
                counts[chassis_uuid] = counts.get(chassis_uuid, 0) + 1
        return counts

    def _single_optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, list):
            if not value:
                return None
            return str(value[0])
        return str(value)
