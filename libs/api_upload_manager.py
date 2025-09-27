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
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
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
                        skip_root_space_page=False  # Don't skip children
                    )
                    if not success:
                        self.logger.warning(f"Some children failed for root space page: {item['title']}")
                continue
            
            # Skip if already created
            if item.get("created", False):
                self.logger.info(f"Skipping already created document: {item['title']}")
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
            
            # Process children with this document as parent
            if item.get("children"):
                success = self._upload_documents_recursive(
                    item["children"], 
                    collection_id, 
                    document_id,  # This document becomes the parent
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
        
        # Prepare document content
        title = item["title"]
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
        
        return {
            "created_items": created_items,
            "total_items": total_items,
            "completion_percentage": completion_percentage,
            "upload_successful": space_data.get("processing_stats", {}).get("upload_successful", False),
            "uploaded_at": space_data.get("processing_stats", {}).get("uploaded_at"),
            "collection_id": space_data.get("processing_stats", {}).get("collection_id")
        }
    
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