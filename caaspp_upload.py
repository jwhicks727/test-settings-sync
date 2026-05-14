"""CAASPP test settings upload — Aeries export to TOMS."""

import time
import os
from datetime import datetime, timedelta
from browser_helpers import start_driver
from toms_helpers import toms_login, toms_navigate_to_upload, toms_download_template, toms_upload_and_submit
from merge_data import merge

# ── Configuration ──────────────────────────────────────────────────────────────
TOMS_URL = "https://mytoms.ets.org/TOMS"
PROFILE_DIR = "/Users/jasonhicks/Projects/test-settings-sync/edge-profile"
ROLE_TEXT = "Site CAASPP Coordinator"
TEMPLATE_FILENAME = "CAASPP_Upload_Stu_Accom_Template.xlsx"
SHEET_XML_PATH = "xl/worksheets/sheet4.xml"


def main():
    driver, wait = start_driver(PROFILE_DIR)
    downloads_dir = os.path.join(os.path.dirname(PROFILE_DIR), "downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    try:
        print("Opening TOMS...")
        driver.get(TOMS_URL)
        time.sleep(2)

        if not toms_login(driver, ROLE_TEXT):
            return

        toms_navigate_to_upload(driver)

        template_file = toms_download_template(driver, downloads_dir, TEMPLATE_FILENAME)
        if not template_file:
            return

        # ── Merge Aeries data into template ──────────────────────────────
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
        aeries_export = os.path.join(downloads_dir, f"CAASPPTestSettings{tomorrow_str}.csv")

        if not os.path.exists(aeries_export):
            print(f"Aeries export not found: {aeries_export}")
            print("Run aeries_caaspp_export.py first.")
            return

        merge(template_file, aeries_export, sheet_xml_path=SHEET_XML_PATH)

        result = toms_upload_and_submit(driver, template_file)

        if result == 'errors':
            # TODO: Download error CSV, fix template, re-upload
            pass

    except Exception as e:
        print(f"Unexpected error: {e}")

    finally:
        print("\nBrowser will stay open until you press Enter.")
        input("Press Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    main()