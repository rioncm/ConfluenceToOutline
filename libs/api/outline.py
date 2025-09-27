"""
Outline API client implementation.

This module provides a complete API client for Outline knowledge base
integration with document creation, collection management, and file uploads.
"""
import requests
import os
from pathlib import Path
from urllib.parse import urljoin
from typing import Dict, Any, Optional
import time

from .base import BaseAPIClient, APIResponse
from ..logger import get_logger


class OutlineAPIClient(BaseAPIClient):
    """Outline API client for document management operations."""
    
    def _setup_client(self):
        """Setup the HTTP session with authentication."""
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.config.api_key}',
            'Content-Type': 'application/json'
        })
        # Set timeout on requests, not session
        self.timeout = self.config.timeout
        self.base_url = self.config.api_url.rstrip('/')
        
        self.logger.info(f"Initialized Outline API client for {self.base_url}")
    
    def test_connection(self) -> APIResponse:
        """Test API connectivity using auth.info endpoint."""
        try:
            self.logger.debug("Testing API connection...")
            response = self.session.post(urljoin(self.base_url, '/api/auth.info'))
            result = self._handle_response(response, "test_connection")
            
            if result.success:
                user_name = result.data.get('data', {}).get('user', {}).get('name', 'Unknown')
                self.logger.info(f"API connection successful - authenticated as: {user_name}")
            
            return result
        except Exception as e:
            return APIResponse(success=False, data={}, error=str(e))
    
    def create_collection(self, name: str, description: str = "", 
                         color: str = "#4E5C6E") -> APIResponse:
        """Create a new collection in Outline."""
        try:
            self.logger.info(f"Creating collection: {name}")
            
            data = {
                'name': name,
                'description': description,
                'color': color,
                'private': False  # Public collection
            }
            
            response = self.session.post(
                urljoin(self.base_url, '/api/collections.create'),
                json=data
            )
            
            result = self._handle_response(response, f"create_collection({name})")
            
            if result.success:
                collection_id = result.data.get('data', {}).get('id')
                self.logger.info(f"Created collection '{name}' with ID: {collection_id}")
            
            return result
            
        except Exception as e:
            return APIResponse(success=False, data={}, error=str(e))
    
    def create_document(self, collection_id: str, title: str, 
                       content: str, parent_id: Optional[str] = None,
                       publish: bool = True) -> APIResponse:
        """Create a document in Outline."""
        try:
            self.logger.info(f"Creating document: {title}")
            
            data = {
                'title': title,
                'text': content,
                'collectionId': collection_id,
                'publish': publish
            }
            
            # Add parent relationship if specified
            if parent_id:
                data['parentDocumentId'] = parent_id
                self.logger.debug(f"Setting parent document: {parent_id}")
            
            response = self.session.post(
                urljoin(self.base_url, '/api/documents.create'),
                json=data
            )
            
            result = self._handle_response(response, f"create_document({title})")
            
            if result.success:
                doc_id = result.data.get('data', {}).get('id')
                doc_url = result.data.get('data', {}).get('url')
                self.logger.info(f"Created document '{title}' with ID: {doc_id}")
                self.logger.debug(f"Document URL: {doc_url}")
            
            return result
            
        except Exception as e:
            return APIResponse(success=False, data={}, error=str(e))
    
    def update_document(self, document_id: str, title: Optional[str] = None, 
                       content: Optional[str] = None) -> APIResponse:
        """Update an existing document."""
        try:
            self.logger.info(f"Updating document: {document_id}")
            
            data = {'id': document_id}
            
            if title is not None:
                data['title'] = title
            if content is not None:
                data['text'] = content
            
            response = self.session.post(
                urljoin(self.base_url, '/api/documents.update'),
                json=data
            )
            
            return self._handle_response(response, f"update_document({document_id})")
            
        except Exception as e:
            return APIResponse(success=False, data={}, error=str(e))
    
    def upload_attachment(self, file_path: str, document_id: str, 
                         filename: Optional[str] = None) -> APIResponse:
        """Upload file attachment to Outline."""
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                return APIResponse(success=False, data={}, error=f"File not found: {file_path}")
            
            actual_filename = filename or file_path_obj.name
            self.logger.info(f"Uploading attachment: {actual_filename}")
            
            # For file uploads, we need to use multipart/form-data
            files = {
                'file': (actual_filename, open(file_path_obj, 'rb')),
                'documentId': (None, document_id),
                'name': (None, actual_filename)
            }
            
            # Temporarily remove Content-Type header for multipart upload
            headers = dict(self.session.headers)
            if 'Content-Type' in headers:
                del headers['Content-Type']
            
            response = self.session.post(
                urljoin(self.base_url, '/api/attachments.create'),
                files=files,
                headers=headers,
                timeout=self.timeout
            )
            
            # Close the file
            files['file'][1].close()
            
            result = self._handle_response(response, f"upload_attachment({actual_filename})")
            
            if result.success:
                attachment_id = result.data.get('data', {}).get('id')
                self.logger.info(f"Uploaded attachment '{actual_filename}' with ID: {attachment_id}")
            
            return result
            
        except Exception as e:
            return APIResponse(success=False, data={}, error=str(e))
    
    def get_collection(self, collection_id: str) -> APIResponse:
        """Get collection details by ID."""
        try:
            response = self.session.post(
                urljoin(self.base_url, '/api/collections.info'),
                json={'id': collection_id}
            )
            
            return self._handle_response(response, f"get_collection({collection_id})")
            
        except Exception as e:
            return APIResponse(success=False, data={}, error=str(e))
    
    def get_document(self, document_id: str) -> APIResponse:
        """Get document details by ID."""
        try:
            response = self.session.post(
                urljoin(self.base_url, '/api/documents.info'),
                json={'id': document_id}
            )
            
            return self._handle_response(response, f"get_document({document_id})")
            
        except Exception as e:
            return APIResponse(success=False, data={}, error=str(e))
    
    def list_collections(self, limit: int = 25, offset: int = 0) -> APIResponse:
        """List available collections."""
        try:
            data = {
                'limit': limit,
                'offset': offset,
                'sort': 'updatedAt',
                'direction': 'DESC'
            }
            
            response = self.session.post(
                urljoin(self.base_url, '/api/collections.list'),
                json=data
            )
            
            return self._handle_response(response, "list_collections")
            
        except Exception as e:
            return APIResponse(success=False, data={}, error=str(e))
    
    def list_documents(self, collection_id: str, limit: int = 25, 
                      offset: int = 0) -> APIResponse:
        """List documents in a collection."""
        try:
            data = {
                'collectionId': collection_id,
                'limit': limit,
                'offset': offset,
                'sort': 'updatedAt',
                'direction': 'DESC'
            }
            
            response = self.session.post(
                urljoin(self.base_url, '/api/documents.list'),
                json=data
            )
            
            return self._handle_response(response, f"list_documents({collection_id})")
            
        except Exception as e:
            return APIResponse(success=False, data={}, error=str(e))
    
    def search_documents(self, query: str, collection_id: Optional[str] = None,
                        limit: int = 25) -> APIResponse:
        """Search for documents."""
        try:
            data = {
                'query': query,
                'limit': limit
            }
            
            if collection_id:
                data['collectionId'] = collection_id
            
            response = self.session.post(
                urljoin(self.base_url, '/api/documents.search'),
                json=data
            )
            
            return self._handle_response(response, f"search_documents({query})")
            
        except Exception as e:
            return APIResponse(success=False, data={}, error=str(e))