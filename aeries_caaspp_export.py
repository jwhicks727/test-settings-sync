"""Aeries CAASPP export — log in, navigate to State Testing Export Files, download reports.

Currently: navigates to Aeries, handles login, confirms dashboard.
"""

import time
import os
import glob
from datetime import datetime, timedelta
from browser_helpers import start_driver, find_element, js_click

# ── Configuration ──────────────────────────────────────────────────────────────
AERIES_URL = "https://soaracademy.aeries.net/admin/Login.aspx"
PROFILE_DIR = "/Users/jasonhicks/Projects/test-settings-sync/edge-profile"


def main():
    driver, wait = start_driver(PROFILE_DIR)

    try:
        print("Opening Aeries...")
        driver.get(AERIES_URL)
        time.sleep(2)

        # ── Check login state ────────────────────────────────────────────────
        for attempt in range(10):
            # Check for login page — auto-click Log In if credentials are filled
            login_button = find_element(driver, '#btnSignIn_Aeries')
            if login_button:
                print("Login page detected. Clicking Log In...")
                time.sleep(0.5)
                js_click(driver, login_button)
                time.sleep(2)
                break

            # Check for dashboard
            if "Search Student" in (driver.page_source or ""):
                break

            time.sleep(0.5)

        # ── Handle district selection if present ─────────────────────────────
        # Look for Continue button on district selection screen
        continue_button = driver.execute_script("""
            var buttons = document.querySelectorAll('input[type="submit"], button');
            for (var i = 0; i < buttons.length; i++) {
                if (buttons[i].value === 'Continue' || buttons[i].textContent.includes('Continue')) {
                    return buttons[i];
                }
            }
            return null;
        """)

        if continue_button:
            print("District selection screen — clicking Continue...")
            driver.execute_script("arguments[0].click();", continue_button)
            time.sleep(2)

        # ── Confirm dashboard loaded ─────────────────────────────────────────
        for attempt in range(50):
            if "Search Student" in (driver.page_source or ""):
                break
            time.sleep(0.1)

        print("Dashboard loaded.")

        # ── Navigate to School Info ──────────────────────────────────────────
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

        # ── Navigate to Imports and Exports ──────────────────────────────────
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

        # ── Navigate to State Testing Export Files ───────────────────────────
        print("Clicking State Testing Export Files...")
        driver.execute_script("""
            var link = document.getElementById('ctl00_NavigationTreet281');
            if (link) link.click();
        """)
        time.sleep(2)

        # ── Select CAASPP Student Test Settings ──────────────────────────────
        print("Selecting CAASPP Student Test Settings...")
        driver.execute_script("""
            var radio = document.getElementById('ctl00_MainContent_rdoWhichSettings_0');
            if (radio) radio.click();
        """)
        print("CAASPP option selected.")
        time.sleep(1)

        # ── Enter tomorrow's date ────────────────────────────────────────────
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%m/%d/%Y")
        print(f"Entering date: {tomorrow}...")
        driver.execute_script("""
            var input = document.getElementById('ctl00_MainContent_txtDateTD_txtKendoDatePicker');
            if (!input) return;
            var widget = $(input).data('kendoDatePicker');
            if (widget) {
                widget.value(new Date(arguments[0]));
                widget.trigger('change');
            }
        """, tomorrow)
        print("Date entered.")
        time.sleep(1)

        # ── Click Download File ──────────────────────────────────────────────
        print("Clicking Download File...")
        driver.execute_script("""
            var btn = document.getElementById('ctl00_MainContent_btnDownload');
            if (btn) btn.click();
        """)
        print("Download File clicked.")
        time.sleep(2)

        # ── Wait for export file to download ─────────────────────────────────
        downloads_dir = os.path.join(os.path.dirname(PROFILE_DIR), "downloads")
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
        export_file = os.path.join(downloads_dir, f"CAASPPTestSettings{tomorrow_str}.csv")
        print("Waiting for export to download...")
        for attempt in range(30):
            if os.path.exists(export_file) and not os.path.exists(export_file + ".crdownload"):
                break
            time.sleep(0.5)

        if os.path.exists(export_file):
            print(f"Export saved: {export_file}")
        else:
            print("Export download failed.")
            return

    except Exception as e:
        print(f"Unexpected error: {e}")

    finally:
        print("\nBrowser will stay open until you press Enter.")
        input("Press Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    main()