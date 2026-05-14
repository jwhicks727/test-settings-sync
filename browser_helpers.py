"""Shared Selenium helper functions for browser automation projects.

Provides Edge WebDriver setup with persistent profiles, and utility
functions for interacting with React-based web applications.
"""

import os
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains

# ── Configuration ──────────────────────────────────────────────────────────────
EDGEDRIVER_PATH = "/Users/jasonhicks/Projects/msedgedriver/edgedriver_mac64/msedgedriver"


def start_driver(profile_dir):
    """Launch Edge using a persistent profile so we stay logged in between runs.

    Args:
        profile_dir: Path to the Edge profile directory for session persistence

    Returns:
        Tuple of (driver, wait) — the WebDriver instance and a WebDriverWait
    """
    # Remove lock file in case Edge is already open
    lock_file = os.path.join(profile_dir, "SingletonLock")
    if os.path.exists(lock_file):
        os.remove(lock_file)

    options = Options()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_experimental_option("prefs", {
        "download.default_directory": os.path.join(os.path.dirname(profile_dir), "downloads"),
        "download.prompt_for_download": False
    })
    options.add_experimental_option("prefs", {
        "download.default_directory": os.path.join(os.path.dirname(profile_dir), "downloads"),
        "download.prompt_for_download": False,
        "profile.default_content_setting_values.automatic_downloads": 1
    })
    options.use_chromium = True
    service = Service(EDGEDRIVER_PATH)
    driver = webdriver.Edge(service=service, options=options)
    wait = WebDriverWait(driver, 10)
    return driver, wait


def find_element(driver, selector):
    """Find a single element by CSS selector using JavaScript.

    Returns the element if found, or None if not found.
    """
    return driver.execute_script(f"return document.querySelector('{selector}')")


def js_click(driver, element):
    """Click an element using ActionChains, which simulates a real mouse movement.

    More reliable than a plain click for React components.
    """
    ActionChains(driver).move_to_element(element).click().perform()


def set_input_value(driver, element, value):
    """Type a value into a React-controlled input field.

    React manages its own internal state, so we can't just set .value directly —
    we have to use the native setter and fire an input event to notify React.
    """
    driver.execute_script("""
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        nativeInputValueSetter.call(arguments[0], arguments[1]);
        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
    """, element, value)