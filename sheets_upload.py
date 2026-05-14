"""Upload TOMS settings reports to Google Sheets.

Uses a service account to write report data to a shared spreadsheet.
"""

import gspread
import openpyxl


# ── Configuration ──────────────────────────────────────────────────────────────
CREDENTIALS_FILE = "/Users/jasonhicks/Projects/test-settings-sync/credentials.json"
SPREADSHEET_ID = "1Nn70EPs5XB5dojO-UXOKaz2uwuaW4JbC_WybUPDNtvA"


def upload_report_to_sheets(report_path, sheet_name="Raw"):
    """Upload a TOMS settings report to a Google Sheet tab.

    Clears the existing tab and replaces it with the report data.

    Args:
        report_path: Path to the downloaded TOMS report (xlsx)
        sheet_name: Name of the tab to write to (default: "Raw")

    Returns:
        True if successful, False otherwise
    """
    print(f"\n── Uploading to Google Sheets: {sheet_name} ─────────────────")

    # Read the report xlsx
    print(f"  Reading report: {report_path}")
    wb = openpyxl.load_workbook(report_path, read_only=True)
    ws = wb.active

    # Convert all rows to a list of lists (strings)
    data = []
    for row in ws.iter_rows(values_only=True):
        data.append([str(val) if val is not None else '' for val in row])
    wb.close()
    print(f"  {len(data)} rows read from report.")

    # Connect to Google Sheets
    try:
        print("  Connecting to Google Sheets...")
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)

        # Find or create the tab
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            print(f"  Found existing '{sheet_name}' tab — clearing...")
            worksheet.clear()
        except gspread.exceptions.WorksheetNotFound:
            print(f"  Creating '{sheet_name}' tab...")
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=len(data), cols=len(data[0]) if data else 1)

        # Resize to fit the data
        worksheet.resize(rows=len(data), cols=len(data[0]) if data else 1)

        # Write all data at once
        print(f"  Writing {len(data)} rows...")
        worksheet.update(data, value_input_option='RAW')

        print(f"  ✓ Uploaded to '{sheet_name}' tab successfully.")
        return True

    except Exception as e:
        print(f"  ✗ Google Sheets upload failed: {e}")
        return False