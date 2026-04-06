from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, cast

from quickbase_data_client.config import LEVELS_LIST, LEVELS_LITERAL
from quickbase_data_client.exceptions import (
    QuickbaseSchemaError,
    QuickbaseValidationError,
    format_error_message,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from quickbase_data_client.schema_cache import SchemaCache


class Identifier:
    """
    A lazy identifier for APP, TABLE, FIELD, or REPORT.
    """

    def __init__(
        self,
        level: LEVELS_LITERAL,
        id: str | int | None = None,
        name: str | None = None,
        parent: Identifier | None = None,
        type: str | None = None,
        schema_cache: SchemaCache | None = None,
        decorative: bool = False,
    ) -> None:
        normalized_level = level.upper()
        if normalized_level not in LEVELS_LIST:
            raise QuickbaseValidationError(
                format_error_message(
                    "Identifier level must be one of APP, TABLE, FIELD, or REPORT.",
                    operation="Identifier.__init__",
                    level=level,
                )
            )
        if name is None and id is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "Identifier requires either id or name.",
                    operation="Identifier.__init__",
                    level=normalized_level,
                )
            )
        if parent is not None and not isinstance(parent, Identifier):
            raise QuickbaseValidationError(
                format_error_message(
                    "Identifier.parent must be an Identifier when provided.",
                    operation="Identifier.__init__",
                    level=normalized_level,
                    parent_type=parent.__class__.__name__ if parent is not None else None,
                )
            )

        self._level: LEVELS_LITERAL = cast(LEVELS_LITERAL, normalized_level)
        self._name: str | None = name
        self._id: str | None = None if id is None else str(id)
        self._type: str | None = type
        self._parent: Identifier | None = parent
        self._schema_cache: SchemaCache | None = None
        self.properties: Dict[str, Any] = {}
        self._field_identities: list[Identifier] | None = None
        self._decorative: bool = decorative
        if schema_cache is not None:
            self.schema_cache = schema_cache

    def __repr__(self) -> str:
        parent_id = self._parent._id if self._parent is not None else None
        return (
            "{"
            f"'level':{self._level!r},"
            f"'id':{self._id!r},"
            f"'name':{self._name!r},"
            f"'parent_id':{parent_id!r}"
            "}"
        )

    @property
    def level(self) -> LEVELS_LITERAL:
        return self._level

    def _get_schema_cache(self, operation: str) -> SchemaCache:
        schema_cache = self.schema_cache
        if schema_cache is None:
            raise QuickbaseSchemaError(
                format_error_message(
                    "Schema lookup requires an attached SchemaCache.",
                    operation=operation,
                    object_ref=repr(self),
                )
            )
        return schema_cache

    def _get_schema_callable(self, operation: str, name: str) -> Any:
        schema_callable = getattr(self._get_schema_cache(operation), name, None)
        if not callable(schema_callable):
            raise QuickbaseSchemaError(
                format_error_message(
                    "Attached SchemaCache does not provide the required lookup.",
                    operation=operation,
                    lookup=name,
                    object_ref=repr(self),
                )
            )
        return schema_callable

    def _schema_parent_level(self) -> LEVELS_LITERAL | None:
        if self._level == "TABLE":
            return "APP"
        if self._level in {"FIELD", "REPORT"}:
            return "TABLE"
        return None

    def _resolve_parent_from_schema(self) -> Identifier | None:
        if self._parent is not None or self._id is None or self._decorative:
            return self._parent
        if self.schema_cache is None:
            return None

        parent_level = self._schema_parent_level()
        if parent_level is None:
            return None

        get_parent = self._get_schema_callable("Identifier.parent", "get_parent")
        parent_id = get_parent(level=self._level, id=self._id)
        if parent_id is None:
            return None

        self._parent = Identifier(level=parent_level, id=parent_id, schema_cache=self.schema_cache)
        return self._parent

    @property
    def name(self) -> str | None:
        if self._name is None:
            if self._decorative:
                logger.warning(
                    "Identifier.name auto-resolution skipped for decorative identifier %s.",
                    self,
                )
                return None

            if self._id is None:
                raise QuickbaseValidationError(
                    format_error_message(
                        "Identifier cannot resolve name without an id.",
                        operation="Identifier.name",
                        object_ref=repr(self),
                    )
                )

            parent_id = self.parent.id if self.parent is not None else None
            if self._level in {"FIELD", "REPORT"} and parent_id is None:
                raise QuickbaseSchemaError(
                    format_error_message(
                        (
                            "Identifier cannot resolve name without a parent "
                            "reference or cached schema metadata."
                        ),
                        operation="Identifier.name",
                        object_ref=repr(self),
                    )
                )

            get_name = self._get_schema_callable("Identifier.name", "get_name")
            self._name = get_name(level=self._level, id=self._id, parent_id=parent_id)
            if self._name is None:
                raise QuickbaseSchemaError(
                    format_error_message(
                        "Schema lookup returned no name.",
                        operation="Identifier.name",
                        object_ref=repr(self),
                    )
                )
            logger.debug("Resolved Identifier name '%s' for %s.", self._name, self)

        return self._name

    @property
    def id(self) -> str | None:
        if self._id is None:
            if self._decorative:
                logger.warning(
                    "Identifier.id auto-resolution skipped for decorative identifier %s.",
                    self,
                )
                return None

            if self._name is None:
                raise QuickbaseValidationError(
                    format_error_message(
                        "Identifier cannot resolve id without a name.",
                        operation="Identifier.id",
                        object_ref=repr(self),
                    )
                )

            if self._level != "APP" and self._parent is None:
                raise QuickbaseValidationError(
                    format_error_message(
                        "Identifier cannot resolve id from a name without a parent reference.",
                        operation="Identifier.id",
                        object_ref=repr(self),
                    )
                )

            get_id = self._get_schema_callable("Identifier.id", "get_id")
            parent_id = self._parent.id if self._parent is not None else None
            self._id = get_id(level=self._level, name=self._name, parent_id=parent_id)
            if self._id is None:
                raise QuickbaseSchemaError(
                    format_error_message(
                        "Schema lookup returned no id.",
                        operation="Identifier.id",
                        object_ref=repr(self),
                    )
                )
            logger.debug("Resolved Identifier id '%s' for %s.", self._id, self)

        return self._id

    @property
    def type(self) -> str | None:
        if self._level in {"APP", "TABLE"}:
            return None

        if self._type is None:
            if self._decorative:
                logger.warning(
                    "Identifier.type auto-resolution skipped for decorative identifier %s.",
                    self,
                )
                return None

            if self.id is None:
                raise QuickbaseValidationError(
                    format_error_message(
                        "Identifier cannot resolve type without an id.",
                        operation="Identifier.type",
                        object_ref=repr(self),
                    )
                )

            parent_id = self.parent.id if self.parent is not None else None
            if parent_id is None:
                raise QuickbaseSchemaError(
                    format_error_message(
                        (
                            "Identifier cannot resolve type without a parent "
                            "reference or cached schema metadata."
                        ),
                        operation="Identifier.type",
                        object_ref=repr(self),
                    )
                )

            get_type = self._get_schema_callable("Identifier.type", "get_type")
            self._type = get_type(level=self._level, id=self._id, parent_id=parent_id)
            if self._type is None:
                raise QuickbaseSchemaError(
                    format_error_message(
                        "Schema lookup returned no type.",
                        operation="Identifier.type",
                        object_ref=repr(self),
                    )
                )
            logger.debug("Resolved Identifier type '%s' for %s.", self._type, self)

        return self._type

    @property
    def parent(self) -> Identifier | None:
        if self._level == "APP":
            return None
        if self._parent is not None:
            return self._parent
        if self.schema_cache is None:
            return None
        return self._resolve_parent_from_schema()

    @property
    def decorative(self) -> bool:
        return self._decorative

    @property
    def schema_cache(self) -> SchemaCache | None:
        if self._schema_cache is not None:
            return self._schema_cache
        if self._parent is not None:
            return self._parent.schema_cache
        return None

    def get_properties(self, filters: List[str] | None = None) -> Dict[str, Any]:
        if not self.properties:
            get_properties = self._get_schema_callable(
                "Identifier.get_properties",
                "get_properties",
            )
            raw = get_properties(
                self._level,
                self.id,
                self.parent.id if self.parent else None,
            )
            self.properties = raw or {}
            logger.debug("Loaded Identifier properties for %s.", self)

        if filters:
            return {k: v for k, v in self.properties.items() if k in filters}
        return self.properties

    @parent.setter
    def parent(self, parent: Any) -> None:
        if parent is None or not isinstance(parent, Identifier):
            raise QuickbaseValidationError(
                format_error_message(
                    "Identifier.parent must be set to an Identifier instance.",
                    operation="Identifier.parent",
                    parent_type=type(parent).__name__ if parent is not None else None,
                )
            )
        self._parent = parent

    @schema_cache.setter
    def schema_cache(self, schema_cache: SchemaCache) -> None:
        from quickbase_data_client.schema_cache import SchemaCache

        if not isinstance(schema_cache, SchemaCache):
            raise QuickbaseValidationError(
                format_error_message(
                    "Identifier.schema_cache must be a SchemaCache instance.",
                    operation="Identifier.schema_cache",
                    schema_cache_type=type(schema_cache).__name__,
                )
            )
        self._schema_cache = schema_cache

    @name.setter
    def name(self, name: str) -> None:
        if name is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "Identifier.name cannot be set to None.",
                    operation="Identifier.name",
                    object_ref=repr(self),
                )
            )
        self._name = name

    @id.setter
    def id(self, id: str) -> None:
        if id is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "Identifier.id cannot be set to None.",
                    operation="Identifier.id",
                    object_ref=repr(self),
                )
            )
        self._id = id

    @type.setter
    def type(self, type: str) -> None:
        if type is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "Identifier.type cannot be set to None.",
                    operation="Identifier.type",
                    object_ref=repr(self),
                )
            )
        self._type = type

    def create_child(
        self,
        level: LEVELS_LITERAL,
        id: str | int | None = None,
        name: str | None = None,
        type: str | None = None,
        decorative: bool = False,
    ) -> Identifier:
        return Identifier(
            level=level,
            id=id,
            name=name,
            parent=self,
            type=type,
            schema_cache=self.schema_cache,
            decorative=decorative,
        )

    def field_identities(self) -> List[Identifier] | None:
        if self.level != "TABLE":
            return None

        if self._field_identities is None:
            generate_field_identities = self._get_schema_callable(
                "Identifier.field_identities",
                "generate_field_identities",
            )
            self._field_identities = generate_field_identities(self)

        return self._field_identities

    @staticmethod
    def factory(
        identifier: Identifier | None,
        *,
        valid_levels: LEVELS_LITERAL | List[LEVELS_LITERAL] | None = None,
        id: str | None = None,
        name: str | None = None,
        level: LEVELS_LITERAL | None = None,
        default_level: LEVELS_LITERAL,
        parent: Identifier | None = None,
        schema_cache: SchemaCache | None = None,
    ) -> Identifier:
        if isinstance(valid_levels, list):
            valid_lvls = valid_levels
        elif valid_levels:
            valid_lvls = [valid_levels]
        else:
            valid_lvls = []

        if isinstance(identifier, Identifier):
            if valid_lvls and identifier.level not in valid_lvls:
                raise QuickbaseValidationError(
                    format_error_message(
                        "Identifier has an invalid level for this operation.",
                        operation="Identifier.factory",
                        identifier_level=identifier.level,
                        valid_levels=valid_lvls,
                    )
                )
            if parent is not None:
                if identifier._parent is None:
                    identifier.parent = parent
                elif identifier._parent.id != parent.id:
                    raise QuickbaseValidationError(
                        format_error_message(
                            "Identifier has a conflicting parent reference.",
                            operation="Identifier.factory",
                            identifier_level=identifier.level,
                            identifier_id=identifier._id,
                            parent_id=identifier._parent.id,
                            expected_parent_id=parent.id,
                        )
                    )
            if schema_cache is not None and identifier.schema_cache is None:
                identifier.schema_cache = schema_cache
            return identifier

        effective_level = default_level if level is None else level
        return Identifier(
            level=effective_level,
            id=id,
            name=name,
            parent=parent,
            schema_cache=schema_cache,
        )
