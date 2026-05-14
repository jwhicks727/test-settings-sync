"""Shared TOMS functions for CAASPP and ELPAC upload workflows.

Handles login, role selection, navigation, template download,
file upload, and validation bounce.
"""

import time
import os
from browser_helpers import find_element, js_click


def toms_login(driver, role_text):
    """Handle TOMS login, role selection, and dashboard confirmation.

    Args:
        driver: Selenium WebDriver instance
        role_text: Role to select, e.g. "Site CAASPP Coordinator"
    """
    # ── Check login state ────────────────────────────────────────────────
    for attempt in range(10):
        login_button = find_element(driver, '#kc-login')
        if login_button:
            print("Login page detected. Clicking Secure Logon...")
            time.sleep(1)
            js_click(driver, login_button)
            time.sleep(2)

            # Wait for either role selection, dashboard, or 2SV
            landed = False
            for check in range(20):
                # Check for role selection dropdown
                role_dropdown = driver.execute_script("""
                    var opts = document.querySelectorAll('.myTOMS_roleselect_option');
                    return opts.length > 0;
                """)
                if role_dropdown:
                    print("Logged in — role selection screen.")
                    landed = True
                    break

                if "MyTOMS Home" in (driver.page_source or ""):
                    print("Logged in — dashboard loaded.")
                    landed = True
                    break

                time.sleep(0.5)

            if not landed:
                print("Verification screen detected — complete it in the browser.")
                input("Press Enter once you are past verification...")
                time.sleep(2)
            break


    # ── Handle role selection if present ──────────────────────────────────
    role_present = driver.execute_script("""
        var elements = document.querySelectorAll('td, li, a, span, div');
        for (var i = 0; i < elements.length; i++) {
            if (elements[i].textContent.includes('Please select a role')) {
                return true;
            }
        }
        return false;
    """)

    if role_present:
        print(f"Selecting role: {role_text}...")

        role_selected = driver.execute_script("""
            var selects = document.querySelectorAll('select');
            for (var s = 0; s < selects.length; s++) {
                var options = selects[s].querySelectorAll('option');
                for (var i = 0; i < options.length; i++) {
                    if (options[i].textContent.includes(arguments[0])) {
                        selects[s].value = options[i].value;
                        selects[s].dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                }
            }
            return false;
        """, role_text)

        if role_selected:
            print("Role selected.")
            time.sleep(0.5)

            logon_button = driver.execute_script("""
                var btn = document.getElementById('okButton');
                if (btn) return btn;
                return null;
            """)

            if logon_button:
                driver.execute_script("arguments[0].click();", logon_button)
                print("Logon clicked.")
            else:
                print("Logon button not found.")
                return False
        else:
            print(f"Role '{role_text}' not found on screen.")
            return False

        time.sleep(2)

    # ── Confirm dashboard loaded ─────────────────────────────────────────
    for attempt in range(50):
        if "MyTOMS Home" in (driver.page_source or ""):
            break
        time.sleep(0.1)

    print("Dashboard loaded.")

    # ── Verify correct role is active ────────────────────────────────────
    current_role = driver.execute_script("""
        var el = document.getElementById('selectedRoleOrg');
        return el ? el.textContent : '';
    """)

    if role_text in current_role:
        print(f"Role confirmed: {current_role.strip()}")
    else:
        print(f"Wrong role active: {current_role.strip()}")
        print(f"Switching to {role_text}...")

        role_switched = driver.execute_script("""
            var select = document.getElementById('roleOrgSelect');
            if (!select) return false;
            var options = select.querySelectorAll('option');
            for (var i = 0; i < options.length; i++) {
                if (options[i].textContent.includes(arguments[0])) {
                    select.selectedIndex = i;
                    roAction(i);
                    return true;
                }
            }
            return false;
        """, role_text)

        if role_switched:
            print("Role switched. Waiting for page to reload...")
            time.sleep(3)
            for attempt in range(50):
                if "MyTOMS Home" in (driver.page_source or ""):
                    break
                time.sleep(0.1)
            print("Dashboard reloaded.")
        else:
            print(f"Could not find '{role_text}' in role dropdown.")
            return False

    return True


def reenter_frame(driver):
    """Switch back to the main content iframe after a page load."""
    driver.switch_to.default_content()
    time.sleep(1)
    for attempt in range(50):
        if find_element(driver, '#theFrame'):
            break
        time.sleep(0.1)
    driver.switch_to.frame("theFrame")
    print("Back inside iframe.")


