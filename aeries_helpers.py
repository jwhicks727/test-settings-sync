"""Shared Aeries functions for CAASPP and ELPAC export workflows.

Handles login, navigation to State Testing Export Files, and download.
"""

import time
from datetime import datetime, timedelta
from browser_helpers import find_element, js_click


def aeries_login(driver):
    """Handle Aeries login and district selection."""
    for attempt in range(10):
        login_button = find_element(driver, '#btnSignIn_Aeries')
        if login_button:
            print("Login page detected. Clicking Log In...")
            time.sleep(1)
            js_click(driver, login_button)
            time.sleep(3)
            break

        if "Search Student" in (driver.page_source or ""):
            break

        time.sleep(0.5)

    # Handle district selection if present
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

    for attempt in range(50):
        if "Search Student" in (driver.page_source or ""):
            break
        time.sleep(0.1)

    print("Dashboard loaded.")
    return True


def aeries_navigate_to_export(driver):
    """Navigate from dashboard to School Info > Imports and Exports > State Testing Export Files."""
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

    print("Clicking State Testing Export Files...")
    driver.execute_script("""
        var link = document.getElementById('ctl00_NavigationTreet281');
        if (link) link.click();
    """)
    time.sleep(2)


def aeries_download_export(driver, radio_id, export_prefix, downloads_dir):
    """Select a test type, enter tomorrow's date, and download.

    Args:
        driver: Selenium WebDriver instance
        radio_id: ID of the radio button to select
        export_prefix: Filename prefix, e.g. "CAASPPTestSettings"
        downloads_dir: Path to downloads directory

    Returns:
        Path to the downloaded file, or None if download failed
    """
    print(f"Selecting test settings radio: {radio_id}...")
    driver.execute_script(f"""
        var radio = document.getElementById('{radio_id}');
        if (radio) radio.click();
    """)
    print("Option selected.")
    time.sleep(1)

    # Enter tomorrow's date
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%m/%d/%Y")
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
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

    print("Clicking Download File...")
    driver.execute_script("""
        var btn = document.getElementById('ctl00_MainContent_btnDownload');
        if (btn) btn.click();
    """)
    print("Download File clicked.")
    time.sleep(2)

    import os
    export_file = os.path.join(downloads_dir, f"{export_prefix}{tomorrow_str}.csv")
    print("Waiting for export to download...")
    for attempt in range(30):
        if os.path.exists(export_file) and not os.path.exists(export_file + ".crdownload"):
            break
        time.sleep(0.5)

    if os.path.exists(export_file):
        print(f"Export saved: {export_file}")
        return export_file
    else:
        print("Export download failed.")
        return None