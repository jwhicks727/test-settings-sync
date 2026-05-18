"""SEIS export — generate and download TOMS Summative Assessments report.

Navigates SEIS, generates the report, and downloads the TOMS export.
"""

import time
from browser_helpers import start_driver, find_element, js_click

# ── Configuration ──────────────────────────────────────────────────────────────
SEIS_URL = "https://seis.org/login"
PROFILE_DIR = "/Users/jasonhicks/Projects/test-settings-sync/edge-profile"


def main():
    driver, wait = start_driver(PROFILE_DIR)

    try:
        print("Opening SEIS...")
        driver.get(SEIS_URL)
        time.sleep(2)

        # ── Check login state ────────────────────────────────────────────
        for attempt in range(10):
            # Check for login page
            login_button = driver.execute_script("""
                var buttons = document.querySelectorAll('button[type="submit"]');
                for (var i = 0; i < buttons.length; i++) {
                    if (buttons[i].textContent.trim().includes('Login')) {
                        return buttons[i];
                    }
                }
                return null;
            """)

            if login_button:
                print("Login page detected. Clicking Login...")
                time.sleep(1)
                js_click(driver, login_button)
                time.sleep(3)

                # Check if we got past login or need manual auth
                if "login" in driver.current_url.lower():
                    print("Manual login required — please log in in the browser.")
                    input("Press Enter once you are logged in...")
                    time.sleep(2)
                break
            
            # Check if we're already past login
            if "login" not in driver.current_url.lower():
                break

            time.sleep(0.5)

        print("Logged in to SEIS.")

        # ── Click Reports dropdown ───────────────────────────────────────
        print("Clicking Reports...")
        driver.execute_script("""
            var links = document.querySelectorAll('.dropdown-toggle');
            for (var i = 0; i < links.length; i++) {
                if (links[i].textContent.trim().startsWith('Reports')) {
                    links[i].click();
                    break;
                }
            }
        """)
        time.sleep(1)

        # ── Click TOMS Summative Assessments ─────────────────────────────
        print("Clicking TOMS Summative Assessments...")
        driver.execute_script("""
            var link = document.querySelector('a[href="/reports/toms"]');
            if (link) link.click();
        """)
        time.sleep(1)

        # ── Generate Report ──────────────────────────────────────────────
        print("Clicking Generate Report...")
        driver.execute_script("""
            var btn = document.querySelector('button[data-ng-click="vm.createReport()"]');
            if (btn) btn.click();
        """)
        time.sleep(1)

        # ── Download TOMS report ─────────────────────────────────────────
        print("Clicking TOMS Download...")
        driver.execute_script("""
            var rows = document.querySelectorAll('tr[data-ng-repeat="report in vm.reports"]');
            if (rows.length > 0) {
                var links = rows[0].querySelectorAll('a[data-ng-click]');
                for (var i = 0; i < links.length; i++) {
                    if (links[i].getAttribute('data-ng-click').includes('true')) {
                        links[i].click();
                        break;
                    }
                }
            }
        """)
        print("TOMS download initiated.")
        
        # ── Wait for download to complete ────────────────────────────────
        import os, glob
        downloads_dir = os.path.join(os.path.dirname(PROFILE_DIR), "downloads")
        
        # Find the newest xlsx file
        print("Waiting for download...")
        seis_report = None
        for attempt in range(30):
            xlsx_files = glob.glob(os.path.join(downloads_dir, "*.xlsx"))
            xlsx_files = [f for f in xlsx_files if not f.endswith('.crdownload')]
            if xlsx_files:
                newest = max(xlsx_files, key=os.path.getmtime)
                # Check it was modified in the last 30 seconds
                import time as time_mod
                if time_mod.time() - os.path.getmtime(newest) < 30:
                    seis_report = newest
                    break
            time.sleep(0.2)

        if seis_report:
            print(f"SEIS report saved: {seis_report}")
        else:
            print("SEIS report download failed.")

    except Exception as e:
        print(f"Unexpected error: {e}")

    finally:
        print("\nBrowser will stay open until you press Enter.")
        input("Press Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    main()