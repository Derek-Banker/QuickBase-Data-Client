from __future__ import annotations

import warnings
from typing import overload

from quickbase_data_client.exceptions import QuickbaseValidationError, format_error_message
from quickbase_data_client.identifier import Identifier
from quickbase_data_client.quickbase_api import QuickBaseAPI
from quickbase_data_client.table import Table as TableModel


class App:
    """
    Helper for interacting with a specific QuickBase App.
    """

    @overload
    def __init__(self, api_client: QuickBaseAPI, identifier: Identifier) -> None: ...

    @overload
    def __init__(self, api_client: QuickBaseAPI, *, id: str) -> None: ...

    @overload
    def __init__(self, api_client: QuickBaseAPI, *, name: str) -> None: ...

    @overload
    def __init__(self, api_client: QuickBaseAPI, *, id: str, name: str) -> None: ...

    def __init__(
        self,
        api_client: QuickBaseAPI,
        identifier: Identifier | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
    ) -> None:
        if api_client is None or not isinstance(api_client, QuickBaseAPI):
            raise QuickbaseValidationError(
                format_error_message(
                    "App requires a valid QuickBaseAPI instance.",
                    operation="App.__init__",
                    api_client_type=type(api_client).__name__ if api_client is not None else None,
                )
            )

        self._identifier = Identifier.factory(
            identifier=identifier,
            valid_levels="APP",
            id=id,
            name=name,
            default_level="APP",
            schema_cache=api_client.schema_cache,
        )
        self._api_client = api_client
        self.loaded_tables: list[TableModel] = []

    @property
    def name(self):
        return self._identifier.name

    @property
    def id(self):
        return self._identifier.id

    @property
    def identifier(self):
        return self._identifier

    @identifier.setter
    def identifier(self, identifier: Identifier):
        if not isinstance(identifier, Identifier):
            raise QuickbaseValidationError(
                format_error_message(
                    "App.identifier must be an Identifier instance.",
                    operation="App.identifier",
                    identifier_type=type(identifier).__name__,
                )
            )
        self._identifier = Identifier.factory(
            identifier,
            valid_levels="APP",
            default_level="APP",
            schema_cache=self._api_client.schema_cache,
        )

    @property
    def api_client(self):
        return self._api_client

    @api_client.setter
    def api_client(self, api_client: QuickBaseAPI):
        if not isinstance(api_client, QuickBaseAPI):
            raise QuickbaseValidationError(
                format_error_message(
                    "App.api_client must be a QuickBaseAPI instance.",
                    operation="App.api_client",
                    api_client_type=type(api_client).__name__,
                )
            )
        self._api_client = api_client

    def table(
        self,
        identifier: Identifier | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
    ) -> TableModel:
        if identifier is not None:
            table = TableModel(self, identifier=identifier)
        elif id is not None and name is not None:
            table = TableModel(self, id=id, name=name)
        elif id is not None:
            table = TableModel(self, id=id)
        elif name is not None:
            table = TableModel(self, name=name)
        else:
            raise QuickbaseValidationError(
                format_error_message(
                    "App.table requires an identifier, id, or name.",
                    operation="App.table",
                    app_id=self.id,
                    app_name=self.name,
                )
            )

        self.loaded_tables.append(table)
        return table

    def Table(
        self,
        identifier: Identifier | None = None,
        id: str | None = None,
        name: str | None = None,
    ) -> TableModel:
        warnings.warn(
            "App.Table() is deprecated; use app.table(...) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.table(identifier=identifier, id=id, name=name)

    def get_loaded_tables(self) -> list[TableModel]:
        return self.loaded_tables


AppRef = App
