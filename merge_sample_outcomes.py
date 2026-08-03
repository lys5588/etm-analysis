"""
Merge all scenario_outcomes.csv files from task directories into a single CSV.

This script:
1. Reads all scenario_outcomes.csv files from data/tasks/{n}/ folders
2. Extracts columns matching the pattern 'sample_{k}'
3. Merges them horizontally in folder order (sorted numerically)
4. Outputs: [label column] + [all sample columns in order] + [unit column from last file]
"""

import os
import re
import csv
from typing import List, Tuple, Dict

TASKS_DIR = os.path.join(os.getcwd(), "data", "tasks")
OUTPUT_DIR = os.path.join(os.getcwd(), "data", "output")
OUTPUT_FILE = "sample_outcomes_merged.csv"
SCENARIO_OUTCOMES = "scenario_outcomes.csv"

# Pattern to match sample_{k} column names
SAMPLE_PATTERN = re.compile(r'^sample_\d+$')


def list_task_dirs(path: str) -> List[str]:
    """List all task directories sorted numerically."""
    if not os.path.isdir(path):
        return []
    
    def sort_key(name: str):
        try:
            return (0, int(name))
        except ValueError:
            return (1, name)
    
    names = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]
    names.sort(key=sort_key)
    return [os.path.join(path, n) for n in names]


def read_csv_data(file_path: str) -> Tuple[List[str], List[List[str]]]:
    """Read CSV file and return header and rows."""
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    return header, rows


def find_sample_columns(header: List[str]) -> List[int]:
    """Find indices of columns matching sample_{k} pattern."""
    indices = []
    for i, col_name in enumerate(header):
        if SAMPLE_PATTERN.match(col_name):
            indices.append(i)
    return indices


def merge_sample_outcomes():
    """Main function to merge all sample outcomes."""
    task_dirs = list_task_dirs(TASKS_DIR)
    
    if not task_dirs:
        print(f"No task directories found in {TASKS_DIR}")
        return
    
    print(f"Found {len(task_dirs)} task directories")
    
    # Data structures for merging
    first_file_label_col = None  # Labels from first file (column 0)
    sample_columns = []  # List of (col_name, col_data) tuples
    last_file_unit_col = None  # Unit column from last file
    last_file_header = None
    
    processed_count = 0
    skipped_count = 0
    
    for task_dir in task_dirs:
        task_id = os.path.basename(task_dir)
        outcomes_file = os.path.join(task_dir, SCENARIO_OUTCOMES)
        
        if not os.path.isfile(outcomes_file):
            skipped_count += 1
            print(f"  Task {task_id}: No {SCENARIO_OUTCOMES}, skipping...")
            continue
        
        header, rows = read_csv_data(outcomes_file)
        
        # Find sample columns
        sample_indices = find_sample_columns(header)
        
        if not sample_indices:
            skipped_count += 1
            print(f"  Task {task_id}: No sample_{{k}} columns found, skipping...")
            continue
        
        # Store first file's label column
        if first_file_label_col is None:
            first_file_label_col = [row[0] if row else '' for row in rows]
            # Also store header for first column
            first_col_header = header[0]
        
        # Extract sample columns data
        for idx in sample_indices:
            col_name = header[idx]
            col_data = [row[idx] if idx < len(row) else '' for row in rows]
            sample_columns.append((col_name, col_data))
        
        # Always update last file's unit column (last column)
        last_col_idx = len(header) - 1
        last_file_unit_col = [row[last_col_idx] if last_col_idx < len(row) else '' for row in rows]
        last_file_header = header
        
        processed_count += 1
        if processed_count % 100 == 0:
            print(f"  Processed {processed_count} task directories...")
    
    if not sample_columns:
        print("No sample data found to merge!")
        return
    
    print(f"\nProcessed: {processed_count}, Skipped: {skipped_count}")
    print(f"Total sample columns collected: {len(sample_columns)}")
    
    # Build merged data
    # Header: [first_col_header] + [sample_0, sample_1, ...] + [unit]
    merged_header = [first_col_header]
    for col_name, _ in sample_columns:
        merged_header.append(col_name)
    merged_header.append(last_file_header[-1])  # 'unit'
    
    # Rows: [label] + [sample values...] + [unit]
    num_rows = len(first_file_label_col)
    merged_rows = []
    
    for i in range(num_rows):
        row = [first_file_label_col[i]]
        for _, col_data in sample_columns:
            row.append(col_data[i] if i < len(col_data) else '')
        row.append(last_file_unit_col[i] if i < len(last_file_unit_col) else '')
        merged_rows.append(row)
    
    # Write output
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(merged_header)
        writer.writerows(merged_rows)
    
    print(f"\nMerge complete!")
    print(f"  Output file: {output_path}")
    print(f"  Rows: {len(merged_rows)}")
    print(f"  Columns: {len(merged_header)} (1 label + {len(sample_columns)} samples + 1 unit)")


if __name__ == "__main__":
    merge_sample_outcomes()
