# Confluence Space Processor

A clean, modular system for processing Confluence exports and uploading to Outline via API. Features a three-phase workflow with separation of concerns, comprehensive error handling, and resumable operations.

## 🏗️ Architecture Overview

The system uses a **clean architecture** approach with four distinct phases:

0. **Extract ZIPs** - Extract Confluence export ZIP files to input directories
1. **Process Input** - Extract complete space structure from `index.html`
2. **Extract Content** - Convert HTML to clean markdown without breadcrumbs
3. **API Upload** - Create collections and pages with proper parent-child relationships

## 🚀 Quick Start

```bash
# Setup
git clone <repository>
cd IS
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Outline API credentials:
# OUTLINE_API_URL=https://your-outline-instance.com/api
# OUTLINE_API_TOKEN=your_api_token_here
```

## 📋 Workflow

### Phase 0: Extract ZIP Files (Optional)
```bash
# Extract Confluence export ZIP files
python main.py extract-zips
```
- Extracts ZIP files from `zips/` directory to `input/` directories
- Uses secure extraction with safety checks against zip bombs
- Creates properly named directories (e.g., `Export-135853/`)
- **Skip this step if you already have extracted directories in `input/`**

### Phase 1: Process Input Directories
```bash
# Extract structure from all exports in input/
python main.py process-input
```
- Scans `input/Export-*/` directories for Confluence exports
- Extracts complete hierarchical structure from `index.html` files using DOM parser
- Creates `{space_key}.json` files in `output/` (e.g., `is.json`, `gi.json`)
- **Review and edit these JSON files before proceeding to next phase**

### Phase 2: Extract Content
```bash
# Extract markdown content for all spaces
python main.py extract-content

# Or process specific spaces
python main.py extract-content --spaces is gi
```
- Converts HTML files to clean markdown
- Removes breadcrumbs and duplicate titles (captured in Phase 1)
- Populates `md_content` fields in JSON files
- Handles attachments and embedded content

### Phase 3: API Upload  
```bash
# Upload specific spaces to Outline
python main.py api-upload --spaces is gi

# Force mode - update existing documents (bypasses 'created' status)
python main.py api-upload --spaces is gi --force
```
- Creates collections and pages via Outline API
- Maintains proper parent-child relationships using UUIDs
- Updates JSON files with creation status and UUIDs
- **Resumable**: Skips already created items if upload is interrupted
- **Force mode**: Updates existing documents with latest content
- **Collection deduplication**: Handles duplicate collection names with user interaction
- **Comprehensive retry logic**: Handles rate limiting and network errors with exponential backoff

## 📊 Status and Management

```bash
# Show status of all spaces
python main.py status

# Reset upload status to retry failed uploads
python main.py reset --spaces is gi

# Clean reset - remove all processed files (keeps ZIPs)
python main.py point-zero
```

## 🏁 Complete Example

```bash
# 0. Place Confluence export ZIP files in zips/
cp "Confluence space export.zip" zips/

# 1. Extract ZIP files to input directories
python main.py extract-zips

# 2. Process all input directories  
python main.py process-input

# 3. Review generated JSON files in output/
ls output/*.json

# 4. Extract content
python main.py extract-content

# 5. Upload to API (requires credentials)
export OUTLINE_API_URL="https://your-outline.com/api"  
export OUTLINE_API_TOKEN="your-token"
python main.py api-upload --spaces is gi

# 6. Update existing documents with latest content (force mode)
python main.py api-upload --spaces is gi --force

# 6. Check final status
python main.py status
```

## 📁 Directory Structure

```
ConfluenceToOutline/
├── zips/                  # Confluence export ZIP files
│   ├── Confluence-space-export-135853.html.zip
│   └── Confluence-space-export-204041.html.zip
├── input/                 # Extracted export directories
│   ├── Export-135853/
│   │   └── IS/           # Space directory with index.html
│   └── Export-204041/
│       └── GI/
├── output/                # Generated JSON files
│   ├── is.json           # Space structure + content
│   └── gi.json
├── libs/                  # Core libraries
│   ├── space_processor.py     # Main processing engine
│   ├── api_upload_manager.py  # API upload handling
│   ├── dom_hierarchy_parser.py # HTML structure parser
│   ├── zip_extractor.py       # Safe ZIP extraction
│   └── ...
├── archive/               # Historical data and experiments
└── main.py               # Primary CLI interface
```

## 🔧 API Configuration

### Environment Variables
```bash
export OUTLINE_API_URL="https://your-outline-instance.com/api"
export OUTLINE_API_TOKEN="your-api-token-here"
```

**Note:** The system also supports the legacy `OUTLINE_API_KEY` environment variable for backward compatibility.

