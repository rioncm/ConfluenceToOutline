# API Integration Guide

This document covers Phase 3 of the Information Systems Documentation Processor - API integration for uploading processed Confluence content to external systems.

## 🎯 Overview

Phase 3 integrates the processed documentation with external APIs (like Outline, Notion, etc.) using the structured data generated in Phase 2. The system is designed for reliability, error recovery, and batch processing.

## 📊 Data Flow

```
Phase 2 Output (structure.json) → API Integration → Target System
├── Navigation hierarchy
├── Page content (Markdown)  
├── Attachment metadata
└── File relationships
```

## 🔗 Supported APIs

### Outline API Integration
- **Authentication**: Bearer token via environment variables
- **Endpoints**: Collections, Documents, Attachments
- **Features**: Hierarchical document creation, attachment upload
- **Rate Limits**: Configurable with retry logic

### Configuration
```bash
# .env file
OUTLINE_API_KEY=your_api_key_here
OUTLINE_API_URL=https://your-instance.outline.com
```

## 🚀 API Commands

### Test API Connection
```bash
# Test basic connectivity
python main.py api-test --collections

# Test document listing
python main.py api-test --documents  

# Test specific collection
python main.py api-test --collections --documents --collection-id UUID
```

### Upload Content (Phase 3)
```bash
# Upload all processed content
python main.py api-upload

# Upload specific directory
python main.py api-upload --source output/Export-135853

# Dry run (validate without uploading)
python main.py api-upload --dry-run

# Resume failed upload
python main.py api-upload --resume
```

## 📋 API Upload Process

### Step 1: Validation
- Verify API credentials and connectivity
- Validate structure.json format and content
- Check attachment file availability
- Estimate upload requirements

### Step 2: Hierarchy Creation
- Create collection (if needed)
- Build navigation structure top-down
- Create parent documents before children
- Maintain UUID mapping for relationships

### Step 3: Content Upload
- Upload documents with Markdown content
- Process attachments (images, files)
- Update cross-references and links
- Verify upload integrity

### Step 4: Verification
- Validate complete hierarchy exists
- Check attachment availability
- Verify content integrity
- Generate upload report

## 🛠 Implementation Details

### API Client Architecture
```python
class OutlineAPI:
    def __init__(self, api_key: str, api_url: str):
        self.session = requests.Session()
        self.base_url = api_url
        self.headers = {'Authorization': f'Bearer {api_key}'}
    
    def create_collection(self, name: str) -> dict:
        """Create a new collection"""
        
    def create_document(self, collection_id: str, title: str, 
                       content: str, parent_id: str = None) -> dict:
        """Create a document with optional parent"""
        
    def upload_attachment(self, file_path: str, document_id: str) -> dict:
        """Upload file attachment to document"""
```

### Error Handling & Recovery
- **Transient Errors**: Automatic retry with exponential backoff
- **Rate Limiting**: Respect API limits with intelligent throttling
- **Partial Failures**: Resume capability for interrupted uploads
- **Rollback Support**: Ability to clean up failed uploads

### Progress Tracking
```python
class APIUploadProgress:
    """Track upload progress with resume capability"""
    
    def __init__(self, total_documents: int, total_attachments: int):
        self.total_docs = total_documents
        self.total_attachments = total_attachments
        self.completed_docs = 0
        self.completed_attachments = 0
        self.failed_items = []
    
    def save_checkpoint(self, file_path: str):
        """Save progress for resume capability"""
        
    def load_checkpoint(self, file_path: str) -> bool:
        """Load previous progress state"""
```

## 🔄 Upload Strategies

### Strategy 1: Complete Hierarchy First
1. Create all navigation containers (collections, folders)
2. Create all documents with minimal content
3. Update documents with full content and attachments
4. Verify and fix any broken relationships

**Pros**: Clear structure, easy to debug
**Cons**: Slower, requires multiple passes

### Strategy 2: Depth-First Upload
1. Create parent document with content
2. Upload attachments for parent
3. Recursively create children
4. Update cross-references

**Pros**: Faster, natural document flow
**Cons**: Complex rollback on failures

### Strategy 3: Batch Processing
1. Process documents in batches of configurable size
2. Handle attachments separately in batches
3. Update relationships after all content exists
4. Comprehensive verification at the end

**Pros**: Optimal for large datasets, good error recovery
**Cons**: Complex coordination, temporary inconsistent state

## 📊 Data Mapping

### Structure.json to API Mapping
```json
{
  "navigation": [
    {
      "title": "Help Docs",              // → Collection Name
      "type": "navigation",              // → Collection/Folder
      "path": ["Help Docs"],             // → URL slug path
      "children": [...],                 // → Nested structure
      "pages": [
        {
          "title": "Linux Administration", // → Document Title  
          "type": "page",                  // → Document
          "page_data": {
            "content": "# Title\n...",     // → Document Content
            "attachments": [...],          // → File Uploads
            "page_id": "2663809025"        // → Source Reference
          }
        }
      ]
    }
  ]
}
```

### Attachment Handling
```json
{
  "filename": "image.png",
  "local_path": "/path/to/file",         // → Upload Source
  "relative_path": "attachments/123/",   // → Original Reference
  "mime_type": "image/png",              // → Content-Type Header
  "size_bytes": 12345,                   // → Validation
  "referenced_in_content": true          // → Update Links
}
```

