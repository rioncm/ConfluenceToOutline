# Information Systems Documentation Processor - Quick Reference

## 🚀 Complete 3-Phase Workflow

### Prerequisites
```bash
# Setup environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure API (create .env file)
OUTLINE_API_KEY=your_api_key_here
OUTLINE_API_URL=https://app.getoutline.com
```

### Phase 1: Extract ZIP Files
```bash
python main.py extract-zips
# Output: Extracted files in input/ directory
```

### Phase 2: Clean & Process Content  
```bash
python main.py process-all
# Output: Clean HTML and Markdown in output/ directory
```

### Phase 3: Upload to Outline ✅ NEW
```bash
python main.py api-upload --html-dir ./output/cleaned/html --collection-name "My Docs"
# Output: Documents live in your Outline knowledge base
```

## 🎯 One-Line Commands

### Basic Workflow
```bash
# Process everything with defaults
python main.py extract-zips && python main.py process-all && python main.py api-upload --html-dir ./output/cleaned/html
```

### Custom Workflow
```bash  
# Custom directories and settings
python main.py extract-zips --zips-dir ./my-zips --input-dir ./my-input && \
python main.py process-all --input-dir ./my-input --output-dir ./my-output && \
python main.py api-upload --html-dir ./my-output/cleaned/html --collection-name "Custom Collection"
```

## 📊 Expected Results

**Phase 1**: ZIP files → Structured HTML files  
**Phase 2**: HTML files → Clean Markdown + Navigation  
**Phase 3**: Markdown files → Live Outline documents  

## 🔍 Quick Troubleshooting

```bash
# Test API connection
python main.py api-test --collections

# Debug mode
python main.py --log-level DEBUG api-upload --html-dir ./test

# Minimal test
python main.py api-upload --html-dir ./test_data --collection-name "Test"
```

## ✅ Success Indicators

```
Phase 1: ✅ Extracted N files safely
Phase 2: ✅ Processed N HTML files  
Phase 3: ✅ Success rate: 100.0% - All files uploaded!
```