# TODO: Features, functionality, and Fixes


## Features


## Functionality



## Fixes

## Priority 1

- linting reporting errors in space_processor.py
- **PARTIALLY FIXED**: attachments are not properly linked in the uploaded/created documents. 
    - ✅ **Implementation complete**: New workflow creates pages with minimal content → uploads attachments → updates content with attachment links
    - 🔄 **Testing needed**: Full workflow needs fresh test on new Outline instance to verify complete attachment linking 
    - **Root cause**: Content extraction inconsistently converts attachments to markdown links
    - **Handle images properly**
        ![](/api/attachments.redirect?id=64fb54c5-d651-4717-815b-7f34b48a4e2e \" =180x180\")

        The full format is !["AltText"](API_ENDPOINT?IMAGE_UUID \" =wXh\") 

        The minimal format is ![](API_ENDPOINT?IMAGE_UUID)

## Priority 2
- Collections are being duplicated on multiple api uploads
    - need logic to check if a collection or page already exists before pushing and change to update vs create.

# solved issues
- ✅ **CRITICAL**: No spaces have been processed yet - output directory is empty
- ✅ **403 attachment error is actually validation error** - need valid document IDs 
- ✅ **Complete workflow needs to run**: extract -> process -> extract-content -> upload
- ✅ **Attachment upload response parsing bug** - attachment ID was nested incorrectly 
- ✅ **Attachment upload system is working perfectly** - all 3 test attachments uploaded successfully (3/3 = 100%)
- ✅ logging is working correctly - DEBUG level active
- ✅ API authentication is working (can list collections successfully)
- ✅ Attachment upload logic is implemented correctly - two-phase upload process working
