# TODO: Features, functionality, and Fixes


## Features


## Functionality



## Fixes

## Priority 1



## Priority 2




# Completed
- ✅ **Image and attachment handling fully implemented** - **COMPLETED**: Complete URL parameter stripping and templated format conversion system
    - ✅ Automatic URL parameter removal from attachment references (`?width=760`, etc.)
    - ✅ Templated format system `{attachments/path}` for clean UUID replacement
    - ✅ Proper Outline API URL format: `https://docs.pminc.me/api/attachments.redirect?id=UUID`
    - ✅ Enhanced attachments section with detailed metadata (content type, original name, UUID)
    - ✅ Unlinked attachment detection and automatic display
    - ✅ Complete support for images and document attachments
    - ✅ Production tested with 7+ spaces successfully uploaded
    - **Technical Details**: 
        - HTML-level URL cleaning before markdown conversion
        - Templated format conversion during extraction
        - UUID-based replacement after attachment upload
        - Enhanced attachment metadata tracking and display
- ✅ **Collections are being duplicated on multiple api uploads** - **FIXED**: Complete collection deduplication logic implemented  
- ✅ linting reporting errors in space_processor.py - **FIXED**: All 11 BeautifulSoup type annotation errors resolved with proper type guards
- ✅ **CRITICAL**: No spaces have been processed yet - output directory is empty
- ✅ **403 attachment error is actually validation error** - need valid document IDs 
- ✅ **Complete workflow needs to run**: extract -> process -> extract-content -> upload
- ✅ **Attachment upload response parsing bug** - attachment ID was nested incorrectly 
- ✅ **Attachment upload system is working perfectly** - all 3 test attachments uploaded successfully (3/3 = 100%)
- ✅ logging is working correctly - DEBUG level active
- ✅ API authentication is working (can list collections successfully)
- ✅ Attachment upload logic is implemented correctly - two-phase upload process working
- ✅ **Add "force" flag to api-upload** - **COMPLETED**: Full force mode implementation with comprehensive features
    - ✅ Added `--force` command line flag to api-upload command
    - ✅ Collection ambiguity resolution with interactive user selection
    - ✅ Force mode ignores "created" flags and processes all documents
    - ✅ Existing documents get updated with latest content when force mode enabled
    - ✅ UUID-based document matching with API validation
    - ✅ Rate limiting retry logic (429 errors) with exponential backoff
    - ✅ Immediate UUID persistence to space.json after document creation
    - **Usage**: `python main.py api-upload --spaces <space_key> --force`
    - **Behavior**: Processes space.json regardless of "created" flags, updates existing documents, handles collection name conflicts with user input

- ✅ **COMPLETED**: Image and attachment handling fully implemented and tested
    - **Final Implementation**: Complete URL parameter stripping and templated format conversion system
    - **Workflow**: Strip URL parameters → Convert to templated format → Upload attachments → Replace templates with UUID URLs
    - **Results**: All images now render perfectly in Outline with proper format
        - **Before**: `![](attachments/2626912259/2830270465.png?width=760)`
        - **After**: `![](https://docs.pminc.me/api/attachments.redirect?id=UUID)`
    - **Enhanced Features**:
        - ✅ Automatic URL parameter removal (`?width=760`, etc.)
        - ✅ Templated format system for clean UUID replacement
        - ✅ Proper Outline API URL format support
        - ✅ Enhanced attachments section with metadata
        - ✅ Unlinked attachment detection and display
        - ✅ Complete image and document attachment support
    - **Testing**: Successfully tested with IS space and production uploads
    - **Production Status**: 7+ spaces uploaded successfully with perfect image rendering 
    - ✅ **Collections are being duplicated on multiple api uploads** - **FIXED**: Complete collection deduplication logic implemented
    - ✅ Added collections.list API method to fetch existing collections
    - ✅ Implemented exact name matching for collection lookup  
    - ✅ Enhanced workflow: check stored collection_id → check by name → create new if needed
    - ✅ Added UUID-based document matching to prevent document duplication
    - ✅ Implemented collection_id persistence in space JSON for future runs
    - ✅ Added comprehensive error tracking for collection and document failures
    - **Workflow**: Uses existing collection if found by exact space name match, validates stored collection IDs, matches documents by UUID, creates new documents only when UUID is blank/missing
