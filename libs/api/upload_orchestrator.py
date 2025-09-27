"""
Upload Orchestrator - Phase 3 API Integration

Coordinates the complete workflow for uploading processed HTML content to Outline,
including batch processing, progress tracking, and error handling.
"""

import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

from ..config import AppConfig
from ..logger import get_logger, ProgressLogger
from .outline import OutlineAPIClient


@dataclass
class UploadResult:
    """Result of uploading a single file."""
    success: bool
    file_path: str
    document_id: Optional[str] = None
    document_url: Optional[str] = None
    error: Optional[str] = None
    duration: float = 0.0


@dataclass
class BatchUploadResult:
    """Result of a batch upload operation."""
    total_files: int
    successful_uploads: int = 0
    failed_uploads: int = 0
    results: List[UploadResult] = field(default_factory=list)
    duration: float = 0.0
    collection_id: Optional[str] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_files == 0:
            return 0.0
        return (self.successful_uploads / self.total_files) * 100


class UploadOrchestrator:
    """Orchestrates the complete upload workflow for processed HTML files."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.logger = get_logger(__name__)
        self.api_client = OutlineAPIClient(config.api)
        
    def upload_batch(self, html_dir: str, collection_name: str = "Imported Documents",
                    collection_description: str = "Documents imported from HTML files",
                    max_concurrent: int = 3) -> BatchUploadResult:
        """
        Upload a batch of HTML files to Outline.
        
        Args:
            html_dir: Directory containing HTML files to upload
            collection_name: Name for the collection to create/use
            collection_description: Description for the collection
            max_concurrent: Maximum concurrent uploads (not implemented yet)
            
        Returns:
            BatchUploadResult with detailed statistics
        """
        start_time = time.time()
        html_path = Path(html_dir)
        
        if not html_path.exists():
            self.logger.error(f"HTML directory not found: {html_dir}")
            return BatchUploadResult(total_files=0, duration=0.0)
            
        # Find all HTML files recursively
        html_files = list(html_path.rglob("*.html"))
        if not html_files:
            self.logger.warning(f"No HTML files found in: {html_dir}")
            return BatchUploadResult(total_files=0, duration=0.0)
            
        self.logger.info(f"Found {len(html_files)} HTML files to upload")
        result = BatchUploadResult(total_files=len(html_files))
        
        # Test API connection first
        self.logger.info("Testing API connection...")
        connection_test = self.api_client.test_connection()
        if not connection_test.success:
            self.logger.error(f"API connection failed: {connection_test.error}")
            result.duration = time.time() - start_time
            return result
            
        # Create or find collection
        self.logger.info("Setting up collection...")
        collection_result = self._ensure_collection(collection_name, collection_description)
        if not collection_result.success:
            self.logger.error(f"Failed to create collection: {collection_result.error}")
            result.duration = time.time() - start_time
            return result
            
        collection_id = collection_result.data.get('data', {}).get('id')
        result.collection_id = collection_id
        self.logger.info(f"Using collection ID: {collection_id}")
        
        # Process files one by one (sequential for now)
        progress_logger = ProgressLogger(self.logger, "File uploads", len(html_files))
        
        for i, html_file in enumerate(html_files, 1):
            try:
                upload_result = self._upload_single_file(html_file, collection_id)
                result.results.append(upload_result)
                
                if upload_result.success:
                    result.successful_uploads += 1
                    self.logger.info(f"✅ Uploaded: {html_file.name}")
                    progress_logger.update(1, f"Uploaded {html_file.name}")
                else:
                    result.failed_uploads += 1
                    self.logger.warning(f"❌ Failed: {html_file.name} - {upload_result.error}")
                    progress_logger.update(1, f"Failed {html_file.name}")
                    
                # Small delay to avoid overwhelming the API
                time.sleep(0.5)
                
            except Exception as e:
                error_result = UploadResult(
                    success=False, 
                    file_path=str(html_file),
                    error=str(e)
                )
                result.results.append(error_result)
                result.failed_uploads += 1
                self.logger.error(f"❌ Exception uploading {html_file.name}: {e}")
        
        progress_logger.complete("Batch upload finished")
        result.duration = time.time() - start_time
        self._log_batch_summary(result)
        
        return result
    
    def _ensure_collection(self, name: str, description: str) -> Any:
        """Create collection or find existing one with the same name."""
        # First, try to find existing collection
        collections_result = self.api_client.list_collections()
        
        if collections_result.success:
            collections = collections_result.data.get('data', [])
            for collection in collections:
                if collection.get('name') == name:
                    self.logger.info(f"Found existing collection: {name}")
                    return collections_result  # Return the list result, caller extracts ID
                    
        # Collection doesn't exist, create it
        self.logger.info(f"Creating new collection: {name}")
        return self.api_client.create_collection(name, description)
    
    def _upload_single_file(self, html_file: Path, collection_id: str) -> UploadResult:
        """Upload a single HTML file to Outline."""
        start_time = time.time()
        
        try:
            # Read and prepare content
            content = html_file.read_text(encoding='utf-8')
            title = self._extract_title_from_html(content, html_file.name)
            
            # Create document
            doc_result = self.api_client.create_document(
                collection_id=collection_id,
                title=title,
                content=content,
                publish=True
            )
            
            duration = time.time() - start_time
            
            if doc_result.success:
                doc_data = doc_result.data.get('data', {})
                return UploadResult(
                    success=True,
                    file_path=str(html_file),
                    document_id=doc_data.get('id'),
                    document_url=doc_data.get('url'),
                    duration=duration
                )
            else:
                return UploadResult(
                    success=False,
                    file_path=str(html_file),
                    error=doc_result.error,
                    duration=duration
                )
                
        except Exception as e:
            return UploadResult(
                success=False,
                file_path=str(html_file),
                error=str(e),
                duration=time.time() - start_time
            )
    
    def _extract_title_from_html(self, content: str, fallback_name: str) -> str:
        """Extract title from HTML content or generate from filename."""
        import re
        
        # Try to find title tag
        title_match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
        if title_match:
            title = title_match.group(1).strip()
            # Clean up title
            title = re.sub(r'<[^>]+>', '', title)  # Remove any HTML tags
            title = ' '.join(title.split())  # Normalize whitespace
            if title and len(title) > 3:  # Make sure it's meaningful
                return title
        
        # Try to find first h1
        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.IGNORECASE | re.DOTALL)
        if h1_match:
            title = h1_match.group(1).strip()
            title = re.sub(r'<[^>]+>', '', title)
            title = ' '.join(title.split())
            if title and len(title) > 3:
                return title
        
        # Fallback to filename without extension
        title = Path(fallback_name).stem
        # Convert underscores and dashes to spaces, title case
        title = title.replace('_', ' ').replace('-', ' ')
        title = ' '.join(word.capitalize() for word in title.split())
        
        return title or "Untitled Document"
    
    def _log_batch_summary(self, result: BatchUploadResult) -> None:
        """Log comprehensive summary of batch upload results."""
        self.logger.info("=" * 60)
        self.logger.info("BATCH UPLOAD SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Total files processed: {result.total_files}")
        self.logger.info(f"Successful uploads: {result.successful_uploads}")
        self.logger.info(f"Failed uploads: {result.failed_uploads}")
        self.logger.info(f"Success rate: {result.success_rate:.1f}%")
        self.logger.info(f"Total duration: {result.duration:.2f} seconds")
        
        if result.collection_id:
            self.logger.info(f"Collection ID: {result.collection_id}")
            
        if result.failed_uploads > 0:
            self.logger.info("\nFailed uploads:")
            for upload_result in result.results:
                if not upload_result.success:
                    filename = Path(upload_result.file_path).name
                    self.logger.info(f"  - {filename}: {upload_result.error}")
                    
        # Show first few successful uploads as examples
        successful_results = [r for r in result.results if r.success]
        if successful_results:
            self.logger.info(f"\nFirst {min(3, len(successful_results))} successful uploads:")
            for upload_result in successful_results[:3]:
                filename = Path(upload_result.file_path).name
                self.logger.info(f"  ✅ {filename} -> {upload_result.document_url}")
        
        self.logger.info("=" * 60)