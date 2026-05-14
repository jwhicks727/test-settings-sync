"""Verify uploaded test settings by spot-checking students in TOMS.

Picks random students from the uploaded data, navigates to their
Test Settings page in TOMS, and compares the live settings against
what was in the uploaded file.
"""

import csv
import random
import glob
import time
import os
import openpyxl
from browser_helpers import find_element, js_click
from toms_helpers import reenter_frame

# Known code differences between Aeries and TOMS
# Aeries code -> TOMS code (or None if TOMS doesn't track it)
CODE_EQUIVALENTS = {
    'NEDS_RA_Items_Stimuli_ESN': 'NEDS_RA_Stimuli_ESN',
    'NEDS_RA_SPA': None,  # Aeries tracks this but TOMS does not
}

def download_settings_report(driver, report_value, downloads_dir, file_pattern, form_id='studentTestSettingsForm'):
    """Download a test settings report from TOMS Reports tab.

    Args:
        driver: Selenium WebDriver instance
        report_value: The option value, e.g. "CAASPP_School_Level_Student_Test_Settings_Report"
        downloads_dir: Path to downloads directory
        file_pattern: Glob pattern to find the downloaded file, e.g. "*CAASPP_StudentTestSettings*"

    Returns:
        Path to the downloaded report, or None if download failed
    """
    # Switch to main content
    driver.switch_to.default_content()

    # Click Reports
    print("  Clicking Reports...")
    driver.execute_script("""
        var btn = document.getElementById('menu_Reports');
        if (btn) btn.click();
    """)
    time.sleep(1)

    reenter_frame(driver)

    # Select the report
    print(f"  Selecting report: {report_value}...")
    driver.execute_script(f"""
        var select = document.getElementById('reportType');
        if (select) {{
            select.value = '{report_value}';
            select.dispatchEvent(new Event('change', {{ bubbles: true }}));
            reportSelected();
        }}
    """)
    time.sleep(2)

    # Populate school hidden field and submit form directly (bypasses validation)
    print("  Submitting report form...")
    driver.execute_script("""
        // Try to set school ID on any matching hidden field
        var schFields = document.querySelectorAll('input[type="hidden"][id$="sch_id"]');
        for (var i = 0; i < schFields.length; i++) {
            if (!schFields[i].value) schFields[i].value = '158073';
        }
        
        // Submit whichever form exists
        var form = document.getElementById('studentTestSettingsForm') 
                || document.getElementById('elpacstudentTestSettingsForm');
        if (form) form.submit();
    """)
    time.sleep(2)

    # Wait for file to download
    print("  Waiting for report to download...")
    report_file = None
    for attempt in range(30):
        matches = glob.glob(os.path.join(downloads_dir, file_pattern))
        # Filter out any .crdownload files
        matches = [f for f in matches if not f.endswith('.crdownload')]
        if matches:
            # Get the most recent one
            report_file = max(matches, key=os.path.getmtime)
            break
        time.sleep(0.5)

    if report_file:
        print(f"  Report saved: {report_file}")
    else:
        print("  Report download failed.")

    return report_file


