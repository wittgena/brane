# arch.xor.file.io
## @lineage: gov.gateway.io.base
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager

class FileStore(ABC):
    @abstractmethod
    def write(self, path: str, contents: str | bytes) -> None:
        """Write contents to a file at the specified path"""

    @abstractmethod
    def read(self, path: str) -> str:
        """Read and return the contents of a file as a string"""

    @abstractmethod
    def list(self, path: str) -> list[str]:
        """List all files and directories at the specified path"""

    @abstractmethod
    def delete(self, path: str) -> None:
        """Delete the file or directory at the specified path"""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if a file or directory exists at the specified path"""

    @abstractmethod
    def get_absolute_path(self, path: str) -> str:
        """Get the absolute filesystem path for a given relative path"""

    @abstractmethod
    @contextmanager
    def lock(self, path: str, timeout: float = 30.0) -> Iterator[None]:
        """Acquire an exclusive lock for the given path"""
        yield  # pragma: no cover
