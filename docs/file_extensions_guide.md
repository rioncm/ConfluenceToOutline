# File Extensions Configuration Examples

## Overview
The Information Systems Documentation Processor supports flexible file extension configuration via environment variables. This allows you to customize which file types are processed and extracted.

## Default Supported Extensions
```
.html, .md, .txt, .png, .jpg, .jpeg, .gif, .pdf, .docx, .doc, .xlsx, .xls, .pptx, .ppt
```

## Environment Variables

### `INCLUDE_EXTENSIONS` - Add to Default List
Adds additional file types to the default list without removing any existing ones.

```bash
# Add SVG and WebP image formats
export INCLUDE_EXTENSIONS=.svg,.webp

# Add video formats (with or without leading dots)
export INCLUDE_EXTENSIONS=mp4,avi,.mkv

# Add custom file types
export INCLUDE_EXTENSIONS=.custom,.proprietary,.special
```

### `OVERRIDE_EXTENSIONS` - Replace Default List
**⚠️ Use with caution** - This completely replaces the default extension list.

```bash
# Only process HTML and Markdown files
export OVERRIDE_EXTENSIONS=.html,.md

# Custom minimal set
export OVERRIDE_EXTENSIONS=html,txt,png,jpg

# Include only specific document types
export OVERRIDE_EXTENSIONS=.pdf,.docx,.pptx,.html
```

## Usage Examples

### Scenario 1: Adding Support for Modern Web Formats
```bash
# Add modern image and video formats to defaults
export INCLUDE_EXTENSIONS=.svg,.webp,.mp4,.webm
python main.py extract-zips
```

### Scenario 2: Processing Only Essential Files
```bash
# Only process core documentation files
export OVERRIDE_EXTENSIONS=.html,.md,.txt,.pdf
python main.py extract-zips
```

### Scenario 3: Custom Corporate File Types
```bash
# Add company-specific extensions
export INCLUDE_EXTENSIONS=.corp,.internal,.template
python main.py extract-zips
```

## Validation and Testing

### Check Current Configuration
```python
from libs.config import SecurityConfig
config = SecurityConfig()
print("Allowed extensions:", config.allowed_extensions)
print("Is .svg allowed?", config.is_allowed_file("image.svg"))
```

### Test with Different Settings
```bash
# Test with additional extensions
INCLUDE_EXTENSIONS=.svg,.webp python -c "
from libs.config import SecurityConfig
config = SecurityConfig()
print('Extensions:', len(config.allowed_extensions))
print('Includes .svg:', '.svg' in config.allowed_extensions)
"

# Test with override
OVERRIDE_EXTENSIONS=.html,.md python -c "
from libs.config import SecurityConfig  
config = SecurityConfig()
print('Extensions:', config.allowed_extensions)
print('Only 2 extensions:', len(config.allowed_extensions) == 2)
"
```

## Error Handling

### Common Issues
1. **Empty Extensions**: Empty or whitespace-only extensions are ignored
2. **Invalid Format**: Extensions are automatically corrected (e.g., `svg` → `.svg`)
3. **Duplicates**: Duplicate extensions in `INCLUDE_EXTENSIONS` are automatically filtered

### Best Practices
- **Use `INCLUDE_EXTENSIONS`** for most cases to maintain security defaults
- **Use `OVERRIDE_EXTENSIONS`** only when you need precise control
- **Always include `.html`** in overrides since it's needed for processing
- **Test configuration** before processing large datasets

## Security Considerations

### Default Extensions Are Secure
The default extension list is designed to include common, safe file types while excluding potentially dangerous formats.

### When Overriding
- Be cautious with executable file types (.exe, .bat, .sh)
- Consider the source of your ZIP files
- Monitor logs for blocked files to understand what you might be missing

## Integration with Main Workflow

```bash
# Set extensions in .env file
echo "INCLUDE_EXTENSIONS=.svg,.webp,.mp4" >> .env

# Or set temporarily
export INCLUDE_EXTENSIONS=.svg,.webp
python main.py extract-zips
python main.py process-all
python main.py api-upload --html-dir ./output/cleaned/html
```

## Troubleshooting

### Files Not Being Processed?
1. Check if the extension is in the allowed list
2. Look for "blocked" messages in the logs
3. Add the extension using `INCLUDE_EXTENSIONS`

### Too Many Files?
1. Use `OVERRIDE_EXTENSIONS` to limit to specific types
2. Consider processing in smaller batches
3. Review the default list to see what's included