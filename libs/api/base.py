"""
Base API client classes and interfaces for the documentation processor.

This module provides abstract base classes and common response types
for all API integrations.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging
from ..logger import get_logger


@dataclass
class APIResponse:
    """Standard response format for all API operations."""
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None
    status_code: Optional[int] = None
    retry_after: Optional[int] = None  # For rate limiting
    
    @property
    def is_rate_limited(self) -> bool:
        """Check if response indicates rate limiting."""
        return self.status_code == 429
    
    @property
    def is_server_error(self) -> bool:
        """Check if response indicates server error (5xx)."""
        return self.status_code is not None and 500 <= self.status_code < 600
    
    @property
    def is_client_error(self) -> bool:
        """Check if response indicates client error (4xx)."""
        return self.status_code is not None and 400 <= self.status_code < 500


class BaseAPIClient(ABC):
    """Abstract base class for all API clients."""
    
    def __init__(self, config):
        """Initialize the API client with configuration."""
        self.config = config
        self.logger = get_logger(f'api.{self.__class__.__name__.lower()}')
        self._setup_client()
    
    def _setup_client(self):
        """Setup the HTTP client with authentication and defaults."""
        pass  # Override in subclasses
    
    @abstractmethod
    def test_connection(self) -> APIResponse:
        """Test API connectivity and authentication."""
        pass
    
    @abstractmethod
    def create_collection(self, name: str, description: str = "", 
                         color: str = "#4E5C6E") -> APIResponse:
        """Create a new collection/workspace."""
        pass
    
    @abstractmethod
    def create_document(self, collection_id: str, title: str, 
                       content: str, parent_id: Optional[str] = None,
                       publish: bool = True) -> APIResponse:
        """Create a document with optional parent relationship."""
        pass
    
    @abstractmethod
    def update_document(self, document_id: str, title: Optional[str] = None, 
                       content: Optional[str] = None) -> APIResponse:
        """Update existing document."""
        pass
    
    @abstractmethod
    def upload_attachment(self, file_path: str, document_id: str, 
                         filename: Optional[str] = None) -> APIResponse:
        """Upload file attachment to document."""
        pass
    
    @abstractmethod
    def get_collection(self, collection_id: str) -> APIResponse:
        """Get collection details by ID."""
        pass
    
    @abstractmethod
    def get_document(self, document_id: str) -> APIResponse:
        """Get document details by ID."""
        pass
    
    @abstractmethod
    def list_collections(self, limit: int = 25, offset: int = 0) -> APIResponse:
        """List available collections."""
        pass
    
    @abstractmethod
    def list_documents(self, collection_id: str, limit: int = 25, 
                      offset: int = 0) -> APIResponse:
        """List documents in a collection."""
        pass
    
    def _handle_response(self, response, operation: str) -> APIResponse:
        """Common response handling for all API operations."""
        try:
            if response.status_code == 200:
                return APIResponse(
                    success=True,
                    data=response.json(),
                    status_code=response.status_code
                )
            elif response.status_code == 429:
                # Rate limiting
                retry_after = int(response.headers.get('Retry-After', 60))
                return APIResponse(
                    success=False,
                    data={},
                    error=f"Rate limited - retry after {retry_after} seconds",
                    status_code=response.status_code,
                    retry_after=retry_after
                )
            else:
                # Other errors
                error_data = response.json() if response.content else {}
                error_message = error_data.get('message', f'HTTP {response.status_code}')
                
                self.logger.error(f"{operation} failed: {error_message} (status: {response.status_code})")
                
                return APIResponse(
                    success=False,
                    data=error_data,
                    error=error_message,
                    status_code=response.status_code
                )
        except Exception as e:
            self.logger.error(f"{operation} failed with exception: {e}")
            return APIResponse(
                success=False,
                data={},
                error=str(e)
            )