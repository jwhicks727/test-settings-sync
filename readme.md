# test-settings-sync

Automated daily sync of student test settings between three systems: **SEIS** (special education plans), **Aeries** (student information system), and **TOMS** (California's statewide testing platform). Eliminates a multi-hour weekly manual data entry workflow for CAASPP and ELPAC test administration.

## What It Does

```
SEIS  ──►  Aeries STS table  ──►  Aeries CAASPP/ELPAC export  ──►  TOMS
(IEP)      (source of truth)      (translated to TOMS codes)        (assessment system)
```

Each weekday morning the script:

1. **Phase 0:** Downloads the latest TOMS Summative Assessments report from SEIS, transforms it from TOMS codes to Aeries codes via a learned mapping, and imports new settings into Aeries' STS table
2. **Phase 1:** Downloads the current CAASPP and ELPAC test settings exports from Aeries
3. **Phase 2:** Uploads CAASPP settings to TOMS as Site CAASPP Coordinator. Automatically catches and corrects TOMS validation errors, retrying the upload with a filtered file
4. **Phase 3:** Uploads ELPAC settings to TOMS as Site ELPAC Coordinator with the same error-handling pattern

After each upload, the script:

- Downloads the corresponding TOMS report and verifies every student's settings match what was uploaded
- Re-downloads the TOMS report if many mismatches are detected (TOMS reports are sometimes incomplete)
- Falls back to per-student UI verification for remaining mismatches
- Pushes the CAASPP report to a Google Sheet for stakeholder visibility
- Archives every file from the run for audit
- Emails a PDF and text summary to stakeholders

## Architecture

Single-process Python application using a persistent Selenium-controlled Edge browser session to drive Aeries, SEIS, and TOMS web UIs. No backend, no database, no scheduling daemon — the script is run on demand from the terminal.

### File Structure

```
test-settings-sync/
├── sync_test_settings.py        # Orchestrator — entry point for all runs
├── browser_helpers.py           # Edge WebDriver setup, element finders, JS clicks
├── aeries_helpers.py            # Aeries login + state testing export navigation
├── aeries_import.py             # Aeries Import Data flow for SEIS → STS
├── seis_export.py               # SEIS report download
├── seis_transform.py            # TOMS-format → Aeries-format conversion
├── toms_helpers.py              # TOMS login, navigation, upload, error download
├── merge_data.py                # Zip-level XML manipulation of TOMS templates
├── verify_settings.py           # Report comparison + UI fallback verification
├── change_tracker.py            # Diff between runs, cumulative changelog
├── sheets_upload.py             # Google Sheets export of CAASPP report
├── report_generator.py          # PDF and email report generation
├── code_mapping.json            # TOMS code ↔ Aeries code lookup table
└── runs/                        # Per-run archives (timestamped folders)
```

### Why Zip-Level XML Manipulation?

The TOMS upload template uses Excel data validations that openpyxl strips on write. Writing the template requires manipulating `xl/worksheets/sheet4.xml` and `xl/sharedStrings.xml` directly inside the .xlsx zip archive while preserving the rest of the workbook untouched.

### Code Mapping

Aeries internally uses codes like `EA.TTS.S` and translates them to TOMS codes like `TDS_TTS_Stim` during export. The reverse mapping is needed when importing SEIS (which uses TOMS codes) into Aeries' STS table (which uses Aeries codes). The mapping in `code_mapping.json` was derived from co-occurrence analysis of an STS table dump against a CAASPP export.

## Run

```bash
python3.12 sync_test_settings.py            # Full live run
python3.12 sync_test_settings.py --test     # Skip TOMS uploads (still merges, verifies, reports)
```

## Requirements

- macOS / Linux
- Python 3.12
- Microsoft Edge + msedgedriver (configured path in `browser_helpers.py`)
- Edge profile with saved credentials for Aeries, SEIS, and TOMS at `edge-profile/`
- Google service account at `credentials.json` with domain-wide delegation (Gmail send + Sheets edit scopes)

Python dependencies: `selenium`, `openpyxl`, `weasyprint`, `gspread`, `google-api-python-client`, `google-auth`

## Known Limitations

- **TOMS report incompleteness** — TOMS's School-Level Student Test Settings Report intermittently omits students or settings when downloaded via `form.submit()`. Mitigated by automatic report re-download and per-student UI verification fallback
- **Two-factor authentication** — TOMS occasionally requires 2SV. The script pauses for manual completion when detected
- **Single school** — Hard-coded to SOAR Charter Academy's school ID; would need refactoring for multi-site use

## Maintenance Notes

- After every run, files are archived to `runs/<timestamp>/`. Old runs accumulate — periodic cleanup is fine but the changelog uses recent runs for diff comparison
- `code_mapping.json` covers known Aeries↔TOMS pairs. New codes that appear in SEIS but aren't yet in the mapping are flagged in the run output for manual addition
- `changelog.json` is cumulative and may grow large over time

## License

Internal tool. Not licensed for redistribution.