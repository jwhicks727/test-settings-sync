"""SEIS export — generate and download TOMS Summative Assessments report.

Navigates SEIS, generates the report, and downloads the TOMS export.
"""

import time
import os
import glob
from browser_helpers import start_driver, find_element, js_click

# ── Configuration ──────────────────────────────────────────────────────────────
SEIS_URL = "https://seis.org/login"
PROFILE_DIR = "/Users/jasonhicks/Projects/test-settings-sync/edge-profile"


def is_seis_dashboard_loaded(driver):
    """Check if SEIS dashboard is loaded. Returns False if MFA page is showing."""
    # First check: are we on the MFA page?
    if driver.execute_script("return document.getElementById('factorType') !== null;"):
        return False

    # Second check: is the Reports dropdown actually accessible?
    return driver.execute_script("""
        var links = document.querySelectorAll('.dropdown-toggle');
        for (var i = 0; i < links.length; i++) {
            if (links[i].textContent.trim().startsWith('Reports')) {
                return true;
            }
        }
        return false;
    """)


def wait_for_seis_dashboard(driver, timeout=10):
    """Poll for dashboard up to timeout seconds. Returns True if loaded."""
    for attempt in range(timeout * 10):
        if is_seis_dashboard_loaded(driver):
            return True
        time.sleep(0.1)
    return False


def seis_login(driver):
    """Handle SEIS login including MFA / additional authentication.

    Clicks login button, then watches for either MFA prompt or dashboard.
    If MFA appears, pauses for user to complete it in the browser.
    """
    # Try to click the login button if it's visible
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

    # Poll for either MFA prompt or dashboard — MFA takes priority
    for attempt in range(100):  # up to 10 seconds
        mfa_present = driver.execute_script(
            "return document.getElementById('factorType') !== null;"
        )
        if mfa_present:
            print("=" * 60)
            print("SEIS MFA REQUIRED")
            print("=" * 60)
            print("Complete the multi-factor authentication in the browser.")
            print()
            input("Press Enter once you have reached the SEIS dashboard...")
            time.sleep(2)
            # Verify dashboard loaded after user completes MFA
            if wait_for_seis_dashboard(driver, timeout=15):
                print("Logged in to SEIS.")
                return True
            print("Dashboard not detected after MFA — continuing on user's word.")
            return True

        if is_seis_dashboard_loaded(driver):
            print("Logged in to SEIS.")
            return True

        time.sleep(0.1)

    # Neither MFA nor dashboard detected — prompt for safety
    print("=" * 60)
    print("SEIS state unclear — please verify you're at the dashboard")
    print("=" * 60)
    input("Press Enter once you have reached the SEIS dashboard...")
    time.sleep(2)
    return True


def seis_download_report(driver, downloads_dir):
    """Navigate SEIS, generate report, and download TOMS export.

    Args:
        driver: Selenium WebDriver instance
        downloads_dir: Path to downloads directory

    Returns:
        Path to downloaded xlsx, or None if failed
    """
    print("\nOpening SEIS...")
    driver.get(SEIS_URL)
    time.sleep(2)

    # Handle login including potential 2FA / additional auth
    if not seis_login(driver):
        return None

    # Click Reports dropdown
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

    # Click TOMS Summative Assessments
    print("Clicking TOMS Summative Assessments...")
    driver.execute_script("""
        var link = document.querySelector('a[href="/reports/toms"]');
        if (link) link.click();
    """)
    time.sleep(1)

    # Generate Report
    print("Clicking Generate Report...")
    driver.execute_script("""
        var btn = document.querySelector('button[data-ng-click="vm.createReport()"]');
        if (btn) btn.click();
    """)
    time.sleep(5)

    # Download TOMS report
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

    # Wait for download
    print("Waiting for download...")
    seis_report = None
    for attempt in range(30):
        xlsx_files = glob.glob(os.path.join(downloads_dir, "*.xlsx"))
        xlsx_files = [f for f in xlsx_files if not f.endswith('.crdownload')]
        if xlsx_files:
            newest = max(xlsx_files, key=os.path.getmtime)
            import time as time_mod
            if time_mod.time() - os.path.getmtime(newest) < 30:
                seis_report = newest
                break
        time.sleep(1)

    if seis_report:
        print(f"SEIS report saved: {seis_report}")
    else:
        print("SEIS report download failed.")

    return seis_report


def main():
    driver, wait = start_driver(PROFILE_DIR)
    downloads_dir = os.path.join(os.path.dirname(PROFILE_DIR), "downloads")

    try:
        seis_download_report(driver, downloads_dir)
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        print("\nBrowser will stay open until you press Enter.")
        input("Press Enter to close browser...")
        driver.quit()


if __name__ == "__main__":
    main()