def toms_navigate_to_upload(driver, upload_type_value='/mt/dt/uploadaccoms.htm'):
    """Navigate from dashboard to Students > Upload > Test Settings > Next."""
    print("Looking for Students button...")
    clicked = driver.execute_script("""
        var btn = document.getElementById('menu_Students');
        if (!btn) return 'not found';
        btn.click();
        return 'clicked';
    """)
    print(f"Students button: {clicked}")
    time.sleep(1)

    print("Looking for Upload button...")
    clicked = driver.execute_script("""
        var btn = document.querySelector('button[aria-label="Upload"]');
        if (!btn) return 'not found';
        btn.click();
        return 'clicked';
    """)
    print(f"Upload button: {clicked}")
    time.sleep(1)

    reenter_frame(driver)

    print("Waiting for upload page...")
    for attempt in range(50):
        if find_element(driver, '#uploadType'):
            break
        time.sleep(0.1)

    print("Selecting Test Settings upload type...")
    selected = driver.execute_script("""
        var select = document.getElementById('uploadType');
        if (!select) return 'not found';
        select.value = arguments[0];
        select.dispatchEvent(new Event('change', { bubbles: true }));
        return 'selected';
    """, upload_type_value)
    print(f"Upload type: {selected}")
    time.sleep(1)

    print("Clicking Next...")
    driver.execute_script("""
        var btn = document.getElementById('searchStudents');
        if (btn) btn.click();
    """)
    print("Next clicked.")
    time.sleep(1)

    reenter_frame(driver)


def toms_download_template(driver, downloads_dir, template_filename):
    """Download the template file and wait for it to arrive.

    Args:
        driver: Selenium WebDriver instance
        downloads_dir: Path to downloads directory
        template_filename: Expected filename of the template

    Returns:
        Path to the downloaded template, or None if download failed
    """
    print("Clicking Download Template...")
    driver.execute_script("""
        var btn = document.getElementById('downloadTempButton');
        if (btn) btn.click();
    """)
    print("Template downloaded.")
    time.sleep(2)

    template_file = os.path.join(downloads_dir, template_filename)
    print("Waiting for template to download...")
    for attempt in range(30):
        if os.path.exists(template_file) and not os.path.exists(template_file + ".crdownload"):
            break
        time.sleep(0.5)

    if os.path.exists(template_file):
        print(f"Template saved: {template_file}")
        return template_file
    else:
        print("Template download failed.")
        return None


def toms_upload_and_submit(driver, template_file):
    """Upload the merged template and handle validation bounce.

    Args:
        driver: Selenium WebDriver instance
        template_file: Path to the merged template file

    Returns:
        'uploaded', 'errors', or 'unknown'
    """
    # ── Click Next to upload page ────────────────────────────────────────
    print("Clicking Next...")
    driver.execute_script("""
        var btn = document.getElementById('nextButton');
        if (btn) btn.click();
    """)
    print("Next clicked.")
    time.sleep(1)

    reenter_frame(driver)

    # ── Upload merged file ───────────────────────────────────────────────
    print("Uploading merged template...")
    file_input = driver.find_element("id", "uploadfilepath")
    file_input.send_keys(template_file)
    print("File selected.")
    time.sleep(1)

    # ── Click Next (submit upload) ───────────────────────────────────────
    time.sleep(2)
    print("Clicking Next to submit upload...")
    driver.execute_script("""
        var btn = document.getElementById('nextButton');
        if (btn) btn.click();
    """)
    print("Upload submitted.")
    time.sleep(2)

    reenter_frame(driver)

    # ── Wait for validation to complete ──────────────────────────────────
    print("Waiting for validation to complete...")
    upload_btn = None
    has_errors = False
    max_bounces = 5
    time.sleep(2)
    for bounce in range(max_bounces):
        upload_btn = find_element(driver, '#upload_file_btn1')
        if upload_btn:
            print(f"Upload button found after {bounce} bounce(s).")
            break

        error_status = driver.execute_script("""
            var rows = document.querySelectorAll('tr');
            for (var i = 0; i < rows.length; i++) {
                var cells = rows[i].querySelectorAll('td');
                if (cells.length > 0 && cells[0].textContent.trim() === '1') {
                    var statusCell = cells[3];
                    if (statusCell && statusCell.textContent.trim().startsWith('Errors')) {
                        return statusCell.textContent.trim();
                    }
                    if (statusCell && statusCell.textContent.trim() === 'Processing') {
                        return 'processing';
                    }
                }
            }
            return null;
        """)

        if error_status and error_status != 'processing':
            print(f"Validation returned: {error_status}")
            has_errors = True
            break

        print(f"  Bounce {bounce + 1}: refreshing validation results...")
        driver.execute_script("""
            var btn = document.getElementById('prevButton');
            if (btn) btn.click();
        """)
        time.sleep(2)
        reenter_frame(driver)

        driver.execute_script("""
            var btn = document.getElementById('nextButton');
            if (btn) btn.click();
        """)
        time.sleep(3)
        reenter_frame(driver)

    # ── Handle result ────────────────────────────────────────────────────
    if upload_btn:
        js_click(driver, upload_btn)
        print("Upload clicked. Settings submitted to TOMS.")
        time.sleep(2)
        return 'uploaded'
    elif has_errors:
        print("Errors detected — downloading error report...")
        return 'errors'
    else:
        print("Could not determine validation status — check manually.")
        return 'unknown'