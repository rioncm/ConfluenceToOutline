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
        
    def upload_space(self, space_key: str, force_mode: bool = False) -> bool:
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
                error_msg = f"Failed to create collection for space: {space_key}"
                self._track_collection_failure(space_data, error_msg)
                self.logger.error(error_msg)
                # Save the failure state
                space_file = self.output_dir / f"{space_key}.json"
                with open(space_file, 'w', encoding='utf-8') as f:
                    json.dump(space_data, f, indent=2, ensure_ascii=False)
                return False
                
            # Step 2: Upload all content items as documents
            success = self._upload_documents_recursive(
                space_data["space_content"], 
                collection_id,
                None,  # No parent document for root items
                space_data,  # Pass space_data for attachment access
                skip_root_space_page=True,  # Skip the root space page
                force_mode=force_mode  # Pass force mode flag
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
        Create a single collection for the entire space, or use existing one if found
        The space root page content goes into the collection description
        
        Args:
            space_data: Complete space data from JSON
            
        Returns:
            Collection ID if successful (existing or newly created), None otherwise
        """
        space_name = space_data["space_name"]
        
        # First, check if we already have a collection_id stored from previous runs
        stored_collection_id = space_data.get("processing_stats", {}).get("collection_id")
        if stored_collection_id:
            # Verify the stored collection still exists and is accessible
            if self._check_collection_exists(stored_collection_id, space_name):
                self.logger.info(f"Using stored collection ID from previous run '{space_name}' (ID: {stored_collection_id})")
                return stored_collection_id
            else:
                self.logger.warning(f"Stored collection ID {stored_collection_id} no longer valid, will search/create new one")
        
        # Check if a collection with this name already exists
        existing_collection_id = self._find_existing_collection(space_name)
        if existing_collection_id:
            self.logger.info(f"Found existing collection '{space_name}' (ID: {existing_collection_id})")
            return existing_collection_id
        
        # No existing collection found, create a new one
        self.logger.info(f"Creating new collection for space: {space_name}")
        
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
        
        response = self._make_api_request_with_retry('POST', url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                collection_id = data.get("data", {}).get("id")
                self.logger.info(f"Created collection: {space_data['space_name']} (ID: {collection_id})")
                return collection_id
            else:
                error_msg = data.get('error', 'Unknown error')
                self.logger.error(f"API returned ok=false: {error_msg}")
                return None
        else:
            self.logger.error(f"Failed to create collection {space_data['space_name']}: {response.status_code} {response.text}")
            return None
    
    def _list_collections(self) -> Optional[List[Dict[str, Any]]]:
        """
        List all collections using the Outline API
        
        Returns:
            List of collection data dictionaries if successful, None otherwise
        """
        url = f"{self.api_base_url}/api/collections.list"
        
        try:
            response = self._make_api_request_with_retry('POST', url, json={})
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    collections = data.get("data", [])
                    self.logger.debug(f"Retrieved {len(collections)} collections from API")
                    return collections
                else:
                    self.logger.error(f"API returned ok=false when listing collections: {data.get('error', 'Unknown error')}")
                    return None
            else:
                self.logger.error(f"Failed to list collections: {response.status_code} {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"Exception occurred while listing collections: {str(e)}")
            return None
    
    def _find_existing_collection(self, space_name: str) -> Optional[str]:
        """
        Find an existing collection by exact name match
        
        Args:
            space_name: The space name to search for (exact match)
            
        Returns:
            Collection ID if found, None otherwise
        """
        collections = self._list_collections()
        if not collections:
            self.logger.debug("No collections retrieved, assuming none exist")
            return None
            
        # Look for exact name matches
        matches = []
        for collection in collections:
            if collection.get("name") == space_name:
                matches.append(collection)
        
        if not matches:
            self.logger.debug(f"No existing collection found with exact name '{space_name}'")
            return None
        elif len(matches) == 1:
            # Single match - return the ID
            collection_id = matches[0].get("id")
            self.logger.info(f"Found existing collection '{space_name}' (ID: {collection_id})")
            return collection_id
        else:
            # Multiple matches - need to resolve ambiguity
            self.logger.warning(f"Found {len(matches)} collections with name '{space_name}' - resolving ambiguity")
            selected_collection = self._handle_collection_ambiguity(matches, space_name)
            if selected_collection:
                collection_id = selected_collection.get("id")
                self.logger.info(f"User selected collection '{space_name}' (ID: {collection_id})")
                return collection_id
            else:
                self.logger.info("User chose to quit - no collection selected")
                return None
    
    def _handle_collection_ambiguity(self, matches: List[Dict[str, Any]], space_name: str) -> Optional[Dict[str, Any]]:
        """
        Present user with collection choices when multiple collections have the same name
        
        Args:
            matches: List of collection dictionaries with matching names
            space_name: The space name being searched for
            
        Returns:
            Selected collection dictionary or None if user quits
        """
        print(f"\n⚠️  Ambiguous Collections Identified for '{space_name}':")
        
        # Display options with details
        for i, collection in enumerate(matches, 1):
            collection_id = collection.get("id", "unknown")
            # Try to get document count if available
            doc_count = "unknown"
            if "documents" in collection:
                doc_count = str(len(collection["documents"]))
            elif "documentCount" in collection:
                doc_count = str(collection["documentCount"])
            
            print(f"  {i}. {space_name} UUID=\"{collection_id}\" documents={doc_count}")
        
        # Get user selection
        while True:
            try:
                choice = input(f"\nPlease select a target by number (1-{len(matches)}) OR 'Q/q' to quit: ").strip()
                
                if choice.lower() == 'q':
                    return None
                    
                choice_num = int(choice)
                if 1 <= choice_num <= len(matches):
                    selected = matches[choice_num - 1]
                    print(f"Selected: {space_name} (ID: {selected.get('id')})")
                    return selected
                else:
                    print(f"❌ Please enter a number between 1 and {len(matches)}, or 'Q' to quit")
                    
            except ValueError:
                print("❌ Please enter a valid number or 'Q' to quit")
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Operation cancelled by user")
                return None
    
    def _check_collection_exists(self, collection_id: str, expected_name: str) -> bool:
        """
        Check if a collection exists and has the expected name
        
        Args:
            collection_id: The collection UUID to check
            expected_name: The expected name of the collection
            
        Returns:
            True if collection exists and name matches, False otherwise
        """
        if not collection_id or not collection_id.strip():
            return False
            
        collections = self._list_collections()
        if not collections:
            return False
            
        # Look for the collection by ID and verify name
        for collection in collections:
            if collection.get("id") == collection_id:
                if collection.get("name") == expected_name:
                    self.logger.debug(f"Collection {collection_id} exists with expected name '{expected_name}'")
                    return True
                else:
                    self.logger.warning(f"Collection {collection_id} exists but name mismatch: expected '{expected_name}', got '{collection.get('name')}'")
                    return False
                    
        self.logger.debug(f"Collection {collection_id} not found in collection list")
        return False
    
    def _track_document_failure(self, item: Dict[str, Any], error_message: str) -> None:
        """
        Track a document processing failure in the item data
        
        Args:
            item: The document item that failed
            error_message: The error message to record
        """
        if "processing_errors" not in item:
            item["processing_errors"] = []
        
        error_record = {
            "timestamp": datetime.now().isoformat(),
            "error": error_message,
            "retry_count": len(item["processing_errors"])  # Count of previous failures
        }
        
        item["processing_errors"].append(error_record)
        item["created"] = False  # Mark as not created due to error
        
        self.logger.error(f"Document processing failure recorded for '{item['title']}': {error_message}")
    
    def _track_collection_failure(self, space_data: Dict[str, Any], error_message: str) -> None:
        """
        Track a collection-level failure in the space data
        
        Args:
            space_data: The space data dictionary
            error_message: The error message to record
        """
        if "processing_stats" not in space_data:
            space_data["processing_stats"] = {}
        if "collection_errors" not in space_data["processing_stats"]:
            space_data["processing_stats"]["collection_errors"] = []
        
        error_record = {
            "timestamp": datetime.now().isoformat(),
            "error": error_message
        }
        
        space_data["processing_stats"]["collection_errors"].append(error_record)
        self.logger.error(f"Collection processing failure recorded: {error_message}")
    
    def _make_api_request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Make an API request with retry logic for rate limiting (429 errors)
        
        Args:
            method: HTTP method ('GET', 'POST', etc.)
            url: The API endpoint URL
            **kwargs: Additional arguments to pass to requests method
            
        Returns:
            Response object from successful request
            
        Raises:
            Exception: If all retries are exhausted or non-429 error occurs
        """
        import time
        import random
        
        max_retries = 5
        base_delay = 1  # Base delay in seconds
        max_delay = 60  # Maximum delay in seconds
        
        for attempt in range(max_retries + 1):
            try:
                # Make the request
                response = self.session.request(method, url, **kwargs)
                
                if response.status_code == 429:
                    if attempt == max_retries:
                        self.logger.error(f"Rate limiting: Exhausted all {max_retries} retries for {url}")
                        raise Exception(f"Rate limited after {max_retries} retries")
                    
                    # Calculate delay with exponential backoff + jitter
                    delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                    
                    # Check if server provided retry-after header
                    retry_after = response.headers.get('Retry-After')
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            pass  # Use calculated delay if header is not a number
                    
                    self.logger.warning(f"Rate limited (429) on {url}, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries + 1})")
                    time.sleep(delay)
                    continue
                    
                # Return response for all other status codes (let caller handle errors)
                return response
                
            except requests.exceptions.RequestException as e:
                if attempt == max_retries:
                    self.logger.error(f"Request failed after {max_retries} retries: {e}")
                    raise
                
                # Retry on network errors with shorter delay
                delay = min(base_delay * (attempt + 1), 10)
                self.logger.warning(f"Request failed ({e}), retrying in {delay}s (attempt {attempt + 1}/{max_retries + 1})")
                time.sleep(delay)
        
        raise Exception("Unexpected: Should not reach this point")
    
    def _save_space_data_immediately(self, space_data: Dict[str, Any], reason: str = "") -> None:
        """
        Immediately save space data to JSON file (for force mode and critical updates)
        
        Args:
            space_data: The space data dictionary to save
            reason: Optional reason for the save (for logging)
        """
        try:
            space_key = space_data.get("space_key", "unknown")
            space_file = self.output_dir / f"{space_key}.json"
            
            with open(space_file, 'w', encoding='utf-8') as f:
                json.dump(space_data, f, indent=2, ensure_ascii=False)
            
            if reason:
                self.logger.debug(f"Space data saved immediately: {reason}")
            else:
                self.logger.debug(f"Space data saved immediately for {space_key}")
                
        except Exception as e:
            self.logger.error(f"Failed to save space data immediately: {str(e)}")
    
    def _check_document_exists(self, document_id: str) -> bool:
        """
        Check if a document exists by its UUID using the documents.info API
        
        Args:
            document_id: The document UUID to check
            
        Returns:
            True if document exists and is accessible, False otherwise
        """
        if not document_id or not document_id.strip():
            return False
            
        url = f"{self.api_base_url}/api/documents.info"
        payload = {"id": document_id}
        
        try:
            response = self._make_api_request_with_retry('POST', url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    self.logger.debug(f"Document {document_id} exists and is accessible")
                    return True
                else:
                    self.logger.debug(f"Document {document_id} does not exist or is not accessible")
                    return False
            else:
                self.logger.debug(f"Failed to check document {document_id}: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.debug(f"Exception occurred while checking document {document_id}: {str(e)}")
            return False
    
    def _upload_documents_recursive(
        self, 
        content_items: List[Dict[str, Any]], 
        collection_id: str,
        parent_document_id: Optional[str],
        space_data: Dict[str, Any],
        skip_root_space_page: bool = False,
        force_mode: bool = False
    ) -> bool:
        """
        Recursively upload content items as documents
        
        Args:
            content_items: List of content items to upload
            collection_id: ID of the collection to put documents in
            parent_document_id: ID of parent document (None for root items)
            skip_root_space_page: Whether to skip the first item (root space page)
            force_mode: If True, ignore 'created' status and process all items
            
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
                        skip_root_space_page=False,  # Don't skip children
                        force_mode=force_mode  # Pass force mode down
                    )
                    if not success:
                        self.logger.warning(f"Some children failed for root space page: {item['title']}")
                continue
            
            # Check if document already exists (by UUID or created flag)
            existing_uuid = item.get("page_uuid")
            is_marked_created = item.get("created", False)
            document_exists_in_api = False
            
            # If we have a UUID, check if document actually exists in the API
            if existing_uuid and existing_uuid != collection_id:  # Don't check collection ID as document
                document_exists_in_api = self._check_document_exists(existing_uuid)
                if document_exists_in_api:
                    self.logger.info(f"Document exists in API with UUID {existing_uuid}: {item['title']}")
                else:
                    self.logger.info(f"Document UUID {existing_uuid} not found in API, will recreate: {item['title']}")
            
            # Determine processing strategy based on existence and force mode
            if force_mode and is_marked_created and document_exists_in_api and existing_uuid:
                # FORCE MODE: Update existing document
                document_id = existing_uuid
                self.logger.info(f"FORCE MODE: Updating existing document: {item['title']} (UUID: {existing_uuid})")
                
                # Update document content
                updated_content = item.get("md_content", "")
                if not updated_content.strip():
                    updated_content = f"# {item['title']}\n\nContent not available."
                
                # Update the document
                update_success = self._update_document_content(document_id, item["title"], updated_content)
                if update_success:
                    self.logger.info(f"Successfully updated document content: {item['title']}")
                    
                    # Process attachments if any
                    if item.get("attachments"):
                        self.logger.info(f"Processing attachments for updated document: {item['title']}")
                        self._upload_attachments_for_document(item, document_id, space_data)
                else:
                    error_msg = f"Failed to update document content: {item['title']}"
                    self._track_document_failure(item, error_msg)
                
                # Process children regardless of update success
                if item.get("children"):
                    success = self._upload_documents_recursive(
                        item["children"], 
                        collection_id, 
                        document_id,  # This document becomes the parent
                        space_data,
                        skip_root_space_page=False,
                        force_mode=force_mode  # Pass force mode down
                    )
                    if not success:
                        self.logger.warning(f"Some children failed for updated document: {item['title']}")
                
                continue
                
            elif not force_mode and ((is_marked_created and document_exists_in_api) or (is_marked_created and not existing_uuid)):
                # NORMAL MODE: Skip existing documents but process attachments if needed
                document_id = existing_uuid
                
                # Check if there are pending attachments
                has_pending_attachments = self._has_pending_attachments(item)
                
                if has_pending_attachments and document_id:
                    self.logger.info(f"Document already created but has pending attachments: {item['title']}")
                    # Try to upload pending attachments
                    self._upload_attachments_for_document(item, document_id, space_data)
                    
                    # Save progress after attachment processing
                    space_file = self.output_dir / f"{space_data['space_key']}.json"
                    with open(space_file, 'w', encoding='utf-8') as f:
                        json.dump(space_data, f, indent=2, ensure_ascii=False)
                elif not document_id:
                    self.logger.warning(f"Document {item['title']} marked as created but has no valid page_uuid")
                else:
                    self.logger.info(f"Skipping already created document (no pending attachments): {item['title']}")
                
                # Process children regardless
                if item.get("children"):
                    success = self._upload_documents_recursive(
                        item["children"], 
                        collection_id, 
                        document_id,  # This document becomes the parent
                        space_data,
                        skip_root_space_page=False,
                        force_mode=force_mode  # Pass force mode down
                    )
                    if not success:
                        self.logger.warning(f"Some children failed for document: {item['title']}")
                        
                continue
                
            # Create this document
            success, document_id = self._create_document(item, collection_id, parent_document_id)
            if not success:
                error_msg = f"Failed to create document: {item['title']}"
                self._track_document_failure(item, error_msg)
                # Continue processing other items instead of failing completely
                continue
                
            # Update item with document ID and status
            item["page_uuid"] = document_id  # Keep same field name for compatibility
            item["parent_uuid"] = parent_document_id
            item["created"] = True
            
            self.logger.info(f"Created document: {item['title']} (ID: {document_id})")
            
            # In force mode, immediately save progress to prevent data loss
            if force_mode:
                self._save_space_data_immediately(space_data, f"Document created: {item['title']}")
            
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
                    skip_root_space_page=False,  # Don't skip children
                    force_mode=force_mode  # Pass force mode down
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
            response = self._make_api_request_with_retry('POST', url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    document_id = data.get("data", {}).get("id")
                    return True, document_id
                else:
                    error_msg = data.get('error', 'Unknown error')
                    self.logger.error(f"API returned ok=false for document {title}: {error_msg}")
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
            response = self._make_api_request_with_retry('POST', url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    self.logger.info(f"Successfully updated document content: {title}")
                    return True
                else:
                    error_msg = data.get('error', 'Unknown error')
                    self.logger.error(f"API returned ok=false for document update {title}: {error_msg}")
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
        Replace templated attachment paths with Outline API URLs in markdown content
        Handles both templated format {attachments/path} and direct paths
        
        Args:
            content: Original markdown content with templated or direct paths
            attachment_details: Dictionary of attachment information
            
        Returns:
            Updated markdown content with proper Outline API URLs
        """
        import re
        updated_content = content
        
        for original_path, details in attachment_details.items():
            if details.get("uploaded", False) and details.get("api_url"):
                api_url = details["api_url"]
                content_type = details.get("content_type", "")
                file_name = details.get("name", original_path.split("/")[-1])
                
                # Determine if this is an image
                is_image = content_type.startswith("image/") or any(
                    original_path.lower().endswith(ext) 
                    for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp']
                )
                
                # Replace templated format {attachments/path} first
                templated_path = f"{{{original_path}}}"
                if templated_path in updated_content:
                    if is_image:
                        updated_content = self._replace_templated_image_references(
                            updated_content, templated_path, api_url, file_name
                        )
                    else:
                        updated_content = self._replace_templated_document_references(
                            updated_content, templated_path, api_url, file_name
                        )
                
                # Also handle direct path references (fallback)
                if is_image:
                    updated_content = self._replace_image_references(updated_content, original_path, api_url, file_name)
                else:
                    updated_content = self._replace_document_references(updated_content, original_path, api_url, file_name)
        
        return updated_content
    
    def _replace_templated_image_references(self, content: str, templated_path: str, api_url: str, file_name: str) -> str:
        """
        Replace templated image references with proper Outline format
        
        Args:
            content: Content to update
            templated_path: Templated path like {attachments/path}
            api_url: Outline API URL for the attachment
            file_name: Original filename
            
        Returns:
            Updated content with proper image markdown
        """
        import re
        
        # Pattern to match templated image formats in markdown
        patterns = [
            # ![alt](templated_path)
            rf'!\[([^\]]*)\]\({re.escape(templated_path)}\)',
            # ![](templated_path) 
            rf'!\[\]\({re.escape(templated_path)}\)',
        ]
        
        # Replace each pattern with proper Outline format
        for pattern in patterns:
            def replacement(match):
                alt_text = match.group(1) if match.lastindex and match.lastindex >= 1 else ""
                if not alt_text:
                    alt_text = file_name.rsplit('.', 1)[0]  # Use filename without extension as alt
                
                return f'![{alt_text}]({api_url})'
            
            content = re.sub(pattern, replacement, content)
        
        return content
    
    def _replace_templated_document_references(self, content: str, templated_path: str, api_url: str, file_name: str) -> str:
        """
        Replace templated document attachment references with proper links
        
        Args:
            content: Content to update
            templated_path: Templated path like {attachments/path}
            api_url: Outline API URL for the attachment
            file_name: Original filename
            
        Returns:
            Updated content with proper document links
        """
        # Simple string replacement for templated format
        content = content.replace(templated_path, api_url)
        return content
    
    def _replace_image_references(self, content: str, original_path: str, api_url: str, file_name: str) -> str:
        """
        Replace image references with proper Outline format
        
        Args:
            content: Content to update
            original_path: Original Confluence attachment path
            api_url: Outline API URL for the attachment
            file_name: Original filename
            
        Returns:
            Updated content with proper image markdown
        """
        import re
        
        # Pattern to match various Confluence image formats
        patterns = [
            # Standard markdown image with alt text
            rf'!\[([^\]]*)\]\({re.escape(original_path)}\)',
            # Image with alt text and sizing (Confluence style)  
            rf'!\[([^\]]*)\]\({re.escape(original_path)}\s*\"[^\"]*\"\)',
            # Simple image reference
            rf'!\[\]\({re.escape(original_path)}\)',
            # Direct path references that should become images
            rf'\({re.escape(original_path)}\)',
        ]
        
        # Extract sizing information if present
        size_match = re.search(rf'{re.escape(original_path)}\s*\"\s*=(\d+)x(\d+)', content)
        size_attr = ""
        if size_match:
            width, height = size_match.groups()
            size_attr = f' \" ={width}x{height}\"'
        
        # Replace each pattern with proper Outline format
        for pattern in patterns:
            def replacement(match):
                alt_text = match.group(1) if match.lastindex and match.lastindex >= 1 else ""
                if not alt_text:
                    alt_text = file_name.rsplit('.', 1)[0]  # Use filename without extension as alt
                
                return f'![{alt_text}]({api_url}{size_attr})'
            
            content = re.sub(pattern, replacement, content)
        
        return content
    
    def _replace_document_references(self, content: str, original_path: str, api_url: str, file_name: str) -> str:
        """
        Replace document attachment references with proper links
        
        Args:
            content: Content to update  
            original_path: Original Confluence attachment path
            api_url: Outline API URL for the attachment
            file_name: Original filename
            
        Returns:
            Updated content with proper document links
        """
        # Simple string replacements for documents
        patterns_to_replace = [
            f"]({original_path})",
            f"({original_path})",
            original_path
        ]
        
        replacements = [
            f"]({api_url})",
            f"({api_url})", 
            f"[{file_name}]({api_url})"
        ]
        
        for old_pattern, new_replacement in zip(patterns_to_replace, replacements):
            content = content.replace(old_pattern, new_replacement)
        
        return content
    
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
        
        # Add unlinked attachments section
        updated_content = self._add_unlinked_attachments_section(updated_content, attachment_details)
        
        return updated_content
    
    def _add_unlinked_attachments_section(self, content: str, attachment_details: Dict[str, Dict[str, Any]]) -> str:
        """
        Add an "Attachments" section for any attachments not referenced in the content
        
        Args:
            content: Page content
            attachment_details: Dictionary of attachment information
            
        Returns:
            Content with attachments section appended if needed
        """
        unlinked_attachments = []
        all_attachments = []
        
        for original_path, details in attachment_details.items():
            if details.get("uploaded", False) and details.get("api_url"):
                # Check if this attachment is referenced in the content
                file_name = details.get("name", original_path.split("/")[-1])
                api_url = details["api_url"]
                templated_path = f"{{{original_path}}}"
                
                # Check if attachment is already referenced in content
                is_linked = (
                    original_path in content or 
                    api_url in content or
                    templated_path in content or
                    f"]({original_path})" in content or
                    f"({original_path})" in content
                )
                
                content_type = details.get("content_type", "")
                is_image = content_type.startswith("image/") or any(
                    original_path.lower().endswith(ext) 
                    for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp']
                )
                
                attachment_info = {
                    "name": file_name,
                    "url": api_url,
                    "is_image": is_image,
                    "content_type": content_type,
                    "uuid": details.get("attachment_id", ""),
                    "original_path": original_path
                }
                
                all_attachments.append(attachment_info)
                
                if not is_linked:
                    unlinked_attachments.append(attachment_info)
        
        # Add comprehensive attachments section 
        if all_attachments:
            attachments_section = "\n\n## Original Attachments\n\n"
            
            # Add unlinked attachments first if any exist
            if unlinked_attachments:
                attachments_section += "### Unlinked Attachments\n\n"
                for attachment in unlinked_attachments:
                    if attachment["is_image"]:
                        # Show images directly
                        attachments_section += f"![{attachment['name']}]({attachment['url']})\n\n"
                    else:
                        # Show documents as links
                        attachments_section += f"- [{attachment['name']}]({attachment['url']})\n"
                attachments_section += "\n"
            
            # Add detailed metadata for all attachments
            attachments_section += "### Attachment Details\n\n"
            for attachment in all_attachments:
                attachments_section += f"- **Content Type:** {attachment['content_type']} "
                attachments_section += f"**Original Name:** {attachment['name']} "
                attachments_section += f"**Uploaded UUID:** {attachment['uuid']}\n"
            
            content += attachments_section
            self.logger.info(f"Added attachments section with {len(unlinked_attachments)} unlinked of {len(all_attachments)} total attachments")
        
        return content
    
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