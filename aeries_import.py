"""Aeries import — upload transformed SEIS data into the STS table.

Navigates to Import Data to Aeries, uploads the CSV,
configures the STS table mapping, and imports.
"""

import time
import os
from browser_helpers import start_driver, find_element, js_click
from aeries_helpers import aeries_login

# ── Configuration ──────────────────────────────────────────────────────────────
AERIES_URL = "https://soaracademy.aeries.net/admin/Login.aspx"
PROFILE_DIR = "/Users/jasonhicks/Projects/test-settings-sync/edge-profile"


def navigate_to_import(driver):
    """Navigate from dashboard to School Info > Imports and Exports > Import Data to Aeries."""
    print("Clicking School Info...")
    driver.execute_script("""
        var spans = document.querySelectorAll('.next-sidebar-link-text');
        for (var i = 0; i < spans.length; i++) {
            if (spans[i].textContent.trim() === 'School Info') {
                spans[i].closest('a') ? spans[i].closest('a').click() : spans[i].click();
                break;
            }
        }
    """)
    time.sleep(1)

    print("Clicking Imports and Exports...")
    driver.execute_script("""
        var spans = document.querySelectorAll('.next-sidebar-entry-group');
        for (var i = 0; i < spans.length; i++) {
            if (spans[i].textContent.trim() === 'Imports and Exports') {
                spans[i].click();
                break;
            }
        }
    """)
    time.sleep(1)

    print("Clicking Import Data to Aeries...")
    driver.execute_script("""
        document.querySelector('a[href="ImportData.aspx"]').click();
    """)
    time.sleep(2)
    print("Import page loaded.")


def main():
    driver, wait = start_driver(PROFILE_DIR)
    downloads_dir = os.path.join(os.path.dirname(PROFILE_DIR), "downloads")

    try:
        print("Opening Aeries...")
        driver.get(AERIES_URL)
        time.sleep(2)

        aeries_login(driver)
        navigate_to_import(driver)

        # Step 1: Upload CSV
        csv_path = os.path.join(downloads_dir, "seis_aeries_import.csv")
        print(f"Uploading {csv_path}...")
        file_input = find_element(driver, "input.box__file")
        file_input.send_keys(csv_path)
        time.sleep(2)
        print("CSV uploaded.")

        # Step 2: Expand Destination Table accordion
        print("Expanding Destination Table...")
        driver.execute_script('document.getElementById("TableAccordionTitle").click();')
        time.sleep(1)

        # Step 3: Select STS table
        print("Selecting STS table...")
        driver.execute_script("""
            var cells = document.querySelectorAll('td[role="gridcell"]');
            for (var i = 0; i < cells.length; i++) {
                if (cells[i].textContent.trim() === 'STS') {
                    cells[i].click();
                    break;
                }
            }
        """)

        time.sleep(1)

        # Step 4: Check "Map ID by this STU.CID" checkbox
        print("Checking 'Map ID by this STU.CID'...")
        checkbox = find_element(driver, "input.chkTranslateID")
        if not checkbox.is_selected():
            js_click(driver, checkbox)
        time.sleep(1)

        # Step 5: Select CID from the mapping dropdown
        print("Selecting CID from dropdown...")
        driver.execute_script("""
            var items = document.querySelectorAll('.ddlitem');
            for (var i = 0; i < items.length; i++) {
                if (items[i].textContent.trim() === 'CID') {
                    items[i].click();
                    break;
                }
            }
        """)
        time.sleep(1)

        # Step 6: Click Import — COMMENTED OUT until human verification is complete
        print("\n** Import button NOT clicked (commented out for safety). **")
        # print("Clicking Import...")
        # import_btn = find_element(driver, "a.ImportData")
        # js_click(driver, import_btn)
        # time.sleep(3)
        # print("Import submitted.")

    except Exception as e:
        print(f"Unexpected error: {e}")

    finally:
        print("\nBrowser will stay open until you press Enter.")
        input("Press Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    main()