### Command Line Options
```bash
python main.py api-upload \
  --spaces is gi \
  --api-url "https://your-outline.com/api" \
  --api-token "your-token"
```

## 📈 Features

### ✅ Secure ZIP Extraction
- **Safe extraction** with zip bomb protection and path traversal prevention
- **Size limits** to prevent excessive disk usage
- **Automatic directory naming** from ZIP filenames
- **Preserves ZIP files** for re-extraction if needed

### ✅ Robust Structure Parsing
- **Complete hierarchy extraction** from `index.html` using DOM parser
- Handles malformed HTML and complex nested structures
- Captures all 200+ pages with proper parent-child relationships
- Supports multiple spaces in single workflow

### ✅ Clean Content Processing  
- **Smart markdown conversion** from HTML
- **Breadcrumb removal** - no more navigation clutter
- **Title deduplication** - titles captured from structure, not content
- **Advanced attachment handling** - complete image and file support with Outline compatibility

### ✅ Advanced Attachment & Image Support
- **Automatic URL parameter removal** - strips `?width=760` and other Confluence query parameters
- **Templated format conversion** - uses clean `{attachment/path}` system for UUID replacement
- **Perfect Outline compatibility** - converts to proper `/api/attachments.redirect?id=UUID` format
- **Unlinked attachment detection** - automatically adds attachment sections for orphaned files
- **Comprehensive metadata tracking** - preserves content type, original names, and UUIDs
- **Two-phase upload workflow** - creates attachment records then uploads to secure storage
- **Proper markdown image syntax** - maintains alt text and sizing information

### ✅ Resumable API Operations
- **UUID tracking** for created collections and pages
- **Status persistence** in JSON files
- **Skip already created** items on retry
- **Progress reporting** with completion percentages

### ✅ Production Ready
- **Comprehensive error handling** with detailed logging
- **Advanced rate limiting** with exponential backoff and server header respect
- **Force mode operations** for updating existing content and collections
- **Interactive conflict resolution** for duplicate collection names
- **Clean separation of concerns** for maintainability
- **Flexible CLI** with intuitive commands
- **Centralized configuration** with validation and type safety
- **Environment variable support** with command-line overrides
- **Complete attachment workflows** tested with 7+ production spaces

## 🔄 Migration from Legacy

If you have an existing setup using the old workflow:

```bash

python main.py extract-zips
python main.py process-input
python main.py extract-content --spaces is gi
python main.py api-upload --spaces is gi
```


## 🛠️ Development

### Running Tests
```bash
python -m pytest test_data/
```

### Adding New Space Types
1. Ensure space has `index.html` with navigation structure
2. Place in `input/Export-*/SPACE_KEY/` directory
3. Run `process-input` to extract structure
4. Review generated JSON in `output/`
5. Process normally with `extract-content` and `api-upload`

### Extending Functionality
- **Custom parsers**: Extend `DomHierarchyParser` in `libs/`
- **Content processing**: Modify `SpaceProcessor.html_to_markdown()`
- **API integration**: Enhance `ApiUploadManager` for new endpoints

## 🐛 Troubleshooting

### Common Issues

**"No zip files found in zips/ directory"**
- Place your Confluence export ZIP files in the `zips/` directory
- Ensure files have `.zip` extension
- Use `python main.py extract-zips` to process them

**"No spaces found to process"**
- Ensure exports are in `input/Export-*/SPACE_KEY/` format
- Check that `index.html` exists in space directory

**"Space file not found"**  
- Run `process-input` first to create JSON files
- Check `output/` directory for generated files

**"Failed to create collection/page"**
- Verify API credentials and network connectivity
- Check Outline instance is accessible
- Review rate limiting (default 0.1s delay between requests)
- It's recommended to disable rate limiting or setting the request value very high for this process.

**"Upload interrupted"**
- Use `python main.py reset --spaces <key>` to reset status
- Or continue with same command - already created items will be skipped

**"Attachments not displaying correctly"**
- Re-run `extract-content` to update attachment URLs with latest format
- Use `--force` mode to update existing pages: `python main.py api-upload --spaces <key> --force`
- Check that attachment files exist in `input/Export-*/SPACE/attachments/` directories

**"Images showing as broken links"**
- Ensure images were successfully uploaded (check JSON for `"uploaded": true`)
- Verify Outline instance supports the attachment redirect endpoint
- Use force mode to refresh all attachment URLs

### Debug Mode
```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG
python main.py status
```

## 📝 License

GNU AFFERO GENERAL PUBLIC LICENSE

## 🤝 Contributing  

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)  
5. Open Pull Request

## 📞 Support

For issues and questions:
- Check the troubleshooting section above
- Review logs in the terminal output
- Use `python main.py status` to check current state
- Open an issue in the repository