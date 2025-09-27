# Information Systems Documentation Processor

A Python-based tool for processing and cleaning Confluence HTML exports and extracting navigation structures from documentation pages.

## Overview

This tool provides a complete pipeline for:
1. **Cleaning HTML exports** from Confluence with proper markdown conversion
2. **Extracting navigation structures** from documentation hierarchies
3. **API integration** for document management systems

## Features

- **HTML Cleaning**: Converts Confluence HTML exports to clean markdown
- **Navigation Extraction**: Builds hierarchical structures from breadcrumb navigation
- **Confluence Footer Removal**: Automatically removes generated timestamps and references
- **Multi-format Support**: Handles both HTML and markdown input files
- **Batch Processing**: Processes entire directories efficiently
- **API Integration**: Test and interact with document management APIs

## Installation

### Prerequisites

- Python 3.8 or higher
- Virtual environment (recommended)

### Setup

1. **Clone or download the project files**
2. **Navigate to the project directory:**
   ```bash
   cd /path/to/IS/app
   ```

3. **Create and activate virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On macOS/Linux
   # or
   venv\Scripts\activate     # On Windows
   ```

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

The tool provides three main commands through a command-line interface:

### 1. Clean HTML Files (`clean-html`)

Converts Confluence HTML exports to clean markdown format.

**Basic usage:**
```bash
python main.py clean-html --input-dir ../html --output-dir ../cleaned
```

**Full options:**
```bash
python main.py clean-html \
    --input-dir ../html \
    --output-dir ../cleaned_pages \
    --pattern "*.html" \
    --no-breadcrumbs \
    --no-titles
```

**Options:**
- `--input-dir` (required): Directory containing HTML files to clean
- `--output-dir` (optional): Output directory for cleaned files (default: input_dir/cleaned)
- `--pattern` (optional): File pattern to match (default: *.md)
- `--no-breadcrumbs`: Skip preserving breadcrumb navigation
- `--no-titles`: Skip preserving title structure

**Example output:**
```
Cleaning HTML files from: ../html
Processing: 3CX-System-Details_2481520646.html
Processing: Servers-and-Virtual-Machines_681672705.html
Processing complete!
  Total files: 219
  Processed successfully: 219
  Errors: 0
  Output directory: ../cleaned_pages
```

### 2. Extract Navigation Structure (`process-pages`)

Extracts hierarchical navigation data from cleaned markdown files.

**Basic usage:**
```bash
python main.py process-pages --pages-dir ../cleaned_pages --output ../structure.json
```

**Full options:**
```bash
python main.py process-pages \
    --pages-dir ../cleaned_pages \
    --output ../navigation_structure.json \
    --pattern "*.html"
```

**Options:**
- `--pages-dir` (optional): Directory containing pages to process (default: ../pages)
- `--output` (optional): Output JSON file (default: ../processed_pages.json)
- `--pattern` (optional): File pattern to match (default: *.md)

**Output format:**
```json
{
  "pages": [
    {
      "filename": "clean_3CX-System-Details_2481520646.html",
      "title": "3CX System Details",
      "path": [
        "Servers and Virtual Machines",
        "Proxmox Virtual Machines",
        "3cx - VOIP Server"
      ]
    }
  ],
  "total_files": 219
}
```

### 3. API Testing (`api-test`)

Test connections to document management APIs.

**Usage:**
```bash
# List collections
python main.py api-test --collections

# List documents
python main.py api-test --documents

# Both with custom collection ID
python main.py api-test --collections --documents --collection-id YOUR_COLLECTION_ID
```

## Complete Workflow Example

Here's a complete example of processing Confluence HTML exports:

```bash
# 1. Activate virtual environment
source venv/bin/activate

# 2. Clean HTML exports
python main.py clean-html \
    --input-dir ../html \
    --output-dir ../cleaned_pages \
    --pattern "*.html"

# 3. Extract navigation structure
python main.py process-pages \
    --pages-dir ../cleaned_pages \
    --output ../final_structure.json \
    --pattern "*.html"

# 4. Test API if needed
python main.py api-test --collections
```

## Project Structure

```
IS/
├── app/
│   ├── main.py              # Main CLI application
│   ├── requirements.txt     # Python dependencies
│   ├── venv/               # Virtual environment
│   └── libs/
│       ├── pages.py        # Page processing logic
│       └── html_cleaner.py # HTML cleaning logic
├── html/                   # Original HTML exports
├── cleaned_pages/          # Cleaned markdown files
└── structure.json          # Extracted navigation data
```

## Dependencies

- `requests` - HTTP client for API interactions
- `beautifulsoup4` - HTML parsing and manipulation
- `lxml` - XML/HTML parser backend
- `html2text` - HTML to markdown conversion
- `markdown` - Markdown processing
- `mistune` - Alternative markdown parser
- `python-dotenv` - Environment variable management

## Configuration

Create a `.env` file in the `app` directory for API configuration:

```env
OUTLINE_API_KEY=your_api_key_here
OUTLINE_API_URL=https://your-instance.com
```

## What Gets Cleaned

The HTML cleaner removes:

- ✅ Confluence-generated footers ("Document generated by Confluence...")
- ✅ Atlassian branding links
- ✅ Page metadata (creation/modification info)  
- ✅ Confluence-specific HTML classes and styling
- ✅ Empty HTML elements
- ✅ Excessive whitespace and blank lines

The cleaner preserves:

- ✅ Content hierarchy and structure
- ✅ Navigation breadcrumbs (items 3+ in numbered lists)
- ✅ Page titles (extracted from headers)
- ✅ Links and formatting
- ✅ Images and attachments references

## Troubleshooting

### Virtual Environment Issues

If you get `ModuleNotFoundError`, ensure the virtual environment is activated:

```bash
# Check if venv is active (should show (venv) in prompt)
which python

# If not active, activate it
source venv/bin/activate

# Verify packages are installed
pip list
```

### File Path Issues

Use absolute paths or ensure you're running commands from the correct directory:

```bash
# Run from the app directory
cd /path/to/IS/app

# Use the full command with venv activation
source venv/bin/activate && python main.py clean-html --input-dir ../html
```

### Common Error Solutions

**"No such file or directory: main.py"**
- Ensure you're in the `app` directory
- Check that `main.py` exists in the current directory

**"Module not found: html2text"**
- Activate virtual environment: `source venv/bin/activate`
- Install requirements: `pip install -r requirements.txt`

**"No files found to process"**
- Check the `--input-dir` path is correct
- Verify the `--pattern` matches your files
- Use `ls` to confirm files exist in the input directory

## Performance

- **Processing Speed**: ~200 files processed in under 2 minutes
- **Size Reduction**: Average 5-7KB reduction per file
- **Memory Usage**: Efficient processing of large document sets
- **Error Handling**: Continues processing even if individual files fail

## Output Quality

The cleaned files maintain:
- **Readable markdown format**
- **Preserved navigation structure**  
- **Clean formatting without HTML artifacts**
- **Proper heading hierarchy**
- **Working links and references**

## License

This project is for internal use processing Confluence documentation exports.

## Support

For issues or questions, check:
1. This README for common solutions
2. The `processing_summary.json` file for detailed results
3. Terminal output for specific error messages

---

*Last updated: September 26, 2025*