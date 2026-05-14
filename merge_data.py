"""Merge Aeries export data into a TOMS template file.

Works for both CAASPP and ELPAC — same structure, different files.
Manipulates the xlsx as a zip, inserting data into the correct sheet
and registering text values in the shared strings table.
"""

import csv
import zipfile
import shutil
import os
import re


def merge(template_path, aeries_csv_path, output_path=None, sheet_xml_path='xl/worksheets/sheet4.xml'):
    if output_path is None:
        output_path = template_path

    # Read Aeries CSV
    print(f"Reading Aeries export: {aeries_csv_path}")
    rows = []
    with open(aeries_csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append(row)
    print(f"  {len(rows)} student rows found.")

    # Build column letters (A, B, C, ... Z, AA, AB, ...)
    def col_letter(col_index):
        result = ''
        while col_index >= 0:
            result = chr(65 + (col_index % 26)) + result
            col_index = col_index // 26 - 1
        return result

    # Figure out dimensions
    max_cols = max(len(row) for row in rows) if rows else 1
    last_col = col_letter(max_cols - 1)
    last_row = len(rows) + 1

    # Work on a copy
    temp_path = template_path.replace('.xlsx', '_temp.xlsx')
    shutil.copy2(template_path, temp_path)

    # Save a pre-merge copy for auditing
    backup_path = template_path.replace('.xlsx', '_original.xlsx')
    shutil.copy2(template_path, backup_path)

    # Read sheet XML and shared strings from the template
    with zipfile.ZipFile(temp_path, 'r') as zin:
        sheet_xml = zin.read(sheet_xml_path).decode('utf-8')
        shared_strings_xml = zin.read('xl/sharedStrings.xml').decode('utf-8')
        all_files = zin.namelist()

    # ── Count existing shared strings by counting </si> tags ─────────────
    existing_count = shared_strings_xml.count('</si>')
    next_index = existing_count
    print(f"  Template has {existing_count} existing shared strings.")

    # ── Collect unique new strings and assign indices ─────────────────────
    # Map each unique text value to a shared string index
    new_string_map = {}  # escaped_value -> index
    new_string_list = []  # ordered list of escaped values to append

    for row_data in rows:
        for value in row_data:
            value = value.strip()
            if not value:
                continue
            # Skip numbers — they don't go in shared strings
            try:
                float(value)
                continue
            except ValueError:
                pass
            # Escape for XML
            escaped = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            if escaped not in new_string_map:
                new_string_map[escaped] = next_index
                new_string_list.append(escaped)
                next_index += 1

    print(f"  {len(new_string_list)} new unique strings to register.")

    # ── Append new strings to the shared strings table ───────────────────
    if new_string_list:
        new_si_entries = ''.join(f'<si><t>{s}</t></si>' for s in new_string_list)
        shared_strings_xml = shared_strings_xml.replace('</sst>', new_si_entries + '</sst>')

        # Update count and uniqueCount to reflect total <si> entries
        total_si = existing_count + len(new_string_list)
        # Replace count="..." and uniqueCount="..." in the <sst> tag
        shared_strings_xml = re.sub(
            r'count="\d+"',
            f'count="{total_si}"',
            shared_strings_xml,
            count=1
        )
        shared_strings_xml = re.sub(
            r'uniqueCount="\d+"',
            f'uniqueCount="{total_si}"',
            shared_strings_xml,
            count=1
        )

    # ── Build row XML using shared string references ─────────────────────
    row_xml_parts = []
    for i, row_data in enumerate(rows):
        row_num = i + 2  # Data starts at row 2 (row 1 is header)
        cells_xml = []

        # Pad row to match template width
        padded_row = row_data + [''] * (max_cols - len(row_data))
        for j, value in enumerate(padded_row):
            value = value.strip()
            cell_ref = f"{col_letter(j)}{row_num}"

            if not value:
                # Empty cell — still include it for TOMS compatibility
                cells_xml.append(f'<c r="{cell_ref}"/>')
            else:
                try:
                    float(value)
                    # Number — store directly
                    cells_xml.append(f'<c r="{cell_ref}"><v>{value}</v></c>')
                except ValueError:
                    # Text — reference the shared string by index
                    escaped = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    idx = new_string_map[escaped]
                    cells_xml.append(f'<c r="{cell_ref}" t="s"><v>{idx}</v></c>')

        row_xml_parts.append(f'<row r="{row_num}">{"".join(cells_xml)}</row>')

    rows_xml = "".join(row_xml_parts)

    # ── Update sheet XML ─────────────────────────────────────────────────
    # Remove existing rows 2+ (keep only row 1 header)
    sheet_xml = re.sub(r'<row r="[2-9]"[^>]*>.*?</row>', '', sheet_xml, flags=re.DOTALL)
    sheet_xml = re.sub(r'<row r="[1-9]\d+"[^>]*>.*?</row>', '', sheet_xml, flags=re.DOTALL)

    # Update dimension ref — keep at least as wide as the original
    dim_match = re.search(r'<dimension ref="[A-Z]+1:([A-Z]+)\d+"', sheet_xml)
    if dim_match:
        original_last_col = dim_match.group(1)
        if len(last_col) < len(original_last_col) or (len(last_col) == len(original_last_col) and last_col < original_last_col):
            last_col = original_last_col

    sheet_xml = re.sub(
        r'<dimension ref="[^"]*"/>',
        f'<dimension ref="A1:{last_col}{last_row}"/>',
        sheet_xml
    )

    # Insert rows before </sheetData>
    sheet_xml = sheet_xml.replace('</sheetData>', rows_xml + '</sheetData>')

    # ── Repack the zip ───────────────────────────────────────────────────
    with zipfile.ZipFile(output_path, 'w') as zout:
        with zipfile.ZipFile(temp_path, 'r') as zin:
            for item in all_files:
                info = zin.getinfo(item)
                if item == sheet_xml_path:
                    zout.writestr(info, sheet_xml.encode('utf-8'))
                elif item == 'xl/sharedStrings.xml':
                    zout.writestr(info, shared_strings_xml.encode('utf-8'))
                else:
                    zout.writestr(info, zin.read(item))

    os.remove(temp_path)
    print(f"Merged file saved: {output_path}")
    print(f"  {len(rows)} rows written, {len(new_string_list)} new strings registered.")

    return output_path