def verify_via_report(csv_path, report_path, report_settings_start_col=16, report_header_row=2, report_data_start_row=3):
    """Compare uploaded Aeries data against the TOMS settings report.

    Args:
        csv_path: Path to the Aeries CSV that was uploaded
        report_path: Path to the downloaded TOMS settings report (xlsx)
        report_settings_start_col: Column index where settings begin in the report (0-based)
        report_header_row: Row number of the header (1-based)
        report_data_start_row: Row number where data begins (1-based)

    Returns:
        Dict with results
    """
    print("\n── Report Verification ──────────────────────────────────────")

    # Read the Aeries CSV — SSID is col 0, settings are col 1+
    expected = {}
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row in reader:
            ssid = row[0].strip()
            if not ssid:
                continue
            settings = set()
            for val in row[1:]:
                val = val.strip()
                if val:
                    settings.add(val)
            expected[ssid] = settings

    print(f"  Aeries: {len(expected)} students with data")

    # Read the TOMS report — skip demographic columns
    wb = openpyxl.load_workbook(report_path, read_only=True)
    ws = wb.active

    actual = {}
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        row_num = i + 1
        # Skip title and header rows
        if row_num < report_data_start_row:
            continue

        ssid = str(row[0]).strip() if row[0] else ''
        if not ssid:
            continue

        # Only collect values from settings columns (skip demographics)
        settings = set()
        for val in row[report_settings_start_col:]:
            if val:
                val = str(val).strip()
                if val:
                    settings.add(val)
        actual[ssid] = settings

    wb.close()
    print(f"  TOMS report: {len(actual)} students with data")

    # Compare
    results = {'total': len(expected), 'matched': 0, 'mismatched': 0, 'missing': 0, 'details': []}

    for ssid, exp_settings in expected.items():
        if ssid not in actual:
            results['missing'] += 1
            results['details'].append({
                'ssid': ssid, 'status': 'missing',
                'reason': 'Student not found in TOMS report'
            })
            continue

        act_settings = actual[ssid]

        # Translate Aeries codes to TOMS equivalents before comparing
        translated_exp = set()
        for code in exp_settings:
            if code in CODE_EQUIVALENTS:
                equiv = CODE_EQUIVALENTS[code]
                if equiv is not None:
                    translated_exp.add(equiv)
            else:
                translated_exp.add(code)

        missing = translated_exp - act_settings
        extra = act_settings - translated_exp

        if not missing and not extra:
            results['matched'] += 1
        else:
            results['mismatched'] += 1
            results['details'].append({
                'ssid': ssid, 'status': 'mismatch',
                'missing': missing, 'extra': extra
            })

    print(f"\n  Results:")
    print(f"    Matched:    {results['matched']}/{results['total']}")
    print(f"    Mismatched: {results['mismatched']}/{results['total']}")
    print(f"    Missing:    {results['missing']}/{results['total']}")

    if results['mismatched'] > 0:
        print(f"\n  First 5 mismatches:")
        for detail in results['details'][:5]:
            if detail['status'] == 'mismatch':
                print(f"    SSID {detail['ssid']}:")
                if detail['missing']:
                    print(f"      Missing from TOMS: {detail['missing']}")
                if detail['extra']:
                    print(f"      Extra in TOMS: {detail['extra']}")

    if results['missing'] > 0:
        print(f"\n  Missing students (in Aeries but not in TOMS report):")
        for detail in results['details']:
            if detail['status'] == 'missing':
                print(f"    SSID {detail['ssid']}")

    return results

def get_student_settings_from_csv(csv_path, ssid):
    """Get all non-empty setting values for a student from the Aeries CSV.

    Args:
        csv_path: Path to the Aeries export CSV
        ssid: Student SSID to look up

    Returns:
        Set of setting code strings, or None if student not found
    """
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row in reader:
            if row[0].strip() == str(ssid):
                # Collect all non-empty values except the SSID (column 0)
                settings = set()
                for val in row[1:]:
                    val = val.strip()
                    if val:
                        settings.add(val)
                return settings
    return None


def get_student_settings_from_toms(driver):
    """Scrape all active test settings from the current TOMS student page.

    Reads checked checkboxes and selected dropdown values.

    Returns:
        Set of setting code strings
    """
    settings = driver.execute_script("""
        var codes = [];

        // Checked checkboxes
        var checkboxes = document.querySelectorAll('input[type="checkbox"]:checked');
        for (var i = 0; i < checkboxes.length; i++) {
            if (checkboxes[i].value && checkboxes[i].value !== 'on') {
                codes.push(checkboxes[i].value);
            }
        }

        // Selected dropdown values (non-empty)
        var selects = document.querySelectorAll('select');
        for (var i = 0; i < selects.length; i++) {
            var val = selects[i].value;
            if (val && val !== '' && val !== 'Select') {
                codes.push(val);
            }
        }

        return codes;
    """)
    return set(settings)


