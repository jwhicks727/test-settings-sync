"""Track changes between runs and maintain a cumulative changelog.

Compares the current Aeries export against the previous run to detect
new settings, removed settings, and new/removed students. Records all
changes in a persistent changelog file.
"""

import csv
import json
import os
import glob
from datetime import datetime


CHANGELOG_FILE = "/Users/jasonhicks/Projects/test-settings-sync/changelog.json"


def read_settings_from_csv(csv_path):
    """Read an Aeries CSV into a dict of SSID -> set of setting codes.

    Args:
        csv_path: Path to Aeries export CSV

    Returns:
        Dict mapping SSID strings to sets of setting code strings
    """
    students = {}
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row in reader:
            ssid = row[0].strip()
            if not ssid:
                continue
            settings = set()
            for val in row[1:]:
                val = val.strip()
                if val:
                    settings.add(val)
            students[ssid] = settings
    return students


def diff_runs(current_csv, program):
    """Compare current export against the most recent previous run.

    Args:
        current_csv: Path to the current Aeries export CSV
        program: 'CAASPP' or 'ELPAC'

    Returns:
        Dict with changes, or None if no previous run found
    """
    # Find the previous run's CSV
    prefix = 'CAASPPTestSettings' if program == 'CAASPP' else 'ELPACTestSettings'
    current_dir = os.path.dirname(current_csv)

    # Look through run archives for the most recent previous CSV
    run_dirs = sorted(glob.glob('runs/*/'), reverse=True)
    prev_csv = None
    for run_dir in run_dirs:
        candidates = glob.glob(os.path.join(run_dir, f'{prefix}*.csv'))
        if candidates:
            candidate = candidates[0]
            # Make sure it's not from the current run
            if os.path.abspath(candidate) != os.path.abspath(current_csv):
                prev_csv = candidate
                break

    if not prev_csv:
        print(f"  No previous {program} run found for comparison.")
        return None

    print(f"  Comparing against: {prev_csv}")

    current = read_settings_from_csv(current_csv)
    previous = read_settings_from_csv(prev_csv)

    changes = {
        'program': program,
        'previous_file': prev_csv,
        'current_file': current_csv,
        'new_students': [],
        'removed_students': [],
        'settings_added': [],    # (ssid, setting)
        'settings_removed': [],  # (ssid, setting)
    }

    # New students (in current but not previous)
    for ssid in current:
        if ssid not in previous:
            changes['new_students'].append(ssid)
            for setting in current[ssid]:
                changes['settings_added'].append((ssid, setting))

    # Removed students (in previous but not current)
    for ssid in previous:
        if ssid not in current:
            changes['removed_students'].append(ssid)
            for setting in previous[ssid]:
                changes['settings_removed'].append((ssid, setting))

    # Changed settings for existing students
    for ssid in current:
        if ssid in previous:
            added = current[ssid] - previous[ssid]
            removed = previous[ssid] - current[ssid]
            for setting in added:
                changes['settings_added'].append((ssid, setting))
            for setting in removed:
                changes['settings_removed'].append((ssid, setting))

    # Summary
    print(f"  {program} changes since last run:")
    print(f"    New students:      {len(changes['new_students'])}")
    print(f"    Removed students:  {len(changes['removed_students'])}")
    print(f"    Settings added:    {len(changes['settings_added'])}")
    print(f"    Settings removed:  {len(changes['settings_removed'])}")

    return changes