## 🔧 Configuration Options

### API Configuration
```python
@dataclass
class APIConfig:
    api_key: str
    api_url: str  
    timeout: int = 30                    # Request timeout
    max_retries: int = 3                 # Retry attempts
    batch_size: int = 10                 # Documents per batch
    rate_limit_delay: float = 1.0        # Seconds between requests
    max_concurrent: int = 4              # Parallel uploads
    resume_enabled: bool = True          # Support resume
    verify_uploads: bool = True          # Post-upload verification
```

### Upload Behavior
```bash
# Upload options
--dry-run              # Validate without uploading
--resume               # Continue from checkpoint  
--batch-size N         # Documents per batch
--max-retries N        # Retry attempts
--rate-limit-delay N   # Seconds between requests
--skip-attachments     # Upload documents only
--verify               # Verify uploads (default: true)
--rollback             # Remove uploaded content on failure
```

## 📈 Monitoring & Metrics

### Upload Metrics
- **Documents**: Created, updated, failed
- **Attachments**: Uploaded, failed, skipped
- **Performance**: Upload speed, API response times
- **Errors**: Rate limits, timeouts, validation failures

### Progress Reporting
```bash
API Upload Progress:
├── Collections: 1/1 created
├── Documents: 156/219 uploaded (71%)  
├── Attachments: 89/99 uploaded (90%)
├── Failed Items: 3 documents, 2 attachments
└── Estimated Time: 5 minutes remaining
```

### Log Integration
```python
logger.info(f"Starting API upload - {doc_count} documents, {att_count} attachments")
logger.info(f"Created collection: {collection_name} ({collection_id})")
logger.info(f"Uploaded document: {doc_title} ({doc_id})")
logger.warning(f"Rate limited - waiting {delay}s before retry")
logger.error(f"Failed to upload document: {doc_title} - {error}")
```

## 🚨 Error Recovery

### Common API Errors
- **401 Unauthorized**: Check API key and permissions
- **403 Forbidden**: Verify API access to collections/documents
- **429 Rate Limited**: Automatic retry with backoff
- **500 Server Error**: Retry with exponential backoff
- **Network Timeout**: Retry with extended timeout

### Recovery Strategies
```python
def handle_api_error(error: APIError, context: UploadContext):
    if error.code == 429:  # Rate limited
        delay = error.retry_after or calculate_backoff(context.retry_count)
        logger.warning(f"Rate limited - waiting {delay}s")
        time.sleep(delay)
        return RetryAction.RETRY
    
    elif error.code in [500, 502, 503]:  # Server errors
        if context.retry_count < max_retries:
            delay = exponential_backoff(context.retry_count)
            logger.warning(f"Server error - retrying in {delay}s")
            time.sleep(delay)
            return RetryAction.RETRY
        return RetryAction.FAIL
    
    else:  # Client errors (4xx)
        logger.error(f"Client error {error.code}: {error.message}")
        return RetryAction.SKIP
```

### Rollback Capability
```python
class UploadTransaction:
    """Track created resources for rollback capability"""
    
    def __init__(self):
        self.created_collections = []
        self.created_documents = []
        self.uploaded_attachments = []
    
    def rollback(self):
        """Clean up created resources in reverse order"""
        for attachment in reversed(self.uploaded_attachments):
            self.delete_attachment(attachment['id'])
        
        for document in reversed(self.created_documents):  
            self.delete_document(document['id'])
            
        for collection in reversed(self.created_collections):
            self.delete_collection(collection['id'])
```

## 🧪 Testing API Integration

### Unit Tests
```bash
# Test API client functionality
python -m pytest tests/test_api_client.py

# Test error handling
python -m pytest tests/test_api_errors.py

# Test data mapping
python -m pytest tests/test_api_mapping.py
```

### Integration Tests  
```bash
# Test against API sandbox
python -m pytest tests/test_api_integration.py --sandbox

# Test upload workflow
python -m pytest tests/test_upload_workflow.py --slow
```

### Manual Testing
```bash
# Test with small dataset
python main.py api-upload --source test_data --dry-run

# Test error recovery
python main.py api-upload --source test_data --max-retries 1

# Test resume functionality  
python main.py api-upload --source test_data --resume
```

## 📋 Best Practices

### API Usage
1. **Always test with dry-run first** before real uploads
2. **Monitor rate limits** and adjust delays accordingly
3. **Use batch processing** for large datasets
4. **Enable resume capability** for reliability
5. **Verify uploads** to ensure data integrity

### Error Handling
1. **Log all API interactions** for debugging
2. **Implement exponential backoff** for retries
3. **Distinguish transient vs permanent errors**
4. **Provide clear error messages** to users
5. **Support rollback** for failed uploads

### Performance
1. **Use concurrent uploads** where safe
2. **Process attachments separately** from documents
3. **Batch related operations** to reduce API calls
4. **Cache API responses** where appropriate
5. **Monitor and optimize** upload performance

---

## 🚀 Next Steps for Phase 3 Implementation

1. **Implement OutlineAPI client class**
2. **Create upload workflow orchestrator**  
3. **Add error handling and retry logic**
4. **Implement progress tracking and resume**
5. **Add comprehensive testing**
6. **Document API-specific configurations**

This foundation provides a robust framework for reliable API integration with any target system.