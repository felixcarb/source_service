from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class Document:
    """Document retrieved from a source."""
    key: str                     # Unique identifier (path, name, etc.)
    metadata: Dict[str, Any]     # Metadata (size, date, type, etc.)
    content: Optional[bytes] = None  # Document content


class DocumentSource(ABC):
    """Base interface for all document sources."""

    @abstractmethod
    def list_documents(self, config: Dict[str, Any]) -> List[Document]:
        """List available documents (metadata only)."""
        raise NotImplementedError

    @abstractmethod
    def fetch_document(self, config: Dict[str, Any], key: str) -> Document:
        """Fetch a single document by its key."""
        raise NotImplementedError

    @abstractmethod
    def fetch_documents(self, config: Dict[str, Any], keys: Optional[List[str]] = None) -> List[Document]:
        """Fetch one or more documents (all if keys is None)."""
        raise NotImplementedError

    def move_document(self, config: Dict[str, Any], key: str, destination: str) -> bool:
        """
        Move a document to a new location within the same source.
        Returns True if successful, False if the operation is not supported.
        Subclasses that support moving should override this method.
        """
        return False

    def delete_document(self, config: Dict[str, Any], key: str) -> bool:
        """
        Delete a document from the source.
        Returns True if successful, False if the operation is not supported.
        Subclasses that support deletion should override this method.
        """
        return False
