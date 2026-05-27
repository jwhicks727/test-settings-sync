#!/bin/bash
# Create GitHub labels and issues for test-settings-sync roadmap
# Run from the test-settings-sync repo directory after `gh auth login`

set -e

# ── Create labels ──────────────────────────────────────────────────────
echo "Creating labels..."
gh label create "bug" --color "d73a4a" --description "Something isn't working" --force
gh label create "enhancement" --color "a2eeef" --description "New feature or improvement" --force
gh label create "refactor" --color "fbca04" --description "Code reorganization, no behavior change" --force
gh label create "investigation" --color "5319e7" --description "Needs research before action" --force
gh label create "data-quality" --color "0e8a16" --description "Data integrity or hygiene issue" --force
gh label create "low-priority" --color "ededed" --description "Nice to have, not urgent" --force

# ── Bugs ───────────────────────────────────────────────────────────────
echo "Creating bug issues..."

gh issue create \
  --title "Email report only shows first 5 mismatches" \
  --label "bug" \
  --body "In report_generator.py, both CAASPP and ELPAC sections cap at \`details[:5]\` when listing mismatches. When verification finds many issues, stakeholders see only a sample. Should show all mismatches, or at least cap at a much higher number (50+) with a 'and N more' summary."

gh issue create \
  --title "SEIS import sometimes doesn't persist to STS table" \
  --label "bug,investigation" \
  --body "On 2026-05-26, Phase 0 reported 'imported 15 new settings' but Phase 1's subsequent Aeries CAASPP export did not include them. The previous standalone import of 118 settings did persist. Possible causes: timing issue with 3-second sleep after Import click, missing confirmation step, or Aeries silently dropping rows that don't meet some criteria. Investigate by reviewing Import History in Aeries after a fresh orchestrator run."

gh issue create \
  --title "Aeries STS export concatenates duplicate setting codes" \
  --label "bug,data-quality" \
  --body "When a student has multiple STS rows mapping to the same TOMS template column, the Aeries CAASPP export joins the values into one cell with no separator (e.g. \`TDS_TTS_Stim&TDS_TTS_ItemTDS_TTS_ALL\`). This breaks the TOMS upload and verification. Root cause is duplicate STS entries from previous failed imports. Fix path: detect concatenated codes during merge or transform, prefer the most-comprehensive code, or de-duplicate at the STS level."

gh issue create \
  --title "filter_csv_for_errors removes entire row on column mismatch" \
  --label "bug" \
  --body "When TOMS error CSV uses regular hyphens (\`-\`) in column names but the template header uses en-dashes (\`–\`), the column match fails and the filter falls through to row deletion. A student loses ALL their settings instead of just the one invalid value. Partially mitigated by adding dash normalization, but should be tested with a forced error scenario. See sync_test_settings.py filter_csv_for_errors()."

# ── Data quality / cleanup ────────────────────────────────────────────
echo "Creating data quality issues..."

gh issue create \
  --title "Clean up 327 inert STS rows from failed early imports" \
  --label "data-quality,low-priority" \
  --body "Early SEIS-to-Aeries import attempts (2026-05-26 morning) inserted TOMS-format codes with no dates into the STS table. They're inert (no effect on exports or student views) but pollute queries and reports. Can be identified by: code containing underscore (\`_\`) or missing start date. ~327 rows across affected students."

gh issue create \
  --title "Clean up duplicate STS entries for 4 error students" \
  --label "data-quality" \
  --body "Students 3565037665, 4059976353, 8584925848, and 8908060768 have duplicate STS entries from today's testing that cause the concatenation bug above. Manual cleanup needed to remove the duplicate rows so each student has only one entry per setting type. Verify in Aeries Test Settings UI after cleanup."

# ── Enhancements ──────────────────────────────────────────────────────
echo "Creating enhancement issues..."

gh issue create \
  --title "Move email recipient list to config file" \
  --label "enhancement" \
  --body "report_generator.py currently hardcodes RECIPIENTS as a Python list. Move to a separate config (config.py or recipients.json) so adding/removing stakeholders doesn't require editing code. Same for CREDENTIALS_FILE and SENDER_EMAIL paths."