def update_changelog(changes):
    """Append changes to the persistent changelog file.

    Only records new settings and removed settings — not unchanged ones.

    Args:
        changes: Dict from diff_runs()
    """
    if not changes:
        return

    # Load existing changelog
    if os.path.exists(CHANGELOG_FILE):
        with open(CHANGELOG_FILE, 'r') as f:
            changelog = json.load(f)
    else:
        changelog = []

    timestamp = datetime.now().isoformat()
    program = changes['program']

    # Record each change
    for ssid, setting in changes['settings_added']:
        changelog.append({
            'timestamp': timestamp,
            'program': program,
            'ssid': ssid,
            'setting': setting,
            'action': 'added'
        })

    for ssid, setting in changes['settings_removed']:
        changelog.append({
            'timestamp': timestamp,
            'program': program,
            'ssid': ssid,
            'setting': setting,
            'action': 'removed'
        })

    for ssid in changes['new_students']:
        changelog.append({
            'timestamp': timestamp,
            'program': program,
            'ssid': ssid,
            'setting': None,
            'action': 'student_added'
        })

    for ssid in changes['removed_students']:
        changelog.append({
            'timestamp': timestamp,
            'program': program,
            'ssid': ssid,
            'setting': None,
            'action': 'student_removed'
        })

    # Save
    with open(CHANGELOG_FILE, 'w') as f:
        json.dump(changelog, f, indent=2)

    total_new = len(changes['settings_added']) + len(changes['new_students'])
    total_removed = len(changes['settings_removed']) + len(changes['removed_students'])
    print(f"  Changelog updated: {total_new} additions, {total_removed} removals recorded.")


def format_changes_for_report(changes):
    """Format changes into readable text for the email/report.

    Args:
        changes: Dict from diff_runs()

    Returns:
        String with formatted changes, or None if no changes
    """

    lines = []

    # Extract previous run timestamp from path (e.g. "runs/2026-05-18_07-55-28/...")
    prev_run_dir = os.path.basename(os.path.dirname(changes['previous_file']))
    prev_display = prev_run_dir.replace("_", " ", 1).replace("-", "/", 2).replace("/", "-", 2)

    if not changes:
        return None

    if (not changes['new_students'] and not changes['removed_students']
            and not changes['settings_added'] and not changes['settings_removed']):
        return f"  No changes since {prev_display}."

    lines = []

    if changes['new_students']:
        lines.append(f"  New students ({len(changes['new_students'])}):")
        for ssid in changes['new_students'][:10]:
            # Show the student's settings
            student_settings = [s for sid, s in changes['settings_added'] if sid == ssid]
            if student_settings:
                lines.append(f"    + {ssid}: {', '.join(student_settings)}")
            else:
                lines.append(f"    + {ssid}")
        if len(changes['new_students']) > 10:
            lines.append(f"    ... and {len(changes['new_students']) - 10} more")

    if changes['removed_students']:
        lines.append(f"  Removed students ({len(changes['removed_students'])}):")
        for ssid in changes['removed_students'][:10]:
            lines.append(f"    - {ssid}")
        if len(changes['removed_students']) > 10:
            lines.append(f"    ... and {len(changes['removed_students']) - 10} more")

    # Group setting changes by student
    if changes['settings_added']:
        lines.append(f"  Settings added since {prev_display} ({len(changes['settings_added'])}):")
        by_student = {}
        for ssid, setting in changes['settings_added']:
            if ssid not in changes['new_students']:  # Skip new students, already listed
                by_student.setdefault(ssid, []).append(setting)
        for ssid, settings in list(by_student.items())[:10]:
            lines.append(f"    {ssid}: +{', '.join(settings)}")
        remaining = len(by_student) - 10
        if remaining > 0:
            lines.append(f"    ... and {remaining} more students")

    if changes['settings_removed']:
        lines.append(f"  Settings removed since {prev_display} ({len(changes['settings_removed'])}):")
        by_student = {}
        for ssid, setting in changes['settings_removed']:
            if ssid not in changes['removed_students']:
                by_student.setdefault(ssid, []).append(setting)
        for ssid, settings in list(by_student.items())[:10]:
            lines.append(f"    {ssid}: -{', '.join(settings)}")
        remaining = len(by_student) - 10
        if remaining > 0:
            lines.append(f"    ... and {remaining} more students")

    return "\n".join(lines)