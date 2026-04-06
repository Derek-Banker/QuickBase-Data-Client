import base64
import logging
from pathlib import Path
from typing import Dict

from quickbase_data_client.config import DEFAULT_EXPORT_PATH, DEFAULT_MAX_FILE_SIZE
from quickbase_data_client.exceptions import QuickbasePayloadError, format_error_message

logger = logging.getLogger(__name__)


class FilePayload:
    """
    Encapsulates a file for QuickBase upload/download.
    """

    __slots__ = ("_file_name", "_file_path", "_file_data")

    def __init__(
        self,
        *,
        name: str | None = None,
        drive_path: Path | str | None = None,
        data: str | None = None,
    ) -> None:
        if drive_path is None and data is None:
            raise QuickbasePayloadError(
                format_error_message(
                    "FilePayload requires drive_path or data.",
                    operation="FilePayload.__init__",
                    file_name=name,
                )
            )

        self._file_name = name
        self._file_path = self._validate_path(drive_path)
        self._file_data = data

    def _validate_path(self, input_path: Path | str | None) -> Path | None:
        if isinstance(input_path, Path):
            path = input_path
        elif isinstance(input_path, str):
            path = Path(input_path)
        else:
            return None

        if not path.exists():
            raise QuickbasePayloadError(
                format_error_message(
                    "Provided file path does not exist.",
                    operation="FilePayload._validate_path",
                    drive_path=str(input_path),
                )
            )

        if path.is_dir():
            raise QuickbasePayloadError(
                format_error_message(
                    "Provided file path points to a directory, not a file.",
                    operation="FilePayload._validate_path",
                    drive_path=str(input_path),
                )
            )

        if path.is_file():
            if self._file_name is None:
                self._file_name = path.name
            return path

        raise QuickbasePayloadError(
            format_error_message(
                "Provided file path is neither a regular file nor a directory.",
                operation="FilePayload._validate_path",
                drive_path=str(input_path),
            )
        )

    @property
    def name(self) -> str | None:
        return self._file_name

    @name.setter
    def name(self, new_name: str | None) -> None:
        self._file_name = new_name

    @property
    def path(self) -> Path | None:
        return self._file_path

    @path.setter
    def path(self, new_path: str | Path | None) -> None:
        self._file_path = self._validate_path(new_path)
        self._file_data = None

    @property
    def encoded(self) -> str:
        return self.get_encoded()

    @encoded.setter
    def encoded(self, data: str) -> None:
        self._file_data = data

    def get_encoded(self, *, size_limit_kb: int | float = DEFAULT_MAX_FILE_SIZE) -> str:
        if self._file_data is not None and self._file_path is None:
            return self._file_data

        if self._file_path is None:
            if self._file_data is not None:
                return self._file_data
            raise QuickbasePayloadError(
                format_error_message(
                    "Cannot encode file payload without a local path or inline data.",
                    operation="FilePayload.get_encoded",
                    file_name=self._file_name,
                )
            )

        encoded = FilePayload._encode_file(self._file_path, size_limit=size_limit_kb)
        self._file_data = encoded
        return encoded

    def as_dict(self, *, size_limit_kb: int | float = DEFAULT_MAX_FILE_SIZE) -> Dict[str, str]:
        if not self._file_name:
            raise QuickbasePayloadError(
                format_error_message(
                    "Cannot build file payload without a file name.",
                    operation="FilePayload.as_dict",
                    drive_path=str(self._file_path) if self._file_path else None,
                )
            )

        return {
            "fileName": self._file_name,
            "data": self.get_encoded(size_limit_kb=size_limit_kb),
        }

    @staticmethod
    def _normalize_size_limit_kb(size_limit: int | float) -> float:
        if (
            isinstance(size_limit, bool)
            or not isinstance(size_limit, (int, float))
            or size_limit <= 0
        ):
            raise QuickbasePayloadError(
                format_error_message(
                    "size_limit must be greater than zero.",
                    operation="FilePayload._encode_file",
                    size_limit_kb=size_limit,
                )
            )
        return float(size_limit)

    @staticmethod
    def _encode_file(
        file_path: Path | str,
        size_limit: int | float = DEFAULT_MAX_FILE_SIZE,
    ) -> str:
        if not isinstance(file_path, Path):
            file_path = Path(file_path)

        size_limit_kb = FilePayload._normalize_size_limit_kb(size_limit)

        if not file_path.exists() or not file_path.is_file():
            raise QuickbasePayloadError(
                format_error_message(
                    "Cannot encode a missing file.",
                    operation="FilePayload._encode_file",
                    drive_path=str(file_path),
                )
            )

        size_kb = file_path.stat().st_size / 1024
        if size_kb > size_limit_kb:
            raise QuickbasePayloadError(
                format_error_message(
                    "File exceeds the configured size limit.",
                    operation="FilePayload._encode_file",
                    drive_path=str(file_path),
                    size_kb=f"{size_kb:.2f}",
                    size_limit_kb=size_limit_kb,
                )
            )

        try:
            raw = file_path.read_bytes()
        except Exception as exc:
            raise QuickbasePayloadError(
                format_error_message(
                    "Failed to read file bytes.",
                    operation="FilePayload._encode_file",
                    drive_path=str(file_path),
                    cause=exc,
                )
            ) from exc

        return base64.b64encode(raw).decode("utf-8")

    @staticmethod
    def _write_bytes(
        file_bytes: bytes,
        file_name: str,
        output_path: str | Path = DEFAULT_EXPORT_PATH,
    ) -> Path:
        out_dir = Path(output_path)
        out_dir.mkdir(parents=True, exist_ok=True)

        target = out_dir / file_name
        try:
            target.write_bytes(file_bytes)
        except Exception as exc:
            raise QuickbasePayloadError(
                format_error_message(
                    "Failed to write file to disk.",
                    operation="FilePayload._write_bytes",
                    file_name=file_name,
                    output_path=str(out_dir),
                    cause=exc,
                )
            ) from exc

        logger.debug("Wrote file '%s' to '%s'.", file_name, target)
        return target

    @staticmethod
    def _decode_file(
        b64_string: str,
        file_name: str,
        output_path: str | Path = DEFAULT_EXPORT_PATH,
    ) -> Path:
        out_dir = Path(output_path)
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            raw = base64.b64decode(b64_string, validate=True)
        except Exception as exc:
            raise QuickbasePayloadError(
                format_error_message(
                    "Invalid base64 file data.",
                    operation="FilePayload._decode_file",
                    file_name=file_name,
                    output_path=str(out_dir),
                    cause=exc,
                )
            ) from exc

        return FilePayload._write_bytes(raw, file_name, out_dir)
