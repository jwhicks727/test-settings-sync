"""Orchestrator — runs all export and upload workflows in a single session.

Flow:
0. Download SEIS report, transform, import new settings into Aeries
1. Clean downloads folder
2. Open Aeries, download CAASPP and ELPAC exports
3. Open TOMS as CAASPP Coordinator, download template, merge, upload, verify
4. Switch to ELPAC Coordinator, download template, merge, upload, verify
5. Archive all files
"""

import time
import os
import glob
import csv
import shutil
import argparse
from datetime import datetime, timedelta
from browser_helpers import start_driver
from aeries_helpers import aeries_login, aeries_navigate_to_export, aeries_download_export
from toms_helpers import toms_login, toms_navigate_to_upload, toms_download_template, toms_upload_and_submit
from merge_data import merge
from seis_export import seis_download_report
from seis_transform import transform_seis_to_aeries
from aeries_import import run_aeries_import, navigate_to_import

# ── Configuration ──────────────────────────────────────────────────────────────
AERIES_URL = "https://soaracademy.aeries.net/admin/Login.aspx"
TOMS_URL = "https://mytoms.ets.org/TOMS"
PROFILE_DIR = "/Users/jasonhicks/Projects/test-settings-sync/edge-profile"

CAASPP_RADIO_ID = "ctl00_MainContent_rdoWhichSettings_0"
ELPAC_RADIO_ID = "ctl00_MainContent_rdoWhichSettings_3"

CAASPP_EXPORT_PREFIX = "CAASPPTestSettings"
ELPAC_EXPORT_PREFIX = "ELPACTestSettings"

CAASPP_TEMPLATE = "CAASPP_Upload_Stu_Accom_Template.xlsx"
ELPAC_TEMPLATE = "ELPAC_Upload_Stu_Accom_Template.xlsx"

CAASPP_ROLE = "Site CAASPP Coordinator"
ELPAC_ROLE = "Site ELPAC Coordinator"

CAASPP_UPLOAD_TYPE = "/mt/dt/uploadaccoms.htm"
ELPAC_UPLOAD_TYPE = "/mt/dt/uploadElpacAccoms.htm"

CAASPP_REPORT_VALUE = "CAASPP_School_Level_Student_Test_Settings_Report"
ELPAC_REPORT_VALUE = "School_Level_ELPAC_Student_Test_Settings_Report"

SHEET_XML_PATH = "xl/worksheets/sheet4.xml"


def has_changes(changes):
    """Check if a changes dict has any actual changes."""
    if not changes:
        return False
    return bool(changes['new_students'] or changes['removed_students']
                or changes['settings_added'] or changes['settings_removed'])

def resolve_concatenations(csv_path, code_mapping_path, output_path):
    """Detect concatenated TOMS codes in Aeries CSV. Prompt user to resolve each.

    Returns list of dicts: {'ssid', 'raw', 'chosen', 'col'}
    """
    import json

    with open(code_mapping_path) as f:
        known_codes = set(json.load(f)['toms_to_aeries'].keys())

    # Sort longest first so greedy match prefers longer codes
    sorted_codes = sorted(known_codes, key=len, reverse=True)

    def parse(val):
        """Greedy split against known codes. Returns list of codes, or [val] if no split."""
        remaining = val
        parsed = []
        while remaining:
            matched = False
            for code in sorted_codes:
                if remaining.startswith(code):
                    parsed.append(code)
                    remaining = remaining[len(code):]
                    matched = True
                    break
            if not matched:
                return [val]
        return parsed if len(parsed) > 1 else [val]

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))

    resolutions = []
    found_any = False

    for row in rows:
        ssid = row[0].strip()
        for col_idx in range(1, len(row)):
            val = row[col_idx].strip()
            if not val or val in known_codes:
                continue
            parsed = parse(val)
            if len(parsed) < 2:
                continue

            if not found_any:
                print("\n" + "=" * 60)
                print("CONCATENATED CODES DETECTED — resolution needed")
                print("=" * 60)
                found_any = True

            print(f"\nSSID {ssid}, column {col_idx + 1}:")
            print(f"  Raw value: {val}")
            for i, code in enumerate(parsed):
                print(f"  [{chr(65+i)}] {code}")
            print(f"  [S] Skip (clear this cell)")

            while True:
                choice = input("  Choice: ").strip().upper()
                if choice == 'S':
                    row[col_idx] = ''
                    resolutions.append({'ssid': ssid, 'raw': val, 'chosen': '(skipped)', 'col': col_idx + 1})
                    break
                elif choice and choice[0].isalpha() and ord(choice[0]) - 65 < len(parsed):
                    chosen = parsed[ord(choice[0]) - 65]
                    row[col_idx] = chosen
                    resolutions.append({'ssid': ssid, 'raw': val, 'chosen': chosen, 'col': col_idx + 1})
                    break
                else:
                    print("  Invalid choice — try again.")

    with open(output_path, 'w', newline='') as f:
        csv.writer(f).writerows(rows)

    if resolutions:
        print(f"\n  Resolved {len(resolutions)} concatenation(s). Saved to {output_path}")
    return resolutions

