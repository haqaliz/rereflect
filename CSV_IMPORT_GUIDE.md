# CSV Import Guide

## Overview

The Customer Feedback Analyzer supports bulk import of feedback data from CSV files. The import feature automatically detects the schema and imports feedback with automatic AI analysis.

## Sample CSV File

A sample CSV file (`sample_feedback.csv`) is included in the project root with 15 example feedback items.

## Supported CSV Schemas

The import feature is flexible and works with various CSV schemas. It automatically detects column names (case-insensitive).

### Required Column

At least one column containing feedback text. The system looks for these column names:
- `feedback_text` (recommended)
- `text`
- `feedback`
- `comment`
- `message`
- `description`
- `review`

### Optional Columns

- `source`, `channel`, or `origin` - Source of the feedback (e.g., "email", "survey", "support_ticket")
- Any other columns are ignored but won't cause errors

## Example CSV Formats

### Format 1: Simple
```csv
feedback_text,source
"Great product! Love it.",survey
"Bug: app crashes on startup",email
"Feature request: dark mode please",support_ticket
```

### Format 2: With Additional Data
```csv
text,source,customer_email,date
"Amazing experience!",review,john@example.com,2024-01-15
"Cannot login to my account",email,support@user.com,2024-01-16
```

### Format 3: Custom Schema
```csv
comment,channel,rating,customer_id
"The onboarding is confusing",feedback_form,2,12345
"Excellent customer support!",survey,5,67890
```

## How to Import

1. **Prepare your CSV file**
   - Ensure it has a header row
   - Include at least one column with feedback text
   - Use UTF-8 encoding

2. **Import via Web Interface**
   - Go to the Feedback Management page
   - Click the "Import CSV" button
   - Select your CSV file
   - Wait for the import to complete

3. **Review Results**
   - Total rows processed
   - Successfully imported count
   - Failed count with error details
   - All imported feedback is automatically analyzed

## Automatic Analysis

Every imported feedback item is automatically analyzed for:
- **Sentiment** (positive, neutral, negative)
- **Urgency** (based on keywords and sentiment)
- **Sentiment Score** (-1 to +1)

## Error Handling

The import process continues even if some rows fail. Common errors:
- Empty feedback text
- Invalid CSV format
- Encoding issues

Failed rows are reported in the results modal with specific error messages.

## Best Practices

1. **Test with small files first** - Try importing 10-20 rows before bulk imports
2. **Use standard column names** - `feedback_text` and `source` are recommended
3. **Clean your data** - Remove empty rows and ensure text is properly quoted
4. **UTF-8 encoding** - Save your CSV as UTF-8 to avoid character issues
5. **Reasonable batch sizes** - Import up to 1,000 rows at a time for best performance

## API Endpoint

For programmatic access:

```bash
POST /api/v1/feedback/import-csv
Content-Type: multipart/form-data

file: <CSV file>
Authorization: Bearer <token>
```

Response:
```json
{
  "total_rows": 15,
  "imported_count": 14,
  "failed_count": 1,
  "errors": ["Row 5: Empty feedback text"]
}
```

## Example: Using the Sample CSV

```bash
# From the project root
# The sample_feedback.csv file is ready to import
# It contains 15 diverse feedback items from various sources

# Upload via web interface or use curl:
curl -X POST http://localhost:8000/api/v1/feedback/import-csv \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@sample_feedback.csv"
```

## Troubleshooting

### "Could not detect feedback text column"
- Ensure your CSV has a header row
- Use one of the standard column names listed above
- Check that the column name spelling is correct

### "CSV file is empty or invalid"
- Verify the file is a valid CSV
- Check for proper UTF-8 encoding
- Ensure there's at least one data row (besides header)

### Import succeeds but feedback not analyzed
- Check backend logs for analysis errors
- Verify the analysis engine is running
- Sentiment analysis happens automatically but may fail silently

## Performance

- Small files (<100 rows): < 5 seconds
- Medium files (100-500 rows): 10-30 seconds
- Large files (500-1000 rows): 30-60 seconds

Each row is analyzed individually, so import time scales with row count.