def navigate_to_student(driver, ssid):
    """Navigate to a student's Test Settings page in TOMS.

    Args:
        driver: Selenium WebDriver instance
        ssid: Student SSID to search for

    Returns:
        True if student was found, False otherwise
    """
    import time

    # Click View & Edit
    driver.switch_to.default_content()
    clicked = driver.execute_script("""
        var btn = document.querySelector('button[aria-label="View & Edit"]');
        if (!btn) return 'not found';
        btn.click();
        return 'clicked';
    """)
    print(f"    View & Edit: {clicked}")
    time.sleep(1)

    reenter_frame(driver)

    # Enter SSID
    ssid_field = find_element(driver, '#wiserID')
    if not ssid_field:
        print("    SSID search field not found.")
        return False

    ssid_field.clear()
    ssid_field.send_keys(str(ssid))
    time.sleep(0.5)

    # Click Search
    driver.execute_script("""
        var btn = document.getElementById('searchStudents');
        if (btn) btn.click();
    """)
    time.sleep(2)

    reenter_frame(driver)

    # Click the magnifying glass to open student profile
    driver.execute_script("""
        var icon = document.querySelector('.fa-magnifying-glass.icnActions');
        if (icon) icon.click();
    """)
    print("    Student profile opened.")
    time.sleep(2)

    reenter_frame(driver)

    # Click Test Settings
    clicked = driver.execute_script("""
        var link = document.getElementById('accom1');
        if (!link) return 'not found';
        link.click();
        return 'clicked';
    """)
    print(f"    Test Settings: {clicked}")
    time.sleep(2)

    reenter_frame(driver)

    return clicked == 'clicked'


def verify_upload(driver, csv_path, sample_size=3):
    """Verify uploaded settings by spot-checking random students.

    Args:
        driver: Selenium WebDriver instance
        csv_path: Path to the Aeries export CSV that was uploaded
        sample_size: Number of students to check

    Returns:
        Dict with results: {'passed': int, 'failed': int, 'details': list}
    """
    import time

    # Read all SSIDs from the CSV
    ssids = []
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row in reader:
            if row[0].strip():
                ssids.append(row[0].strip())

    # Pick random students
    sample = random.sample(ssids, min(sample_size, len(ssids)))

    print(f"\n── Verification: checking {len(sample)} random students ──────────")
    results = {'passed': 0, 'failed': 0, 'details': []}

    # Navigate to Students menu first
    driver.switch_to.default_content()
    driver.execute_script("""
        var btn = document.getElementById('menu_Students');
        if (btn) btn.click();
    """)
    time.sleep(1)

    for i, ssid in enumerate(sample):
        print(f"\n  Student {i + 1}/{len(sample)}: SSID {ssid}")

        # Get expected settings from CSV
        expected = get_student_settings_from_csv(csv_path, ssid)
        if expected is None:
            print(f"    SSID {ssid} not found in CSV — skipping.")
            continue

        # Navigate to student's Test Settings page
        if not navigate_to_student(driver, ssid):
            print(f"    Could not navigate to student — skipping.")
            results['details'].append({
                'ssid': ssid, 'status': 'error', 'reason': 'Navigation failed'
            })
            continue

        # Scrape live settings
        live = get_student_settings_from_toms(driver)

        # Compare
        missing = expected - live    # In CSV but not in TOMS
        extra = live - expected      # In TOMS but not in CSV

        if not missing and not extra:
            print(f"    ✓ All {len(expected)} settings match.")
            results['passed'] += 1
            results['details'].append({
                'ssid': ssid, 'status': 'pass',
                'expected': len(expected), 'matched': len(expected)
            })
        else:
            print(f"    ✗ Mismatch detected:")
            if missing:
                print(f"      Missing from TOMS: {missing}")
            if extra:
                print(f"      Extra in TOMS: {extra}")
            results['failed'] += 1
            results['details'].append({
                'ssid': ssid, 'status': 'fail',
                'missing': missing, 'extra': extra
            })

    print(f"\n── Verification complete: {results['passed']} passed, {results['failed']} failed ──")
    return results