def filter_csv_for_errors(csv_path, parsed_errors, template_path, output_path):
    """Filter Aeries CSV to remove settings that caused TOMS errors.

    Reads the merged template to identify exact values TOMS rejected,
    then removes those values (or entire rows) from the CSV for retry.

    Returns list of dicts describing what was removed.
    """
    import openpyxl

    removed = []

    # Read the merged template to find what values caused errors
    wb = openpyxl.load_workbook(template_path, read_only=True)
    ws = wb.worksheets[3]  # sheet4 = data sheet

    # Build header mapping: column_name -> column_index
    headers = {}
    template_data = {}  # ssid -> row tuple

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            for j, val in enumerate(row):
                if val:
                    clean = str(val).strip().lstrip('*').strip()
                    headers[clean] = j
            continue
        ssid = str(row[0]).strip() if row[0] else ''
        if ssid:
            template_data[ssid] = row

    wb.close()

    # Classify each error
    values_to_remove = {}  # ssid -> set of values
    students_to_remove = set()

    for error in parsed_errors:
        ssid = error['ssid']
        col_name = error['column_name']

        if not col_name:
            # Student-level error — remove entire row
            students_to_remove.add(ssid)
            removed.append({'ssid': ssid, 'action': 'removed row', 'error': error['error']})
            continue

        # Find column index by matching header
        def normalize(s):
            # Normalize en-dash, em-dash, and whitespace for matching
            return s.replace('–', '-').replace('—', '-').replace('\n', ' ').strip()

        col_idx = headers.get(col_name)
        if col_idx is None:
            norm_col = normalize(col_name)
            for header, idx in headers.items():
                norm_header = normalize(header)
                if norm_col == norm_header or norm_col in norm_header or norm_header in norm_col:
                    col_idx = idx
                    break

        if col_idx is not None and ssid in template_data:
            val = template_data[ssid][col_idx]
            if val:
                val = str(val).strip()
                values_to_remove.setdefault(ssid, set()).add(val)
                removed.append({'ssid': ssid, 'setting': val, 'action': 'cleared', 'error': error['error']})
            else:
                # Value is blank but TOMS still errored — remove student
                students_to_remove.add(ssid)
                removed.append({'ssid': ssid, 'action': 'removed row', 'error': error['error']})
        else:
            # Can't identify the column — remove student to be safe
            students_to_remove.add(ssid)
            removed.append({'ssid': ssid, 'action': 'removed row', 'error': error['error']})

    # Filter the Aeries CSV
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))

    filtered_rows = []
    for row in rows:
        ssid = row[0].strip()
        if ssid in students_to_remove:
            continue
        if ssid in values_to_remove:
            row = [row[0]] + ['' if v.strip() in values_to_remove[ssid] else v for v in row[1:]]
        filtered_rows.append(row)

    with open(output_path, 'w', newline='') as f:
        csv.writer(f).writerows(filtered_rows)

    # Print summary
    print(f"\n  Error fixes applied:")
    for item in removed:
        if item['action'] == 'cleared':
            print(f"    SSID {item['ssid']}: removed {item['setting']}")
        else:
            print(f"    SSID {item['ssid']}: removed entire row")

    return removed


