# source_service

A generic, pluggable Python service for fetching documents from multiple sources.  
Supports: **FTP, SFTP, S3, SMB, API, POP3** — and easily extensible for custom sources.

> Designed to be **Django‑agnostic**: can be used in any Python project, scripts, Lambdas, or Celery tasks.

---

## 🚀 Features

- **Unified interface** – list, fetch, and fetch multiple documents.
- **Factory pattern** – instantiate the right source by name.
- **Lightweight** – minimal dependencies, no Django ORM coupling.
- **Pluggable** – add new source types by implementing a simple interface.
- **Secure** – supports credentials, tokens, SSH keys, SSL, etc.
- **Tested** – unit and integration tests against real services (Dockerized).

---

## 📦 Installation

```bash
pip install source-service
```

Or install directly from Git (development):

```bash
pip install git+https://github.com/your-org/source-service.git
```

---

## 🧩 Quick start

```python
from source_service import SourceFactory

# Configuration for an S3 source
config = {
    'bucket': 'my-documents',
    'region': 'eu-west-2',
    'access_key': 'AKIA...',
    'secret_key': '...',
}

# Get the fetcher
fetcher = SourceFactory.get_source('s3')

# List documents (metadata only)
docs = fetcher.list_documents(config)
for doc in docs:
    print(doc.key, doc.metadata['size'])

# Download a single document
doc = fetcher.fetch_document(config, 'folder/report.pdf')
with open('report.pdf', 'wb') as f:
    f.write(doc.content)
```

---

## 🗂️ Supported source types

| Source | Identifier | Dependencies |
|--------|------------|--------------|
| **Amazon S3** | `s3` | `boto3` |
| **FTP** | `ftp` | – (standard library) |
| **SFTP** | `sftp` | `paramiko` |
| **SMB / CIFS** | `smb` | `smbprotocol` |
| **REST API** | `api` | `requests` |
| **POP3** | `pop3` | – (standard library) |

---

## 🔧 Configuration examples

Each source expects a `config` dictionary with appropriate fields.

### S3
```python
config = {
    'bucket': 'my-bucket',
    'access_key': 'AKIA...',
    'secret_key': '...',
    'region': 'eu-west-2',
    'prefix': 'incoming/',          # optional
}
```

### SFTP
```python
config = {
    'host': 'sftp.example.com',
    'port': 22,
    'username': 'user',
    'password': 'pass',             # or use ssh_key_path
    'ssh_key_path': '/path/to/key', # optional
    'path': '/documents',           # directory to list
}
```

### FTP
```python
config = {
    'host': 'ftp.example.com',
    'port': 21,
    'username': 'anonymous',
    'password': 'pass',
    'path': '/pub',
}
```

### SMB (using `smbclient`)
```python
config = {
    'host': 'smb-server',
    'share': 'documents',
    'username': 'user',
    'password': 'pass',
    'path': '/',                   # optional, inside the share
}
```

### API (REST)
```python
config = {
    'url': 'https://api.example.com/documents',
    'headers': {'Accept': 'application/json'},
    'auth': {
        'token': 'your-api-token'
    },
    'params': {'limit': 100},
}
```

### POP3 (email)
```python
config = {
    'host': 'pop.gmail.com',
    'port': 995,
    'use_ssl': True,
    'username': 'user@gmail.com',
    'password': 'app-password',
}
```

---

## 🏭 Factory usage

The factory instantiates fetchers by name:

```python
from source_service import SourceFactory

fetcher = SourceFactory.get_source('s3')
```

If you need to add a custom source, register it:

```python
from source_service import SourceFactory
from .my_source import MyCustomSource

SourceFactory.register('custom', MyCustomSource)
```

---

## 📄 Document model

All fetchers return a `Document` dataclass:

```python
@dataclass
class Document:
    key: str                     # unique identifier (path, name, etc.)
    metadata: Dict[str, Any]     # size, last_modified, content_type, etc.
    content: Optional[bytes] = None  # file contents (if fetched)
```

---

## 🧪 Testing

Install development dependencies:

```bash
pip install -e .[dev]
```

Run unit tests:

```bash
python -m unittest discover tests
```

Integration tests (requires Docker – see `docker-compose.yml`):

```bash
docker compose up -d
python -m unittest discover tests.integration
```

---

## 🔌 Extending with new sources

1. Create a new class that inherits from `DocumentSource`.
2. Implement `list_documents`, `fetch_document`, and optionally `fetch_documents`.
3. Optionally implement `move_document` and `delete_document` if the source supports them.
4. Register it in the factory.

Example:

```python
from source_service import DocumentSource, Document

class MySource(DocumentSource):
    def list_documents(self, config):
        # return List[Document]
        pass

    def fetch_document(self, config, key):
        # return Document
        pass
```

---

## 📦 Dependencies

| Package | Version | Used for |
|---------|---------|----------|
| `boto3` | ≥1.26.0 | S3 |
| `paramiko` | ≥2.10.0 | SFTP |
| `smbprotocol` | ≥1.17.0 | SMB (via `smbclient`) |
| `requests` | ≥2.28.0 | API |
| `jsonschema` | ≥4.0.0 | Config validation (optional) |

---

## 🤝 Contributing

Contributions are welcome! Please:

- Open an issue to discuss your idea.
- Write tests for new features or bug fixes.
- Follow the existing code style.

---

## 📄 License

MIT © [Your Name/Company]

---

## 🧭 Further reading

- [Source code on GitHub](https://github.com/your-org/source-service)
- [Issue tracker](https://github.com/your-org/source-service/issues)
