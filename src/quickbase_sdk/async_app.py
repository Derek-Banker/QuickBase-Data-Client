from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, cast, overload

from quickbase_sdk.app import App as SyncApp
from quickbase_sdk.exceptions import QuickbaseValidationError, format_error_message
from quickbase_sdk.identifier import Identifier

if TYPE_CHECKING:
    from quickbase_sdk.async_quickbase_api import AsyncQuickBaseAPI
    from quickbase_sdk.async_table import AsyncTable as AsyncTableModel


class AsyncApp:
    """Async app helper that mirrors the stable Phase 9 app-scoped entry points."""

    @overload
    def __init__(self, api_client: AsyncQuickBaseAPI, identifier: Identifier) -> None: ...

    @overload
    def __init__(self, api_client: AsyncQuickBaseAPI, *, id: str) -> None: ...

    @overload
    def __init__(self, api_client: AsyncQuickBaseAPI, *, name: str) -> None: ...

    @overload
    def __init__(self, api_client: AsyncQuickBaseAPI, *, id: str, name: str) -> None: ...

    def __init__(
        self,
        api_client: AsyncQuickBaseAPI,
        identifier: Identifier | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
    ) -> None:
        from quickbase_sdk.async_quickbase_api import AsyncQuickBaseAPI

        if api_client is None or not isinstance(api_client, AsyncQuickBaseAPI):
            raise QuickbaseValidationError(
                format_error_message(
                    "AsyncApp requires a valid AsyncQuickBaseAPI instance.",
                    operation="AsyncApp.__init__",
                    api_client_type=type(api_client).__name__ if api_client is not None else None,
                )
            )

        sync_app_factory = cast(Any, SyncApp)
        self._delegate = sync_app_factory(
            api_client,
            identifier=identifier,
            id=id,
            name=name,
        )
        self._loaded_tables: list[AsyncTableModel] = []

    @property
    def name(self):
        return self._delegate.name

    @property
    def id(self):
        return self._delegate.id

    @property
    def identifier(self):
        return self._delegate.identifier

    @identifier.setter
    def identifier(self, identifier: Identifier):
        self._delegate.identifier = identifier

    @property
    def api_client(self) -> AsyncQuickBaseAPI:
        return cast("AsyncQuickBaseAPI", self._delegate.api_client)

    @api_client.setter
    def api_client(self, api_client: AsyncQuickBaseAPI):
        self._delegate.api_client = api_client

    def table(
        self,
        identifier: Identifier | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
    ) -> AsyncTableModel:
        from quickbase_sdk.async_table import AsyncTable as AsyncTableModel

        if identifier is not None:
            table = AsyncTableModel(self, identifier=identifier)
        elif id is not None and name is not None:
            table = AsyncTableModel(self, id=id, name=name)
        elif id is not None:
            table = AsyncTableModel(self, id=id)
        elif name is not None:
            table = AsyncTableModel(self, name=name)
        else:
            raise QuickbaseValidationError(
                format_error_message(
                    "AsyncApp.table requires an identifier, id, or name.",
                    operation="AsyncApp.table",
                    app_id=self.id,
                    app_name=self.name,
                )
            )

        self._loaded_tables.append(table)
        return table

    def Table(
        self,
        identifier: Identifier | None = None,
        id: str | None = None,
        name: str | None = None,
    ) -> AsyncTableModel:
        warnings.warn(
            "AsyncApp.Table() is deprecated; use app.table(...) instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.table(identifier=identifier, id=id, name=name)

    def get_loaded_tables(self) -> list[AsyncTableModel]:
        return self._loaded_tables


AsyncAppRef = AsyncApp