def main():
    # ── Parse arguments ──────────────────────────────────────────────────
    parser = argparse.ArgumentParser(description="Sync test settings from Aeries to TOMS")
    parser.add_argument("--test", action="store_true",
                        help="Generate and merge files but skip TOMS upload")
    args = parser.parse_args()

    driver, wait = start_driver(PROFILE_DIR)
    downloads_dir = os.path.join(os.path.dirname(PROFILE_DIR), "downloads")
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")

    # Track results for summary
    caaspp_result = None
    elpac_result = None
    caaspp_report_verify = None
    elpac_report_verify = None
    seis_import_result = None
    caaspp_errors_removed = []
    elpac_errors_removed = []
    elpac_concatenations = []
    caaspp_concatenations = []

    try:
        # ── Clean downloads folder ───────────────────────────────────────
        os.makedirs(downloads_dir, exist_ok=True)
        for f in glob.glob(os.path.join(downloads_dir, "*")):
            os.remove(f)
        print("Downloads folder cleared.\n")

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 0: SEIS → AERIES IMPORT
        # ═══════════════════════════════════════════════════════════════════
        print("=" * 60)
        print("PHASE 0: SEIS Settings Import")
        print("=" * 60)

        seis_report = seis_download_report(driver, downloads_dir)
        seis_import_result = None

        if seis_report:
            prev_aeries = sorted(glob.glob('runs/*/CAASPPTestSettings*.csv'), reverse=True)
            if prev_aeries:
                prev_aeries_csv = prev_aeries[0]
                print(f"  Filtering against: {prev_aeries_csv}")

                import_csv = transform_seis_to_aeries(seis_report, prev_aeries_csv,
                                                       os.path.join(downloads_dir, 'seis_aeries_import.csv'))

                if import_csv:
                    print("\nOpening Aeries for import...")
                    driver.get(AERIES_URL)
                    time.sleep(2)
                    aeries_login(driver)

                    if args.test:
                        print("Test mode — skipping SEIS import.")
                        seis_import_result = 'test (not imported)'
                    else:
                        with open(import_csv, newline='') as f:
                            import_count = sum(1 for row in csv.reader(f)) - 1
                        run_aeries_import(driver, os.path.abspath(import_csv))
                        seis_import_result = f'imported {import_count} new settings'
                else:
                    seis_import_result = 'no new settings'
                    print("No new SEIS settings to import.")
            else:
                print("  No previous Aeries export found — skipping SEIS filter.")
                seis_import_result = 'skipped (no baseline)'
        else:
            seis_import_result = 'SEIS download failed'

        print(f"SEIS result: {seis_import_result}\n")

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 1: AERIES EXPORTS
        # ═══════════════════════════════════════════════════════════════════
        print("=" * 60)
        print("PHASE 1: Aeries Exports")
        print("=" * 60)

        print("\nOpening Aeries...")
        driver.get(AERIES_URL)
        time.sleep(2)

        aeries_login(driver)
        aeries_navigate_to_export(driver)

        print("\n── CAASPP Export ──────────────────────────────────────")
        caaspp_export = aeries_download_export(
            driver, CAASPP_RADIO_ID, CAASPP_EXPORT_PREFIX, downloads_dir
        )
        if not caaspp_export:
            print("CAASPP export failed. Stopping.")
            return

        print("\n── ELPAC Export ───────────────────────────────────────")
        elpac_export = aeries_download_export(
            driver, ELPAC_RADIO_ID, ELPAC_EXPORT_PREFIX, downloads_dir
        )
        if not elpac_export:
            print("ELPAC export failed. Stopping.")
            return

        print("\nAeries exports complete.")

        from change_tracker import diff_runs, update_changelog, format_changes_for_report

        print("\n── Change Detection ───────────────────────────────────")
        caaspp_changes = diff_runs(caaspp_export, 'CAASPP')
        elpac_changes = diff_runs(elpac_export, 'ELPAC')

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 2: TOMS CAASPP UPLOAD
        # ═══════════════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("PHASE 2: TOMS CAASPP Upload")
        print("=" * 60)

        print("\nOpening TOMS...")
        driver.get(TOMS_URL)
        time.sleep(2)

        if not toms_login(driver, CAASPP_ROLE):
            print("TOMS CAASPP login failed. Stopping.")
            return

       # Default — used if upload block doesn't set a resolved version
        working_csv = caaspp_export

        if True:  # TEMP: force upload to flush stranded settings
            toms_navigate_to_upload(driver, upload_type_value=CAASPP_UPLOAD_TYPE)

            caaspp_template = toms_download_template(driver, downloads_dir, CAASPP_TEMPLATE)
            if not caaspp_template:
                print("CAASPP template download failed. Stopping.")
                return

            original_template = caaspp_template.replace('.xlsx', '_original.xlsx')
            shutil.copy2(caaspp_template, original_template)

            # Resolve any concatenated codes from Aeries export bugs
            resolved_csv = caaspp_export.replace('.csv', '_resolved.csv')
            caaspp_concatenations = resolve_concatenations(
                caaspp_export,
                'code_mapping.json',
                resolved_csv
            )
            if caaspp_concatenations:
                working_csv = resolved_csv
            else:
                working_csv = caaspp_export

            merge(caaspp_template, working_csv, sheet_xml_path=SHEET_XML_PATH)

            if args.test:
                caaspp_result = 'test (not uploaded)'
                print("Test mode — skipping upload.")
            else:
                result = toms_upload_and_submit(driver, caaspp_template, downloads_dir)

                retries = 0
                while isinstance(result, tuple) and result[0] == 'errors' and retries < 2:
                    retries += 1
                    _, error_csv, parsed_errors = result

                    print(f"\n  Fixing {len(parsed_errors)} error(s) and retrying (attempt {retries})...")

                    filtered_csv = os.path.join(downloads_dir, f'caaspp_filtered_{retries}.csv')
                    removed = filter_csv_for_errors(working_csv, parsed_errors, caaspp_template, filtered_csv)
                    caaspp_errors_removed.extend(removed)
                    working_csv = filtered_csv

                    shutil.copy2(original_template, caaspp_template)
                    merge(caaspp_template, working_csv, sheet_xml_path=SHEET_XML_PATH)

                    driver.switch_to.default_content()
                    driver.get(TOMS_URL)
                    time.sleep(2)
                    toms_login(driver, CAASPP_ROLE)
                    toms_navigate_to_upload(driver, upload_type_value=CAASPP_UPLOAD_TYPE)

                    result = toms_upload_and_submit(driver, caaspp_template, downloads_dir)

                caaspp_result = result if isinstance(result, str) else result[0]

                if caaspp_errors_removed:
                    print(f"\n  {len(caaspp_errors_removed)} setting(s) excluded due to TOMS errors.")
        else:
            caaspp_result = 'no changes'
            print("No CAASPP changes since last run — skipping upload.")

        print(f"CAASPP result: {caaspp_result}")

        # ── Verify CAASPP settings via report ────────────────────────────
        sheets_updated = False
        if caaspp_result in ('uploaded', 'no changes'):
            from verify_settings import download_settings_report, verify_via_report

            caaspp_report = download_settings_report(
                driver,
                CAASPP_REPORT_VALUE,
                downloads_dir,
                '*CAASPP_StudentTestSettings*'
            )
            if caaspp_report:
                caaspp_report_verify = verify_via_report(working_csv, caaspp_report, driver=driver)

                # Retry report download if too many mismatches (form.submit() can be incomplete)
                report_retry = 0
                while caaspp_report_verify['mismatched'] > 10 and report_retry < 2:
                    report_retry += 1
                    print(f"\n  Many mismatches detected — re-downloading TOMS report (attempt {report_retry})...")
                    retry_report = download_settings_report(
                        driver,
                        CAASPP_REPORT_VALUE,
                        downloads_dir,
                        '*CAASPP_StudentTestSettings*'
                    )
                    if retry_report:
                        retry_verify = verify_via_report(caaspp_export, retry_report, driver=driver)
                        if retry_verify['matched'] > caaspp_report_verify['matched']:
                            print(f"  Better result: {retry_verify['matched']}/{retry_verify['total']} matched (was {caaspp_report_verify['matched']}).")
                            caaspp_report_verify = retry_verify
                        else:
                            print(f"  No improvement: {retry_verify['matched']}/{retry_verify['total']} matched.")

            if caaspp_report:
                from sheets_upload import upload_report_to_sheets
                sheets_updated = upload_report_to_sheets(caaspp_report, sheet_name="Raw")

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 3: TOMS ELPAC UPLOAD
        # ═══════════════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("PHASE 3: TOMS ELPAC Upload")
        print("=" * 60)

        print("\nNavigating back to TOMS dashboard...")
        driver.switch_to.default_content()
        driver.get(TOMS_URL)
        time.sleep(2)

        if not toms_login(driver, ELPAC_ROLE):
            print("TOMS ELPAC login failed. Stopping.")
            return

        # Default — used if upload block doesn't set a resolved version
        elpac_working_csv = elpac_export

        if has_changes(elpac_changes):
            toms_navigate_to_upload(driver, upload_type_value=ELPAC_UPLOAD_TYPE)

            elpac_template = toms_download_template(driver, downloads_dir, ELPAC_TEMPLATE)
            if not elpac_template:
                print("ELPAC template download failed. Stopping.")
                return

            elpac_original_template = elpac_template.replace('.xlsx', '_original.xlsx')
            shutil.copy2(elpac_template, elpac_original_template)

            # Resolve any concatenated codes from Aeries export bugs
            elpac_resolved_csv = elpac_export.replace('.csv', '_resolved.csv')
            elpac_concatenations = resolve_concatenations(
                elpac_export,
                'code_mapping.json',
                elpac_resolved_csv
            )
            if elpac_concatenations:
                elpac_working_csv = elpac_resolved_csv
            else:
                elpac_working_csv = elpac_export

            merge(elpac_template, elpac_working_csv, sheet_xml_path=SHEET_XML_PATH)

            if args.test:
                elpac_result = 'test (not uploaded)'
                print("Test mode — skipping upload.")
            else:
                result = toms_upload_and_submit(driver, elpac_template, downloads_dir)

                retries = 0
                while isinstance(result, tuple) and result[0] == 'errors' and retries < 2:
                    retries += 1
                    _, error_csv, parsed_errors = result

                    print(f"\n  Fixing {len(parsed_errors)} error(s) and retrying (attempt {retries})...")

                    filtered_csv = os.path.join(downloads_dir, f'elpac_filtered_{retries}.csv')
                    removed = filter_csv_for_errors(elpac_working_csv, parsed_errors, elpac_template, filtered_csv)
                    elpac_errors_removed.extend(removed)
                    elpac_working_csv = filtered_csv

                    shutil.copy2(elpac_original_template, elpac_template)
                    merge(elpac_template, elpac_working_csv, sheet_xml_path=SHEET_XML_PATH)

                    driver.switch_to.default_content()
                    driver.get(TOMS_URL)
                    time.sleep(2)
                    toms_login(driver, ELPAC_ROLE)
                    toms_navigate_to_upload(driver, upload_type_value=ELPAC_UPLOAD_TYPE)

                    result = toms_upload_and_submit(driver, elpac_template, downloads_dir)

                elpac_result = result if isinstance(result, str) else result[0]

                if elpac_errors_removed:
                    print(f"\n  {len(elpac_errors_removed)} setting(s) excluded due to TOMS errors.")
        else:
            elpac_result = 'no changes'
            print("No ELPAC changes since last run — skipping upload.")

        print(f"ELPAC result: {elpac_result}")

        # ── Verify ELPAC settings via report ─────────────────────────────
        if elpac_result in ('uploaded', 'no changes'):
            from verify_settings import download_settings_report, verify_via_report

            elpac_report = download_settings_report(
                driver,
                ELPAC_REPORT_VALUE,
                downloads_dir,
                '*_StudentTestSettings_*',
                form_id='elpacstudentTestSettingsForm'
            )
            if elpac_report:
                elpac_report_verify = verify_via_report(elpac_working_csv, elpac_report, driver=driver)

                # Retry report download if too many mismatches (form.submit() can be incomplete)
                report_retry = 0
                while elpac_report_verify['mismatched'] > 10 and report_retry < 2:
                    report_retry += 1
                    print(f"\n  Many mismatches detected — re-downloading TOMS report (attempt {report_retry})...")
                    retry_report = download_settings_report(
                        driver,
                        ELPAC_REPORT_VALUE,
                        downloads_dir,
                        '*_StudentTestSettings_*',
                        form_id='elpacstudentTestSettingsForm'
                    )
                    if retry_report:
                        retry_verify = verify_via_report(elpac_export, retry_report, report_settings_start_col=17, driver=driver)
                        if retry_verify['matched'] > elpac_report_verify['matched']:
                            print(f"  Better result: {retry_verify['matched']}/{retry_verify['total']} matched (was {elpac_report_verify['matched']}).")
                            elpac_report_verify = retry_verify
                        else:
                            print(f"  No improvement: {retry_verify['matched']}/{retry_verify['total']} matched.")

        # ── Archive run files ────────────────────────────────────────────
        run_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        run_dir = os.path.join("runs", run_timestamp)
        os.makedirs(run_dir, exist_ok=True)

        for f in glob.glob(os.path.join(downloads_dir, "*")):
            shutil.copy2(f, run_dir)
        print(f"\nRun files archived to: {run_dir}")

        if not args.test and caaspp_result in ('uploaded', 'no changes') and elpac_result in ('uploaded', 'no changes'):
            for f in glob.glob(os.path.join(downloads_dir, "*")):
                os.remove(f)
            print("Downloads folder cleaned up.")
        else:
            print("Downloads folder preserved — not all uploads succeeded.")

        if caaspp_changes:
            update_changelog(caaspp_changes)
        if elpac_changes:
            update_changelog(elpac_changes)

        # ── Generate report and send email ───────────────────────────────
        from report_generator import generate_report, send_email

        pdf_path, text_summary = generate_report(
            run_dir, caaspp_result, elpac_result,
            caaspp_report_verify, elpac_report_verify,
            caaspp_changes=caaspp_changes,
            elpac_changes=elpac_changes,
            sheets_updated=sheets_updated,
            seis_result=seis_import_result,
            caaspp_errors_removed=caaspp_errors_removed,
            elpac_errors_removed=elpac_errors_removed,
            caaspp_concatenations=caaspp_concatenations,
            elpac_concatenations=elpac_concatenations
        )

        today_str = datetime.now().strftime("%m/%d/%Y")
        send_email(
            f"Test Settings Sync — {today_str}",
            text_summary
        )

        # ═══════════════════════════════════════════════════════════════════
        # SUMMARY
        # ═══════════════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("SYNC COMPLETE")
        print("=" * 60)

        print(f"  SEIS:   {seis_import_result}")

        caaspp_line = f"  CAASPP: {caaspp_result}"
        if caaspp_report_verify:
            caaspp_line += f" ({caaspp_report_verify['matched']}/{caaspp_report_verify['total']} verified)"
        print(caaspp_line)

        elpac_line = f"  ELPAC:  {elpac_result}"
        if elpac_report_verify:
            elpac_line += f" ({elpac_report_verify['matched']}/{elpac_report_verify['total']} verified)"
        print(elpac_line)

        print(f"  Archive: {run_dir}")
        if not args.test and caaspp_result == 'uploaded' and elpac_result == 'uploaded':
            print(f"  Files:  cleaned up")
        else:
            print(f"  Files:  preserved for review")

    except Exception as e:
        import traceback
        print(f"\nUnexpected error: {e}")
        print(traceback.format_exc())

    finally:
        print("\nBrowser will stay open until you press Enter.")
        input("Press Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    main()