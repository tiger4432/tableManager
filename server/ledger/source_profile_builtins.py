"""Built-in registration data for Source Ontology Profile schema version 1."""
from __future__ import annotations

from . import config
from .source_profile import (
    ClaimDescriptor,
    ContainerSlotDefinition,
    PackDescriptor,
    PackRegistry,
    ProfileRegistries,
    RoleDefinition,
    RoleDescriptor,
    TemplateDefinition,
    TemplateRegistry,
    TypeDefinition,
    TypeRegistry,
    default_binding_kind_registry,
)


def default_profile_registries() -> ProfileRegistries:
    """Return fresh, sealed registries so callers cannot mutate global validation."""
    packs = PackRegistry((
        PackDescriptor(
            pack_id="lot-lineage",
            version=1,
            claims=(ClaimDescriptor(
                claim_id="transition",
                roles=(
                    RoleDescriptor("subject", "entity"),
                    RoleDescriptor("parent", "entity"),
                    RoleDescriptor("child", "entity"),
                    RoleDescriptor("occurred_at", "time"),
                    RoleDescriptor(
                        "event_type", "attribute", required=False,
                        allowed_binding_kinds=(
                            "column", "constant", "declared_lookup"),
                        allowed_constant_types=("string",)),
                ),
            ),),
        ),
        PackDescriptor(
            pack_id="transfer",
            version=1,
            claims=(ClaimDescriptor(
                claim_id="movement",
                roles=(
                    RoleDescriptor("subject", "entity",
                                   allowed_binding_kinds=(
                                       "column", "declared_lookup")),
                    RoleDescriptor("from", "position",
                                   allowed_binding_kinds=(
                                       "column", "constant", "declared_lookup"),
                                   symbolic_constants=("source_position",)),
                    RoleDescriptor("to", "position",
                                   allowed_binding_kinds=(
                                       "column", "declared_lookup")),
                    RoleDescriptor("occurred_at", "time",
                                   allowed_binding_kinds=(
                                       "column", "declared_lookup")),
                    RoleDescriptor("event_key", "identity", required=False,
                                   allowed_binding_kinds=(
                                       "column", "declared_lookup")),
                    RoleDescriptor("row_order", "order", required=False,
                                   allowed_binding_kinds=(
                                       "column", "constant", "declared_lookup"),
                                   allowed_constant_types=("integer",)),
                    RoleDescriptor("qty", "quantity", required=False,
                                   allowed_binding_kinds=(
                                       "column", "constant", "declared_lookup"),
                                   allowed_constant_types=("integer", "number")),
                ),
            ),),
        ),
    )).seal()

    # 🔴 FROM THE DECLARATION since 2026-08-27, not `vocabulary.ENTITY_TYPES`.
    # The declaration carries `keys` and nothing else - it has no `label_ko` field and
    # refuses one - so a type labels itself, which is what the old spelling fell back to
    # for every type that had no label anyway.
    from ledger_api import entity_references
    entity_types = TypeRegistry(
        "entity",
        [TypeDefinition(name=name, keys=tuple(entity_references.identity_keys(name)),
                        label=name)
         for name in entity_references.declared_types()],
    ).seal()

    container_types = TypeRegistry(
        "container",
        [
            TypeDefinition(config.PLACE_WAFER_GRID, ("wafer",), "웨이퍼 격자"),
            TypeDefinition(config.PLACE_DT_SLOT, ("lot", "slot"), "물리 Lot/Slot"),
            TypeDefinition(config.PLACE_DT_JOB, ("job",), "확인 전 이동 단위"),
        ],
    ).seal()

    templates = TemplateRegistry([
        TemplateDefinition(
            name="lot_lineage",
            label="Lot 분할·병합",
            entity_types=("Lot",),
            roles=(
                RoleDefinition("row_identity", "원천 행 식별자"),
                RoleDefinition("occurred_at", "사건 시각"),
                RoleDefinition("event_type", "사건 종류"),
                RoleDefinition("lot", "현재 Lot"),
                RoleDefinition("parent_lot", "부모 Lot"),
                RoleDefinition("child_lot", "자식 Lot"),
                RoleDefinition("slots", "Slot 목록"),
                RoleDefinition("wafers", "Wafer 목록"),
            ),
        ),
        TemplateDefinition(
            name="transfer",
            label="개체 이동",
            entity_types=("Wafer",),
            roles=(
                RoleDefinition("row_identity", "원천 행 식별자"),
                RoleDefinition("occurred_at", "사건 시각"),
                RoleDefinition("event_key", "이동 사건 식별자"),
                RoleDefinition("row_order", "사건 안의 결정적 행 순서"),
                RoleDefinition("wafer", "이동 개체"),
                RoleDefinition("origin_lot", "출발 Lot", required=False),
                RoleDefinition("origin_slot", "출발 Slot", required=False),
                RoleDefinition("origin_job", "출발 이동 단위", required=False),
                RoleDefinition("destination_lookup_key", "목적지 확인 키",
                               required=False),
                RoleDefinition("destination_lot", "목적지 Lot", required=False),
                RoleDefinition("destination_slot", "목적지 Slot", required=False),
                RoleDefinition("destination_job", "목적지 이동 단위", required=False),
                RoleDefinition("recorded_lot", "원천에 기록된 목적지 Lot",
                               required=False),
                RoleDefinition("recorded_slot", "원천에 기록된 목적지 Slot",
                               required=False),
            ),
            containers=(
                ContainerSlotDefinition("from", "출발 위치"),
                ContainerSlotDefinition("to", "도착 위치"),
            ),
        ),
    ]).seal()

    return ProfileRegistries(
        templates=templates,
        entities=entity_types,
        containers=container_types,
        packs=packs,
        binding_kinds=default_binding_kind_registry(),
    )
