# Test Settings Sync
**Python · Selenium · JavaScript · Microsoft Edge**
 
---
 
## The Problem
 
At SOAR Charter Academy, student test settings for CAASPP and ELPAC
assessments are managed in two separate systems — Aeries (our student
information system) and TOMS (the state's Test Operations Management
System). Every testing day, the settings in TOMS need to reflect what's
in Aeries. The manual process: log into Aeries, export a settings file,
log into TOMS, download a template, copy-paste the data in Excel, upload
the merged file, wait for validation, click through confirmation screens.
Then do it all again for ELPAC.
 
Two platforms, two logins, four exports, two merges, two uploads, and a
dozen clicks each — every day during testing season.
 
I built an automation to handle it. 
 
---
 
## What It Does
 
A single command runs the full sync for both CAASPP and ELPAC:
 
```
python3.12 sync_test_settings.py
```
 
The orchestrator moves through three phases:
 
**Phase 1 — Aeries Exports.** Logs into Aeries, navigates to the State
Testing Export Files page, and downloads both the CAASPP and ELPAC
settings CSVs with tomorrow's date.
 
**Phase 2 — CAASPP Upload.** Logs into TOMS as Site CAASPP Coordinator,
downloads the blank template, merges the Aeries data into it, uploads
the merged file, waits for validation, and clicks Upload to submit.
 
**Phase 3 — ELPAC Upload.** Switches to Site ELPAC Coordinator and
repeats the same process with the ELPAC data and template.
 
After each upload, the script verifies the results by spot-checking
three random students directly in the TOMS interface and downloading
the full settings report for comparison.
 
---
 
## Architecture
 
Nine files, each with a single responsibility:
 
**Orchestrator**
 
**sync_test_settings.py** — the production entry point. Runs all exports
and uploads in a single browser session, handles the downloads folder
lifecycle, archives every run, and prints a summary.
 
**Shared Helpers**
 
**browser_helpers.py** — Edge WebDriver setup with persistent profile,
plus utility functions for element finding, clicking, and React-style
input handling. Shared across this project and the
[iru-device-reset](https://github.com/jwhicks727/iru-device-reset) project.
 
**aeries_helpers.py** — login, sidebar navigation, and export download
for Aeries.
 
**toms_helpers.py** — login, role selection, iframe management, template
download, file upload, and the Previous/Next validation bounce for TOMS.
 
**merge_data.py** — pure Python, no browser. Manipulates the TOMS
template at the zip/XML level to insert Aeries data while preserving
the template's data validations, styles, and structure that openpyxl
would strip.
 
**verify_settings.py** — post-upload verification. Spot-checks random
students through the TOMS interface and compares the full settings
report against the uploaded data.
 
**Individual Scripts**
 
**caaspp_upload.py** and **elpac_upload.py** — standalone TOMS upload
scripts for running one workflow at a time.
 
**aeries_caaspp_export.py** and **aeries_elpac_export.py** — standalone
Aeries export scripts for exporting the two datasets.
 
---
 
## How I Built It
 
I used Claude as a coding partner throughout — working through problems
together, evaluating approaches, and making architectural decisions like
how to structure shared helpers across two automation projects. The
project grew from a single script into a modular system as the
complexity of the problem revealed itself.
 
**Authentication** follows the same pattern established in the Iru
project: a persistent Edge browser profile stores authenticated
sessions for both Aeries and TOMS. Subsequent runs open directly to
the dashboard. When a session expires, the script detects the login
page and clicks the Secure Logon button automatically — only pausing
for manual input when two-step verification is required.
 
**The merge problem** was the hardest part. TOMS templates are xlsx
files with data validations, multiple sheets, and shared string tables
that must remain intact for TOMS to accept the upload. Python's
openpyxl library strips the data validations on save. The solution
manipulates the xlsx as a zip archive — reading the sheet XML as a
string, inserting cell data with regex-safe string operations, and
repacking the zip with all other files untouched. The template's
structure, styles, and validations survive because the code never
parses them.
 
**The iframe pattern** in TOMS required special handling. Every page
transition inside TOMS reloads content within an iframe, which
invalidates Selenium's frame reference. A `reenter_frame()` helper
switches back to the main document and re-enters the iframe after each
navigation — called dozens of times across a single run.
 
**Kendo UI controls** in Aeries (date pickers, dropdowns) don't respond
to standard Selenium input. The solution talks directly to the Kendo
widget API through JavaScript, setting values and firing change events
the way the framework expects.
 
---
 
## Run Archives
 
Every run is archived in a timestamped folder under `runs/`:
 
```
runs/
└── 2026-05-13_08-30-00/
    ├── CAASPPTestSettings20260514.csv        # Aeries CAASPP export
    ├── ELPACTestSettings20260514.csv         # Aeries ELPAC export
    ├── CAASPP_Upload_Stu_Accom_Template.xlsx # Merged CAASPP template
    ├── CAASPP_Upload_Stu_Accom_Template_original.xlsx
    ├── ELPAC_Upload_Stu_Accom_Template.xlsx  # Merged ELPAC template
    └── ELPAC_Upload_Stu_Accom_Template_original.xlsx
```
 
Original (pre-merge) templates are preserved alongside the merged
versions for comparison. If an upload causes issues, the exact files
that were sent to TOMS are available for review.
 
---
 
## Status
 
In active development at SOAR Charter Academy. Core workflow is
functional — exports, merges, and uploads complete successfully.
Verification system is in testing. File format compatibility with TOMS
is under refinement.
 
---
 
## Completed Features
 
**✅ Single-command full sync** — one script runs both CAASPP and ELPAC
workflows end to end in a single browser session. One login to Aeries,
both exports. One login to TOMS, both uploads.
 
**✅ Test mode** — a `--test` flag runs the full pipeline (exports,
template downloads, merges) but skips the actual TOMS upload. Useful
for verifying file generation without affecting production data.
 
**✅ Role-aware TOMS navigation** — automatically selects the correct
coordinator role (CAASPP or ELPAC) and verifies the active role before
proceeding. Switches roles via the dashboard dropdown if needed.
 
**✅ Template-safe merge** — manipulates xlsx files at the zip/XML level
to preserve data validations and template structure that standard
Python libraries would strip.
 
**✅ Validation bounce** — after uploading, the script polls TOMS for
validation results by cycling Previous/Next to refresh the status.
Detects both successful validation (Upload button) and errors.
 
**✅ Run archiving** — every run is saved in a timestamped folder with
all source files and merged outputs for auditing and troubleshooting.

**✅ Report-based verification** — After each upload, automatically downloads the full School-Level Student Test Settings Report from TOMS and compares every student's settings against the uploaded data. Reports match counts, mismatches, and missing students. Runs for both CAASPP and ELPAC with format-aware column parsing.
 
**✅ Google Sheets sync** — After each upload verification, automatically pushes the full School-Level Student Test Settings Report to a shared Google Sheet via service account API. Replaces the "Raw" tab with current TOMS settings data, providing the team with an always-current reference without manual exports.

---
 
## Roadmap

**Error handling and retry** — when TOMS returns validation errors,
download the error CSV, identify affected students and settings, remove
the problematic values from the template, and re-upload automatically.
 
**2SV page detection** — detect the TOMS two-step verification page by
its elements rather than by timeout, for faster and more reliable login
handling.
 
**Report generator** — generate per-run reports logging what was
uploaded, what was verified, and any discrepancies found.
 
---
 
## Environment
 
- macOS (Sequoia)
- Python 3.12 via Homebrew
- Microsoft Edge 147+
- msedgedriver (matching Edge version)
- Selenium, openpyxl via pip3.12