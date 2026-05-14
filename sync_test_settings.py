"""Orchestrator — runs all export and upload workflows in a single session.

Flow:
1. Clean downloads folder
2. Open Aeries, download CAASPP and ELPAC exports
3. Open TOMS as CAASPP Coordinator, download template, merge, upload, verify
4. Switch to ELPAC Coordinator, download template, merge, upload, verify
5. Archive all files
"""

import time
import os
import glob
import shutil
import argparse
from datetime import datetime, timedelta
from browser_helpers import start_driver
from aeries_helpers import aeries_login, aeries_navigate_to_export, aeries_download_export
from toms_helpers import toms_login, toms_navigate_to_upload, toms_download_template, toms_upload_and_submit
from merge_data import merge

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

    try:
        # ── Clean downloads folder ───────────────────────────────────────
        os.makedirs(downloads_dir, exist_ok=True)
        for f in glob.glob(os.path.join(downloads_dir, "*")):
            os.remove(f)
        print("Downloads folder cleared.\n")

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 1: AERIES EXPORTS
        # ═══════════════════════════════════════════════════════════════════
        print("=" * 60)
        print("PHASE 1: Aeries Exports")
        print("=" * 60)

        print("\nOpening Aeries...")
        driver.get(AERIES_URL)
        time.sleep(2)

        # Log into Aeries — auto-clicks Log In if credentials are filled
        aeries_login(driver)

        # Navigate: School Info > Imports and Exports > State Testing Export Files
        aeries_navigate_to_export(driver)

        # Download CAASPP export CSV
        print("\n── CAASPP Export ──────────────────────────────────────")
        caaspp_export = aeries_download_export(
            driver, CAASPP_RADIO_ID, CAASPP_EXPORT_PREFIX, downloads_dir
        )
        if not caaspp_export:
            print("CAASPP export failed. Stopping.")
            return

        # Download ELPAC export CSV (same page, different radio button)
        print("\n── ELPAC Export ───────────────────────────────────────")
        elpac_export = aeries_download_export(
            driver, ELPAC_RADIO_ID, ELPAC_EXPORT_PREFIX, downloads_dir
        )
        if not elpac_export:
            print("ELPAC export failed. Stopping.")
            return

        print("\nAeries exports complete.")

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 2: TOMS CAASPP UPLOAD
        # ═══════════════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("PHASE 2: TOMS CAASPP Upload")
        print("=" * 60)

        print("\nOpening TOMS...")
        driver.get(TOMS_URL)
        time.sleep(2)

        # Log into TOMS as CAASPP Coordinator
        if not toms_login(driver, CAASPP_ROLE):
            print("TOMS CAASPP login failed. Stopping.")
            return

        # Navigate: Students > Upload > Test Settings > Next
        toms_navigate_to_upload(driver, upload_type_value=CAASPP_UPLOAD_TYPE)

        # Download the blank CAASPP template from TOMS
        caaspp_template = toms_download_template(driver, downloads_dir, CAASPP_TEMPLATE)
        if not caaspp_template:
            print("CAASPP template download failed. Stopping.")
            return

        # Fill the template with Aeries data (zip-level XML merge)
        merge(caaspp_template, caaspp_export, sheet_xml_path=SHEET_XML_PATH)

        # Upload the merged file to TOMS (or skip in test mode)
        if args.test:
            caaspp_result = 'test (not uploaded)'
            print("Test mode — skipping upload.")
        else:
            caaspp_result = toms_upload_and_submit(driver, caaspp_template)
        print(f"CAASPP result: {caaspp_result}")

        # ── Verify CAASPP upload via settings report ─────────────────────
        if caaspp_result == 'uploaded':
            from verify_settings import download_settings_report, verify_via_report

            # Navigate to Reports tab and download the full settings report
            caaspp_report = download_settings_report(
                driver,
                CAASPP_REPORT_VALUE,
                downloads_dir,
                '*CAASPP_StudentTestSettings*'
            )
            # Compare the report against what we uploaded
            if caaspp_report:
                caaspp_report_verify = verify_via_report(caaspp_export, caaspp_report)

        # Upload CAASPP report to Google Sheets
            if caaspp_report:
                from sheets_upload import upload_report_to_sheets
                upload_report_to_sheets(caaspp_report, sheet_name="Raw")        

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 3: TOMS ELPAC UPLOAD
        # ═══════════════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("PHASE 3: TOMS ELPAC Upload")
        print("=" * 60)

        # Navigate back to TOMS dashboard to switch roles
        print("\nNavigating back to TOMS dashboard...")
        driver.switch_to.default_content()
        driver.get(TOMS_URL)
        time.sleep(2)

        # Log into TOMS as ELPAC Coordinator
        if not toms_login(driver, ELPAC_ROLE):
            print("TOMS ELPAC login failed. Stopping.")
            return

        # Navigate: Students > Upload > Test Settings > Next
        toms_navigate_to_upload(driver, upload_type_value=ELPAC_UPLOAD_TYPE)

        # Download the blank ELPAC template from TOMS
        elpac_template = toms_download_template(driver, downloads_dir, ELPAC_TEMPLATE)
        if not elpac_template:
            print("ELPAC template download failed. Stopping.")
            return

        # Fill the template with Aeries data (zip-level XML merge)
        merge(elpac_template, elpac_export, sheet_xml_path=SHEET_XML_PATH)

        # Upload the merged file to TOMS (or skip in test mode)
        if args.test:
            elpac_result = 'test (not uploaded)'
            print("Test mode — skipping upload.")
        else:
            elpac_result = toms_upload_and_submit(driver, elpac_template)
        print(f"ELPAC result: {elpac_result}")

        # ── Verify ELPAC upload via settings report ──────────────────────
        if elpac_result == 'uploaded':
            from verify_settings import download_settings_report, verify_via_report

            # Navigate to Reports tab and download the full settings report
            elpac_report = download_settings_report(
                driver,
                ELPAC_REPORT_VALUE,
                downloads_dir,
                '*_StudentTestSettings_*',
                form_id='elpacstudentTestSettingsForm'
            )
            # Compare the report against what we uploaded
            if elpac_report:
                elpac_report_verify = verify_via_report(elpac_export, elpac_report, report_settings_start_col=17)

        # ── Archive run files ────────────────────────────────────────────
        run_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        run_dir = os.path.join("runs", run_timestamp)
        os.makedirs(run_dir, exist_ok=True)

        # Copy all files from downloads to the run archive
        for f in glob.glob(os.path.join(downloads_dir, "*")):
            shutil.copy2(f, run_dir)
        print(f"\nRun files archived to: {run_dir}")

        # Clean downloads folder if both uploads succeeded
        if not args.test and caaspp_result == 'uploaded' and elpac_result == 'uploaded':
            for f in glob.glob(os.path.join(downloads_dir, "*")):
                os.remove(f)
            print("Downloads folder cleaned up.")
        else:
            print("Downloads folder preserved — not all uploads succeeded.")

        # ═══════════════════════════════════════════════════════════════════
        # SUMMARY
        # ═══════════════════════════════════════════════════════════════════
        print("\n" + "=" * 60)
        print("SYNC COMPLETE")
        print("=" * 60)

        # CAASPP result line with verification count if available
        caaspp_line = f"  CAASPP: {caaspp_result}"
        if caaspp_report_verify:
            caaspp_line += f" ({caaspp_report_verify['matched']}/{caaspp_report_verify['total']} verified)"
        print(caaspp_line)

        # ELPAC result line with verification count if available
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