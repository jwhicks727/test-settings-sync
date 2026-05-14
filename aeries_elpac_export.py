"""Aeries ELPAC export — download ELPAC test settings CSV."""

import time
import os
from browser_helpers import start_driver
from aeries_helpers import aeries_login, aeries_navigate_to_export, aeries_download_export

# ── Configuration ──────────────────────────────────────────────────────────────
AERIES_URL = "https://soaracademy.aeries.net/admin/Login.aspx"
PROFILE_DIR = "/Users/jasonhicks/Projects/test-settings-sync/edge-profile"
RADIO_ID = "ctl00_MainContent_rdoWhichSettings_3"
EXPORT_PREFIX = "ELPACTestSettings"


def main():
    driver, wait = start_driver(PROFILE_DIR)
    downloads_dir = os.path.join(os.path.dirname(PROFILE_DIR), "downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    try:
        print("Opening Aeries...")
        driver.get(AERIES_URL)
        time.sleep(2)

        aeries_login(driver)
        aeries_navigate_to_export(driver)
        export_file = aeries_download_export(driver, RADIO_ID, EXPORT_PREFIX, downloads_dir)

        if export_file:
            print(f"\nELPAC export complete: {export_file}")
        else:
            print("\nExport failed.")

    except Exception as e:
        print(f"Unexpected error: {e}")

    finally:
        print("\nBrowser will stay open until you press Enter.")
        input("Press Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    main()