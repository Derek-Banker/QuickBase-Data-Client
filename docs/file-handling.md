# File Handling

The sync table surface supports file upload, download, and delete operations.

Async support currently includes file upload only.

Assume the examples below already have a table handle such as:

```python
from quickbase_data_client import Auth, QuickBaseClient

client = QuickBaseClient(Auth("example.quickbase.com", "qb-user-token"))
table = client.table(id="bq123456")
```

## Build A FilePayload

From a local file:

```python
from pathlib import Path

from quickbase_data_client import FilePayload

payload = FilePayload(drive_path=Path("invoice.pdf"))
```

From inline base64 data:

```python
payload = FilePayload(name="invoice.pdf", data="JVBERi0xLjQK...")
```

Inline `data` must already be base64-encoded content.

## Upload A Single File

```python
response = table.upload_files(
    file_field_id=10,
    record_id=123,
    file_payload=FilePayload(drive_path="invoice.pdf"),
)
```

## Upload Multiple Files

```python
response = table.upload_files(
    file_field_id=10,
    multi_file_payload=[
        {"record_id": 123, "file": FilePayload(drive_path="invoice-a.pdf")},
        {"record_id": 124, "file": FilePayload(drive_path="invoice-b.pdf")},
    ],
)
```

Multi-file uploads are batched by request-size budget when needed.

## Download A File

```python
from pathlib import Path

response = table.download_file(
    field_id=10,
    record_id=123,
    version_number=0,
    output_file_name="invoice.pdf",
    output_file_path=Path("exports"),
)

print(response.path)
print(response.bytes_written)
print(response.encoding)
```

The download path is persisted locally. `response.encoding` is `"binary"` or `"base64"` depending on the transport payload Quickbase returned.

## Delete A File

```python
response = table.delete_file(
    field_id=10,
    record_id=123,
    version_number=0,
)
```

## Configure File And Request Limits

Global defaults come from `RequestConfig`:

```python
from quickbase_data_client import Auth, QuickBaseClient, RequestConfig

client = QuickBaseClient(
    Auth("example.quickbase.com", "qb-user-token"),
    request_config=RequestConfig(
        max_file_size_kb=5_000,
        max_request_size_kb=10_000,
    ),
)
```

You can also override per upload call:

```python
table.upload_files(
    file_field_id=10,
    file_payload=FilePayload(drive_path="invoice.pdf"),
    max_file_size_kb=5_000,
    max_request_size_kb=10_000,
)
```
