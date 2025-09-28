#!/usr/bin/env python3
"""
CORRECTED API Upload Manager for SpaceProcessor
Handles uploading space content to Outline API using the CORRECT API structure:

- Space = Collection (top-level container)
- All other things = Documents/Pages (with parent-child relationships)
- Attachments = Separate attachment objects
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import requests
from datetime import datetime
import mimetypes
import os


class ApiUploadManager:
    """
    Upload space content to Outline API using the CORRECT structure:
    - Space -> Collection
    - Everything else -> Document with parentDocumentId relationships
    """
    
    def __init__(self, base_path: Path, api_base_url: str, api_token: str):
        self.base_path = Path(base_path)
        self.output_dir = self.base_path / "output"
        self.api_base_url = api_base_url.rstrip('/')
        self.api_token = api_token
        
        # Set up API session
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        # Don't set up logging configuration here - it should be done by the calling application
        
    def upload_space(self, space_key: str) -> bool:
        """
        Upload a complete space to the API
        
        Workflow:
        1. Create a Collection for the space
        2. Create all content as Documents with parent-child relationships
        
        Args:
            space_key: Space key (e.g., 'is')
            
        Returns:
            True if successful, False otherwise
        """
        space_file = self.output_dir / f"{space_key}.json"
        if not space_file.exists():
            self.logger.error(f"Space file not found: {space_file}")
            return False
            
        # Load the space JSON
        with open(space_file, 'r', encoding='utf-8') as f:
            space_data = json.load(f)
            
        # Start upload process
        self.logger.info(f"Starting upload for space: {space_data['space_name']} ({space_key})")
        
        try:
            # Step 1: Create the collection for this space
            collection_id = self._create_collection_for_space(space_data)
            if not collection_id:
                self.logger.error(f"Failed to create collection for space: {space_key}")
                return False
                
            # Step 2: Upload all content items as documents
            success = self._upload_documents_recursive(
                space_data["space_content"], 
                collection_id,
                None,  # No parent document for root items
                space_data,  # Pass space_data for attachment access
                skip_root_space_page=True  # Skip the root space page
            )
            
            # Always save partial progress, even if not completely successful
            space_data["processing_stats"]["uploaded_at"] = datetime.now().isoformat()
            space_data["processing_stats"]["collection_id"] = collection_id
            
            # Check completion status
            def count_created(items):
                created = total = 0
                for item in items:
                    total += 1
                    if item.get("created", False):
                        created += 1
                    if item.get("children"):
                        child_created, child_total = count_created(item["children"])
                        created += child_created
                        total += child_total
                return created, total
            
            created_count, total_count = count_created(space_data["space_content"])
            success = (created_count == total_count)  # Redefine success based on actual completion
            space_data["processing_stats"]["upload_successful"] = success
            
            # Save updated JSON
            with open(space_file, 'w', encoding='utf-8') as f:
                json.dump(space_data, f, indent=2, ensure_ascii=False)
                
            if success:
                self.logger.info(f"Successfully uploaded space: {space_key} ({created_count}/{total_count} documents)")
            else:
                self.logger.warning(f"Partially uploaded space: {space_key} ({created_count}/{total_count} documents)")
            return success
                
        except Exception as e:
            self.logger.error(f"Error uploading space {space_key}: {e}")
            return False
    
    def _create_collection_for_space(self, space_data: Dict[str, Any]) -> Optional[str]:
        """
        Create a single collection for the entire space
        The space root page content goes into the collection description
        
        Args:
            space_data: Complete space data from JSON
            
        Returns:
            Collection ID if successful, None otherwise
        """
        url = f"{self.api_base_url}/api/collections.create"
        
        # Find the root space page content to use as description
        root_page_content = ""
        space_content = space_data.get("space_content", [])
        if space_content:
            # The first item should be the root space page
            root_item = space_content[0]
            if root_item.get("title") == space_data["space_name"]:
                root_page_content = root_item.get("md_content", "")
        
        # Use root page content as description, fallback to default
        description = root_page_content if root_page_content.strip() else f"Imported from Confluence space: {space_data['space_key']}"
        
        # Prepare payload for collection creation
        payload = {
            "name": space_data["space_name"],
            "description": description,
            "color": "#4E5C6E",  # Default blue-gray
            "icon": "collection"  # Default icon
        }
        
        response = self.session.post(url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                collection_id = data.get("data", {}).get("id")
                self.logger.info(f"Created collection: {space_data['space_name']} (ID: {collection_id})")
                return collection_id
            else:
                self.logger.error(f"API returned ok=false: {data.get('error', 'Unknown error')}")
                return None
        else:
            self.logger.error(f"Failed to create collection {space_data['space_name']}: {response.status_code} {response.text}")
            return None
    
    def _upload_documents_recursive(
        self, 
        content_items: List[Dict[str, Any]], 
        collection_id: str,
        parent_document_id: Optional[str],
        space_data: Dict[str, Any],
        skip_root_space_page: bool = False
    ) -> bool:
        """
        Recursively upload content items as documents
        
        Args:
            content_items: List of content items to upload
            collection_id: ID of the collection to put documents in
            parent_document_id: ID of parent document (None for root items)
            skip_root_space_page: Whether to skip the first item (root space page)
            
        Returns:
            True if all items uploaded successfully, False otherwise
        """
        for i, item in enumerate(content_items):
            # Skip the root space page as its content is now in collection description
            if skip_root_space_page and i == 0:
                # Mark as created and process children only
                item["page_uuid"] = collection_id  # Reference the collection
                item["parent_uuid"] = None
                item["created"] = True
                
                self.logger.info(f"Skipped root space page (content in collection description): {item['title']}")
                
                # Process children with no parent (they become top-level documents)
                if item.get("children"):
                    success = self._upload_documents_recursive(
                        item["children"], 
                        collection_id, 
                        None,  # No parent for root space page children
                        space_data,  # Pass space_data for attachment access
                        skip_root_space_page=False  # Don't skip children
                    )
                    if not success:
                        self.logger.warning(f"Some children failed for root space page: {item['title']}")
                continue
            
            # Check if already created
            if item.get("created", False):
                # Document is created, but check if there are pending attachments
                has_pending_attachments = self._has_pending_attachments(item)
                
                if has_pending_attachments:
                    self.logger.info(f"Document already created but has pending attachments: {item['title']}")
                    document_id = item.get("page_uuid")
                    if document_id:
                        # Try to upload pending attachments
                        self._upload_attachments_for_document(item, document_id, space_data)
                        
                        # Save progress after attachment processing
                        space_file = self.output_dir / f"{space_data['space_name']}.json"
                        with open(space_file, 'w', encoding='utf-8') as f:
                            json.dump(space_data, f, indent=2, ensure_ascii=False)
                    else:
                        self.logger.warning(f"Document {item['title']} marked as created but has no page_uuid")
                else:
                    self.logger.info(f"Skipping already created document (no pending attachments): {item['title']}")
                
                # Process children regardless
                if item.get("children"):
                    success = self._upload_documents_recursive(
                        item["children"], 
                        collection_id, 
                        item.get("page_uuid"),  # This document becomes the parent
                        space_data,
                        skip_root_space_page=False
                    )
                    if not success:
                        self.logger.warning(f"Some children failed for document: {item['title']}")
                        
                continue
                
            # Create this document
            success, document_id = self._create_document(item, collection_id, parent_document_id)
            if not success:
                self.logger.error(f"Failed to create document: {item['title']}")
                # Continue processing other items instead of failing completely
                continue
                
            # Update item with document ID and status
            item["page_uuid"] = document_id  # Keep same field name for compatibility
            item["parent_uuid"] = parent_document_id
            item["created"] = True
            
            self.logger.info(f"Created document: {item['title']} (ID: {document_id})")
            
            # Upload attachments for this document
            if item.get("attachments") and document_id:
                self.logger.info(f"Uploading {len(item['attachments'])} attachments for document: {item['title']}")
                attachment_success = self._upload_attachments_for_document(
                    item, 
                    document_id, 
                    space_data
                )
                if attachment_success:
                    self.logger.info(f"Successfully uploaded all attachments for document: {item['title']}")
                else:
                    self.logger.warning(f"Some attachments failed to upload for document: {item['title']}")
                
                # Update document content with proper attachment links
                updated_content = self._prepare_content_with_attachments(item)
                original_content = item.get("md_content", "")
                
                self.logger.info(f"Content comparison for {item['title']}: Updated length={len(updated_content)}, Original length={len(original_content)}")
                
                if updated_content != original_content:
                    self.logger.info(f"Updating document content with attachment links: {item['title']}")
                    content_update_success = self._update_document_content(
                        document_id,
                        item["title"],
                        updated_content
                    )
                    if not content_update_success:
                        self.logger.warning(f"Failed to update document content for: {item['title']}")
                else:
                    self.logger.info(f"No content changes needed for: {item['title']}")
                    # Still update with full content since we created with minimal content initially
                    if original_content:
                        self.logger.info(f"Updating document with full original content: {item['title']}")
                        self._update_document_content(document_id, item["title"], updated_content)
            
            # Process children with this document as parent
            if item.get("children"):
                success = self._upload_documents_recursive(
                    item["children"], 
                    collection_id, 
                    document_id,  # This document becomes the parent
                    space_data,  # Pass space_data for attachment access
                    skip_root_space_page=False  # Don't skip children
                )
                # Don't fail completely if children fail - continue with other items
                if not success:
                    self.logger.warning(f"Some children failed for document: {item['title']}")
                    
            # Longer delay to avoid rate limiting
            time.sleep(2.0)  # Increased to 2 seconds to be more conservative
            
        return True
        
    def _create_document(
        self, 
        item: Dict[str, Any], 
        collection_id: str,
        parent_document_id: Optional[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Create a single document via API
        
        Args:
            item: Item data from JSON
            collection_id: ID of the collection 
            parent_document_id: ID of parent document
            
        Returns:
            Tuple of (success, document_id)
        """
        url = f"{self.api_base_url}/api/documents.create"
        
        # Prepare document content - initially create with title only for attachment workflow
        title = item["title"]
        
        # Check if this document has attachments that need processing
        has_attachments = bool(item.get("attachments", []))
        
        if has_attachments:
            # Create with minimal content first, will update after attachment processing
            text = f"# {title}\n\n*Loading content with attachments...*"
        else:
            # No attachments, use full content
            text = item.get("md_content", "")
            
            # If there's no content, create a placeholder
            if not text.strip():
                if item["type"] == "collection":
                    text = f"# {title}\n\nThis section contains the following documents:"
                else:
                    text = f"# {title}\n\nContent not available."
        
        # Prepare payload
        payload = {
            "title": title,
            "text": text,
            "collectionId": collection_id,
            "publish": True  # Automatically publish the document
        }
        
        # Set parent if specified
        if parent_document_id:
            payload["parentDocumentId"] = parent_document_id
            
        try:
            response = self.session.post(url, json=payload)
            
            # Handle rate limiting with exponential backoff
            if response.status_code == 429:
                self.logger.warning(f"Rate limit hit for document {title}, retrying with backoff...")
                for retry in range(5):  # Increased retries
                    wait_time = (2 ** retry) * 3  # 3, 6, 12, 24, 48 seconds
                    self.logger.info(f"Waiting {wait_time} seconds before retry {retry + 1}/5")
                    time.sleep(wait_time)
                    response = self.session.post(url, json=payload)
                    if response.status_code != 429:
                        break
                else:
                    self.logger.error(f"Rate limit exceeded after 5 retries for document {title}")
                    return False, None
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    document_id = data.get("data", {}).get("id")
                    return True, document_id
                else:
                    self.logger.error(f"API returned ok=false for document {title}: {data.get('error', 'Unknown error')}")
                    return False, None
            else:
                error_text = response.text
                self.logger.error(f"Failed to create document {title}: {response.status_code} {error_text}")
                return False, None
                
        except Exception as e:
            self.logger.error(f"Error creating document {title}: {e}")
            return False, None
    
    def _update_document_content(
        self, 
        document_id: str,
        title: str, 
        content: str
    ) -> bool:
        """
        Update an existing document's content
        
        Args:
            document_id: ID of the document to update
            title: Document title (for logging)
            content: Updated markdown content
            
        Returns:
            True if update successful, False otherwise
        """
        url = f"{self.api_base_url}/api/documents.update"
        
        payload = {
            "id": document_id,
            "text": content,
            "publish": True
        }
        
        try:
            response = self.session.post(url, json=payload)
            
            # Handle rate limiting
            if response.status_code == 429:
                self.logger.warning(f"Rate limit hit for document update {title}, retrying...")
                for retry in range(3):
                    wait_time = (2 ** retry) * 2
                    time.sleep(wait_time)
                    response = self.session.post(url, json=payload)
                    if response.status_code != 429:
                        break
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    self.logger.info(f"Successfully updated document content: {title}")
                    return True
                else:
                    self.logger.error(f"API returned ok=false for document update {title}: {data.get('error', 'Unknown error')}")
                    return False
            else:
                error_text = response.text
                self.logger.error(f"Failed to update document {title}: {response.status_code} {error_text}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error updating document {title}: {e}")
            return False
    
    def _upload_attachments_for_document(
        self, 
        item: Dict[str, Any], 
        document_id: str,
        space_data: Dict[str, Any]
    ) -> bool:
        """
        Upload all attachments for a document and update references in content
        
        Args:
            item: Item data from JSON with attachments
            document_id: ID of the document these attachments belong to
            space_data: Complete space data for finding local files
            
        Returns:
            True if all attachments uploaded successfully, False otherwise
        """
        attachments = item.get("attachments", [])
        if not attachments:
            return True  # No attachments to upload
        
        # Get local folder path for finding attachment files
        local_folder = Path(self.base_path / space_data["local_folder"])
        
        success_count = 0
        total_attachments = len(attachments)
        
        # Initialize attachment tracking in the item
        if "attachment_details" not in item:
            item["attachment_details"] = {}
        
        for attachment_path in attachments:
            self.logger.info(f"Uploading attachment: {attachment_path}")
            
            # Skip if already uploaded
            if attachment_path in item["attachment_details"]:
                existing = item["attachment_details"][attachment_path]
                if existing.get("uploaded", False):
                    self.logger.info(f"Skipping already uploaded attachment: {attachment_path}")
                    success_count += 1
                    continue
            
            # Retry logic for attachment upload
            max_retries = 3
            retry_count = 0
            success = False
            attachment_info = None
            
            while retry_count < max_retries and not success:
                if retry_count > 0:
                    wait_time = (2 ** retry_count) * 2  # Exponential backoff
                    self.logger.info(f"Retrying attachment upload (attempt {retry_count + 1}/{max_retries}) after {wait_time}s: {attachment_path}")
                    time.sleep(wait_time)
                
                success, attachment_info = self._upload_single_attachment(
                    attachment_path, 
                    document_id, 
                    local_folder
                )
                retry_count += 1
            
            if success and attachment_info:
                # Store detailed attachment information
                item["attachment_details"][attachment_path] = {
                    "attachment_id": attachment_info["attachment_id"],
                    "original_path": attachment_path,
                    "api_url": attachment_info["api_url"],
                    "name": attachment_info["name"],
                    "content_type": attachment_info["content_type"],
                    "size": attachment_info["size"],
                    "uploaded": True,
                    "uploaded_at": datetime.now().isoformat(),
                    "document_id": document_id,
                    "retry_count": retry_count - 1
                }
                success_count += 1
                self.logger.info(f"Successfully uploaded attachment: {attachment_path} -> {attachment_info['attachment_id']}")
            else:
                # Store failure information with detailed error
                failure_info = {
                    "original_path": attachment_path,
                    "uploaded": False,
                    "upload_failed_at": datetime.now().isoformat(),
                    "error": f"Upload failed after {max_retries} attempts",
                    "retry_count": retry_count - 1
                }
                
                # Capture detailed error if available
                if hasattr(self, '_last_attachment_error'):
                    failure_info["detailed_error"] = self._last_attachment_error
                    delattr(self, '_last_attachment_error')  # Clean up
                
                item["attachment_details"][attachment_path] = failure_info
                self.logger.error(f"Failed to upload attachment after {max_retries} attempts: {attachment_path}")
        
        # Update markdown content with new attachment URLs
        if success_count > 0:
            item["md_content"] = self._replace_attachment_urls_in_content(
                item["md_content"], 
                item["attachment_details"]
            )
        
        return success_count == total_attachments
    
    def _has_pending_attachments(self, item: Dict[str, Any]) -> bool:
        """
        Check if a document has attachments that need to be uploaded
        
        Args:
            item: Document item to check
            
        Returns:
            True if there are pending attachments, False otherwise
        """
        attachments = item.get("attachments", [])
        if not attachments:
            return False
            
        attachment_details = item.get("attachment_details", {})
        
        # Check if any attachment is not uploaded or needs retry
        for attachment_path in attachments:
            if attachment_path not in attachment_details:
                return True  # No details means not attempted
                
            details = attachment_details[attachment_path]
            if not details.get("uploaded", False):
                return True  # Not successfully uploaded
                
        return False
    
    def _upload_single_attachment(
        self, 
        attachment_path: str, 
        document_id: str, 
        local_folder: Path
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Upload a single attachment file to Outline API using the two-phase process
        
        Args:
            attachment_path: Relative path to attachment (e.g. 'attachments/681672705/file.pdf')
            document_id: ID of document this attachment belongs to
            local_folder: Base folder containing the attachment files
            
        Returns:
            Tuple of (success, attachment_info_dict)
        """
        try:
            # Build full path to attachment file
            file_path = local_folder / attachment_path
            
            if not file_path.exists():
                self.logger.error(f"Attachment file not found: {file_path}")
                return False, None
            
            # Get file information
            file_size = file_path.stat().st_size
            content_type, _ = mimetypes.guess_type(str(file_path))
            if not content_type:
                content_type = "application/octet-stream"
            
            file_name = file_path.name
            
            # Phase 1: Create attachment record in Outline
            attachment_id, upload_info = self._create_attachment_record(
                file_name, content_type, file_size, document_id
            )
            
            if not attachment_id:
                return False, None
            
            # Phase 2: Upload file to storage
            if upload_info:
                upload_success = self._upload_file_to_storage(file_path, upload_info)
                
                if not upload_success:
                    self.logger.error(f"Failed to upload file to storage for attachment: {file_name}")
                    return False, None
            else:
                self.logger.error(f"No upload info received for attachment: {file_name}")
                return False, None
            
            # Build API redirect URL for this attachment
            api_url = f"{self.api_base_url}/api/attachments.redirect?id={attachment_id}"
            
            return True, {
                "attachment_id": attachment_id,
                "api_url": api_url,
                "name": file_name,
                "content_type": content_type,
                "size": file_size
            }
            
        except Exception as e:
            error_msg = f"Error uploading attachment {attachment_path}: {e}"
            self.logger.error(error_msg)
            # Store the error for the caller to access
            self._last_attachment_error = error_msg
            return False, None
    
    def _create_attachment_record(
        self, 
        name: str, 
        content_type: str, 
        size: int, 
        document_id: str
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Create attachment record in Outline (Phase 1 of upload)
        
        Args:
            name: File name
            content_type: MIME type
            size: File size in bytes
            document_id: Associated document ID
            
        Returns:
            Tuple of (attachment_id, upload_info)
        """
        url = f"{self.api_base_url}/api/attachments.create"
        
        payload = {
            "name": name,
            "contentType": content_type,
            "size": size,
            "documentId": document_id
        }
        
        try:
            response = self.session.post(url, json=payload)
            
            # Handle rate limiting
            if response.status_code == 429:
                self.logger.warning(f"Rate limit hit for attachment {name}, retrying...")
                for retry in range(3):
                    wait_time = (2 ** retry) * 2
                    time.sleep(wait_time)
                    response = self.session.post(url, json=payload)
                    if response.status_code != 429:
                        break
                        
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    attachment_data = data.get("data", {})
                    
                    # The attachment ID is nested under data.attachment.id
                    attachment_info = attachment_data.get("attachment", {})
                    attachment_id = attachment_info.get("id")
                    
                    # Extract upload information for Phase 2
                    upload_info = {
                        "upload_url": attachment_data.get("uploadUrl"),
                        "form_data": attachment_data.get("form", {}),
                        "max_upload_size": attachment_data.get("maxUploadSize")
                    }
                    
                    return attachment_id, upload_info
                else:
                    error_msg = f"API returned ok=false for attachment {name}: {data.get('error', 'No error message')}"
                    self.logger.error(error_msg)
                    self._last_attachment_error = error_msg
                    return None, None
            else:
                error_msg = f"Failed to create attachment record for {name}: HTTP {response.status_code} - {response.text[:200]}"
                self.logger.error(error_msg)
                self._last_attachment_error = error_msg
                return None, None
                
        except Exception as e:
            self.logger.error(f"Error creating attachment record for {name}: {e}")
            return None, None
    
    def _upload_file_to_storage(
        self, 
        file_path: Path, 
        upload_info: Dict[str, Any]
    ) -> bool:
        """
        Upload file to cloud storage (Phase 2 of upload)
        
        Args:
            file_path: Path to local file
            upload_info: Upload information from Phase 1
            
        Returns:
            True if upload successful, False otherwise
        """
        try:
            upload_url = upload_info.get("upload_url")
            form_data = upload_info.get("form_data", {})
            
            if not upload_url:
                self.logger.error(f"No upload URL provided for file: {file_path}")
                return False
            
            # Prepare multipart form data for file upload
            with open(file_path, 'rb') as f:
                files = {
                    'file': (file_path.name, f, mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream')
                }
                
                # Create a new session for the upload (don't use API session with auth headers)
                upload_session = requests.Session()
                
                response = upload_session.post(
                    upload_url,
                    data=form_data,
                    files=files
                )
            
            if response.status_code in [200, 201, 204]:
                return True
            else:
                error_msg = f"Failed to upload file {file_path.name} to storage: HTTP {response.status_code} - {response.text[:200]}"
                self.logger.error(error_msg)
                self._last_attachment_error = error_msg
                return False
                
        except Exception as e:
            error_msg = f"Error uploading file {file_path} to storage: {e}"
            self.logger.error(error_msg)
            self._last_attachment_error = error_msg
            return False
    
    def _replace_attachment_urls_in_content(
        self, 
        content: str, 
        attachment_details: Dict[str, Dict[str, Any]]
    ) -> str:
        """
        Replace local attachment paths with API URLs in markdown content
        
        Args:
            content: Original markdown content with local paths
            attachment_details: Dictionary of attachment information
            
        Returns:
            Updated markdown content with API URLs
        """
        updated_content = content
        
        for original_path, details in attachment_details.items():
            if details.get("uploaded", False) and details.get("api_url"):
                api_url = details["api_url"]
                
                # Simple string replacements for common patterns
                patterns_to_replace = [
                    f"![alt]({original_path})",
                    f"]({original_path})",
                    f"({original_path})",
                    original_path
                ]
                
                replacements = [
                    f"![alt]({api_url})",
                    f"]({api_url})",
                    f"({api_url})",
                    api_url
                ]
                
                for old_pattern, new_replacement in zip(patterns_to_replace, replacements):
                    updated_content = updated_content.replace(old_pattern, new_replacement)
        
        return updated_content
    
    def _prepare_content_with_attachments(self, item: Dict[str, Any]) -> str:
        """
        Prepare document content with proper attachment links
        
        Args:
            item: Document item with attachments and content
            
        Returns:
            Updated content with attachment links
        """
        content = item.get("md_content", "")
        attachments = item.get("attachments", [])
        attachment_details = item.get("attachment_details", {})
        
        if not attachments:
            return content
        
        # Start with the original content
        updated_content = content
        
        # First, replace any existing attachment references with API URLs
        updated_content = self._replace_attachment_urls_in_content(
            updated_content, 
            attachment_details
        )
        
        # Then, ensure all uploaded attachments have references in the content
        for attachment_path in attachments:
            details = attachment_details.get(attachment_path, {})
            if details.get("uploaded", False) and details.get("api_url"):
                api_url = details["api_url"]
                file_name = details.get("name", attachment_path.split("/")[-1])
                
                # Check if this attachment is already referenced in content
                if api_url not in updated_content and attachment_path not in updated_content:
                    # Add a reference to this attachment at the end of content
                    attachment_link = f"\n\n📎 **Attachment:** [{file_name}]({api_url})"
                    updated_content += attachment_link
                    self.logger.info(f"Added missing attachment link for: {file_name}")
        
        return updated_content
    
    def get_upload_status(self, space_key: str) -> Optional[Dict[str, Any]]:
        """
        Get upload status for a space
        
        Args:
            space_key: Space key to check
            
        Returns:
            Dictionary with status information or None if not found
        """
        space_file = self.output_dir / f"{space_key}.json"
        if not space_file.exists():
            return None
            
        with open(space_file, 'r', encoding='utf-8') as f:
            space_data = json.load(f)
        
        def count_items(items, created_count=0, total_count=0):
            for item in items:
                total_count += 1
                if item.get("created", False):
                    created_count += 1
                    
                if item.get("children"):
                    created_count, total_count = count_items(
                        item["children"], created_count, total_count
                    )
                    
            return created_count, total_count
        
        created_items, total_items = count_items(space_data["space_content"])
        completion_percentage = (created_items / total_items * 100) if total_items > 0 else 0
        
        # Get attachment statistics
        attachment_stats = self._get_attachment_statistics(space_data["space_content"])
        
        return {
            "created_items": created_items,
            "total_items": total_items,
            "completion_percentage": completion_percentage,
            "upload_successful": space_data.get("processing_stats", {}).get("upload_successful", False),
            "uploaded_at": space_data.get("processing_stats", {}).get("uploaded_at"),
            "collection_id": space_data.get("processing_stats", {}).get("collection_id"),
            "attachment_stats": attachment_stats
        }
    
    def _get_attachment_statistics(self, content_items: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Get statistics about attachment uploads
        
        Args:
            content_items: List of content items to analyze
            
        Returns:
            Dictionary with attachment statistics
        """
        stats = {
            "total_attachments": 0,
            "uploaded_attachments": 0,
            "failed_attachments": 0,
            "skipped_attachments": 0
        }
        
        def count_attachments(items):
            for item in items:
                attachment_details = item.get("attachment_details", {})
                for path, details in attachment_details.items():
                    stats["total_attachments"] += 1
                    if details.get("uploaded", False):
                        stats["uploaded_attachments"] += 1
                    elif details.get("upload_failed_at"):
                        stats["failed_attachments"] += 1
                    else:
                        stats["skipped_attachments"] += 1
                
                # Process children recursively
                if item.get("children"):
                    count_attachments(item["children"])
        
        count_attachments(content_items)
        return stats
    
    def reset_upload_status(self, space_key: str) -> bool:
        """
        Reset upload status for a space (mark all items as not created)
        
        Args:
            space_key: Space key to reset
            
        Returns:
            True if successful, False otherwise
        """
        space_file = self.output_dir / f"{space_key}.json"
        if not space_file.exists():
            return False
            
        try:
            with open(space_file, 'r', encoding='utf-8') as f:
                space_data = json.load(f)
            
            def reset_items(items):
                for item in items:
                    item["created"] = False
                    item["page_uuid"] = None
                    item["parent_uuid"] = None
                    
                    # Reset attachment details as well
                    if "attachment_details" in item:
                        item["attachment_details"] = {}
                    
                    if item.get("children"):
                        reset_items(item["children"])
            
            reset_items(space_data["space_content"])
            
            # Reset processing stats
            if "processing_stats" in space_data:
                space_data["processing_stats"].pop("uploaded_at", None)
                space_data["processing_stats"].pop("upload_successful", None)
                space_data["processing_stats"].pop("collection_id", None)
            
            # Save updated JSON
            with open(space_file, 'w', encoding='utf-8') as f:
                json.dump(space_data, f, indent=2, ensure_ascii=False)
                
            return True
            
        except Exception as e:
            self.logger.error(f"Error resetting upload status for {space_key}: {e}")
            return False