gh issue create \
  --title "Remove manual Enter pause before Aeries Import click" \
  --label "enhancement" \
  --body "aeries_import.py currently has an \`input('Press Enter to click Import...')\` before clicking. This was added for debugging and should be removed. With dry_run=False in production runs, the orchestrator should never pause."

gh issue create \
  --title "Skip Aeries re-login in Phase 1 when Phase 0 already logged in" \
  --label "enhancement" \
  --body "When Phase 0 (SEIS import) runs, it logs into Aeries to do the import. Phase 1 then navigates to AERIES_URL again and re-runs aeries_login(). The session is already active so this is redundant. Detect existing session and skip the re-login. Saves ~10 seconds per run."

gh issue create \
  --title "Force upload when verification finds mismatches even with no Aeries changes" \
  --label "enhancement" \
  --body "Current skip-upload logic compares Aeries→Aeries (current export vs last run's archive). If Aeries didn't change but TOMS is missing data, the skip prevents recovery. Better behavior: after verification, if mismatches are found and they're not in the Aeries data, force a CAASPP/ELPAC upload to push the stranded data."

gh issue create \
  --title "Show all mismatches in email report, not just first 5" \
  --label "enhancement" \
  --body "Companion to the 'first 5 mismatches' bug. Once we lift the cap, format the report to be readable even with 30+ mismatches — grouped by error type, perhaps with collapsible sections in the PDF version."

gh issue create \
  --title "Wire errors_removed lists into email/PDF report output" \
  --label "enhancement" \
  --body "generate_report() now accepts caaspp_errors_removed and elpac_errors_removed parameters but they're not used in the output yet. Add a 'TOMS errors corrected' section showing what settings were filtered out and why."

gh issue create \
  --title "Raise UI re-check mismatch threshold from 10 to ~50" \
  --label "enhancement" \
  --body "verify_via_report bails on UI re-check when mismatches > 10. The threshold was set when we thought most mismatches were code-mapping issues. Real experience shows most are report-incompleteness artifacts that the UI check can resolve. Raise threshold to ~50 and accept that the UI check is slow but accurate."

gh issue create \
  --title "Take union of multiple TOMS report downloads instead of best-of" \
  --label "enhancement,investigation" \
  --body "Current retry-the-report logic downloads up to 3 reports and uses the one with the most matches. Better: take the union of TOMS settings across all reports per student. If a setting appears in ANY of the downloads, count it as present. Would eliminate most form.submit() incompleteness false positives."

gh issue create \
  --title "TOMS form.submit() report download is unreliable — investigate root cause" \
  --label "investigation" \
  --body "The CAASPP/ELPAC settings report downloads via form.submit() are inconsistent. Sometimes a student is entirely missing, sometimes individual settings are dropped, sometimes the entire report shows wrong data (today's ELPAC run downloaded a Summative ELPAC report instead of the test settings report). Investigate what validateReports() does that we're bypassing — there may be a hidden field or query parameter that controls report content."

gh issue create \
  --title "Detect TOMS 2SV page by elements rather than timeout" \
  --label "enhancement" \
  --body "toms_login() currently waits up to 10 seconds for either role selection or dashboard before assuming 2SV. Detect 2SV page directly by looking for its specific elements so login is faster and more reliable."

# ── Refactoring ───────────────────────────────────────────────────────
echo "Creating refactor issues..."

gh issue create \
  --title "Refactor verify_settings.py (700+ lines) into smaller modules" \
  --label "refactor" \
  --body "verify_settings.py has grown to over 700 lines. Suggested split: keep report comparison and orchestration in verify_settings.py, move UI navigation and scraping functions (navigate_to_student, get_student_settings_from_toms, verify_student_via_ui) into a new toms_student.py module."

gh issue create \
  --title "Migrate from flat file structure to helpers/ package" \
  --label "refactor,low-priority" \
  --body "Project is up to 15+ Python files at the top level. Move all helper modules (browser_helpers, aeries_helpers, toms_helpers, merge_data, verify_settings, change_tracker, sheets_upload, report_generator) into a helpers/ package. Keep runnable scripts (sync_test_settings, aeries_import, seis_export) at top level. Update all imports. Test with a full live run before committing."

echo
echo "Done. View at: https://github.com/jwhicks727/test-settings-sync/issues"
