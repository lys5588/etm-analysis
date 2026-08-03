import os
import sys
import time
import shutil
import subprocess
import csv
import argparse
from typing import List

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
TASKS_DIR = os.path.join(os.getcwd(), "data", "tasks")
INPUT_DIR = os.path.join(REPO_ROOT, "data", "input")
OUTPUT_DIR = os.path.join(REPO_ROOT, "data", "output")
SCENARIO_SCRIPT = os.path.join(REPO_ROOT, "scenario_from_csv.py")

SCENARIO_LIST = "scenario_list.csv"
SCENARIO_SETTINGS = "scenario_settings.csv"
SCENARIO_OUTCOMES = "scenario_outcomes.csv"

RETRY_SLEEP_SECONDS = 5  # fixed delay between retries
DEFAULT_BATCH_SIZE = 1  # default number of scenarios per task


def list_task_dirs(path: str) -> List[str]:
    if not os.path.isdir(path):
        return []
    # sort by numeric folder name if possible, else lexicographic
    def sort_key(name: str):
        try:
            return (0, int(name))
        except ValueError:
            return (1, name)
    names = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]
    names.sort(key=sort_key)
    return [os.path.join(path, n) for n in names]


def assert_file_exists(path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)


def copy_file(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def clean_output_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)
        return
    for name in os.listdir(path):
        file_path = os.path.join(path, name)
        if os.path.isfile(file_path):
            os.remove(file_path)


def run_scenario_script() -> None:
    # run `python scenario_from_csv.py` in repo root
    result = subprocess.run([sys.executable, SCENARIO_SCRIPT], cwd=REPO_ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"scenario_from_csv.py failed with code {result.returncode}")


def execute_task(task_dir: str) -> None:
    # 1) copy task CSVs into data/input
    src_list = os.path.join(task_dir, SCENARIO_LIST)
    src_settings = os.path.join(task_dir, SCENARIO_SETTINGS)
    assert_file_exists(src_list)
    assert_file_exists(src_settings)
    copy_file(src_list, os.path.join(INPUT_DIR, SCENARIO_LIST))
    copy_file(src_settings, os.path.join(INPUT_DIR, SCENARIO_SETTINGS))

    # 2) run scenario_from_csv.py with infinite retries until success
    while True:
        try:
            run_scenario_script()
            out_file = os.path.join(OUTPUT_DIR, SCENARIO_OUTCOMES)
            assert_file_exists(out_file)
            break
        except Exception as e:
            print(f"Task '{os.path.basename(task_dir)}' run failed: {e}. Retrying in {RETRY_SLEEP_SECONDS}s...", flush=True)
            time.sleep(RETRY_SLEEP_SECONDS)

    # 3) copy outcomes to task dir
    copy_file(os.path.join(OUTPUT_DIR, SCENARIO_OUTCOMES), os.path.join(task_dir, SCENARIO_OUTCOMES))

    # 4) clean output files
    clean_output_dir(OUTPUT_DIR)


def split_tasks(batch_size: int, force: bool = False) -> None:
    """
    Split the original scenario_list.csv and scenario_settings.csv into smaller task batches.
    Each batch will be placed in a numbered subfolder under data/tasks.
    
    Args:
        batch_size: Number of scenarios per batch
        force: If True, delete existing tasks and re-split. If False, preserve existing results.
    """
    src_list = os.path.join(INPUT_DIR, SCENARIO_LIST)
    src_settings = os.path.join(INPUT_DIR, SCENARIO_SETTINGS)
    
    assert_file_exists(src_list)
    assert_file_exists(src_settings)
    
    # Read scenario_list.csv
    with open(src_list, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        list_header = next(reader)
        list_rows = list(reader)
    
    # Read scenario_settings.csv
    with open(src_settings, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        settings_header = next(reader)
        settings_rows = list(reader)
    
    # Get scenario names from list (first column is short_name)
    scenario_names = [row[0] for row in list_rows if row]
    total_scenarios = len(scenario_names)
    
    if total_scenarios == 0:
        print("No scenarios found in scenario_list.csv")
        return
    
    print(f"Found {total_scenarios} scenarios, splitting into batches of {batch_size}...")
    
    # Only clear existing tasks directory if force=True
    if force and os.path.isdir(TASKS_DIR):
        print("Force mode: Removing existing tasks directory...")
        shutil.rmtree(TASKS_DIR)
    os.makedirs(TASKS_DIR, exist_ok=True)
    
    # Split into batches
    num_batches = (total_scenarios + batch_size - 1) // batch_size
    created_count = 0
    skipped_count = 0
    
    for batch_idx in range(num_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, total_scenarios)
        batch_scenarios = scenario_names[start_idx:end_idx]
        
        # Create task directory
        task_dir = os.path.join(TASKS_DIR, str(batch_idx + 1))
        
        # Check if task already has results (don't overwrite)
        outcomes_file = os.path.join(task_dir, SCENARIO_OUTCOMES)
        if os.path.isfile(outcomes_file):
            skipped_count += 1
            print(f"  Task {batch_idx + 1}: Already has results, skipping...")
            continue
        
        os.makedirs(task_dir, exist_ok=True)
        
        # Filter scenario_list rows
        batch_list_rows = [row for row in list_rows if row and row[0] in batch_scenarios]
        
        # Write scenario_list.csv for this batch
        with open(os.path.join(task_dir, SCENARIO_LIST), 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(list_header)
            writer.writerows(batch_list_rows)
        
        # Filter scenario_settings columns
        # Header format: ['input', scenario1, scenario2, ...]
        # We need to keep 'input' column and only the columns for this batch
        batch_col_indices = [0]  # Always keep 'input' column
        for i, col_name in enumerate(settings_header[1:], start=1):
            if col_name in batch_scenarios:
                batch_col_indices.append(i)
        
        # Write scenario_settings.csv for this batch
        with open(os.path.join(task_dir, SCENARIO_SETTINGS), 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Write filtered header
            writer.writerow([settings_header[i] for i in batch_col_indices])
            # Write filtered rows
            for row in settings_rows:
                if row:
                    writer.writerow([row[i] if i < len(row) else '' for i in batch_col_indices])
        
        created_count += 1
        print(f"  Task {batch_idx + 1}: {len(batch_scenarios)} scenarios ({batch_scenarios[0]} to {batch_scenarios[-1]})")
    
    print(f"\nSplit complete! Total: {num_batches} batches, Created: {created_count}, Skipped (has results): {skipped_count}")


def merge_results() -> None:
    """
    Merge all scenario_outcomes.csv files from task directories into a single file.
    The merged file will be saved to data/output/scenario_outcomes_merged.csv
    """
    tasks = list_task_dirs(TASKS_DIR)
    if not tasks:
        print(f"No tasks found in {TASKS_DIR}")
        return
    
    merged_header = None
    merged_rows = []
    
    for task_dir in tasks:
        task_id = os.path.basename(task_dir)
        outcomes_file = os.path.join(task_dir, SCENARIO_OUTCOMES)
        
        if not os.path.isfile(outcomes_file):
            print(f"  Warning: Task {task_id} has no {SCENARIO_OUTCOMES}, skipping...")
            continue
        
        with open(outcomes_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)
        
        if merged_header is None:
            merged_header = header
        elif header != merged_header:
            print(f"  Warning: Task {task_id} has different header, attempting to merge anyway...")
        
        merged_rows.extend(rows)
        print(f"  Task {task_id}: {len(rows)} scenarios merged")
    
    if not merged_rows:
        print("No results to merge!")
        return
    
    # Save merged results
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    merged_file = os.path.join(OUTPUT_DIR, "scenario_outcomes_merged.csv")
    
    with open(merged_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(merged_header)
        writer.writerows(merged_rows)
    
    print(f"\nMerge complete! {len(merged_rows)} scenarios saved to {merged_file}")


def get_task_status() -> dict:
    """Get the status of all tasks."""
    tasks = list_task_dirs(TASKS_DIR)
    completed = []
    pending = []
    
    for task_dir in tasks:
        task_id = os.path.basename(task_dir)
        outcomes_file = os.path.join(task_dir, SCENARIO_OUTCOMES)
        if os.path.isfile(outcomes_file):
            completed.append(task_id)
        else:
            pending.append(task_id)
    
    return {
        'total': len(tasks),
        'completed': completed,
        'pending': pending,
    }


def show_status() -> None:
    """Display the current status of all tasks."""
    status = get_task_status()
    
    if status['total'] == 0:
        print(f"No tasks found in {TASKS_DIR}")
        return
    
    print(f"Task Status Summary:")
    print(f"  Total tasks: {status['total']}")
    print(f"  Completed: {len(status['completed'])}")
    print(f"  Pending: {len(status['pending'])}")
    
    if status['completed']:
        print(f"\n  Completed tasks: {', '.join(status['completed'][:10])}", end='')
        if len(status['completed']) > 10:
            print(f" ... and {len(status['completed']) - 10} more")
        else:
            print()
    
    if status['pending']:
        print(f"  Pending tasks: {', '.join(status['pending'][:10])}", end='')
        if len(status['pending']) > 10:
            print(f" ... and {len(status['pending']) - 10} more")
        else:
            print()
        
        # Show next task to run
        print(f"\n  Next task to run: {status['pending'][0]}")


def run_tasks() -> None:
    """Execute all tasks in the tasks directory sequentially."""
    tasks = list_task_dirs(TASKS_DIR)
    if not tasks:
        print(f"No tasks found in {TASKS_DIR}")
        return

    # Get initial status
    status = get_task_status()
    total = status['total']
    completed_before = len(status['completed'])
    
    print(f"Progress: {completed_before}/{total} tasks completed")
    
    if not status['pending']:
        print("All tasks already completed!")
        return
    
    print(f"Starting from task {status['pending'][0]}...\n")

    for task_dir in tasks:
        task_id = os.path.basename(task_dir)
        
        # Skip tasks that already have results
        outcomes_file = os.path.join(task_dir, SCENARIO_OUTCOMES)
        if os.path.isfile(outcomes_file):
            continue
        
        # Get current progress
        current_status = get_task_status()
        completed_now = len(current_status['completed'])
        
        print(f"[{completed_now + 1}/{total}] Starting task {task_id}...", flush=True)
        try:
            execute_task(task_dir)
            print(f"[{completed_now + 1}/{total}] Task {task_id} completed.", flush=True)
        except Exception as e:
            print(f"[{completed_now + 1}/{total}] Task {task_id} encountered a fatal error: {e}", file=sys.stderr)
            print("You can re-run the script to continue from this task.", file=sys.stderr)
            break
    
    # Final status
    final_status = get_task_status()
    print(f"\nFinal progress: {len(final_status['completed'])}/{total} tasks completed")


def main() -> None:
    parser = argparse.ArgumentParser(description='Split, run, and merge scenario tasks')
    parser.add_argument('--split', action='store_true', help='Split input files into task batches (preserves existing results)')
    parser.add_argument('--force-split', action='store_true', help='Force re-split, removing all existing tasks and results')
    parser.add_argument('--run', action='store_true', help='Run all pending tasks sequentially')
    parser.add_argument('--merge', action='store_true', help='Merge all task results')
    parser.add_argument('--all', action='store_true', help='Run split, run, and merge in sequence')
    parser.add_argument('--status', action='store_true', help='Show current task status')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE, 
                        help=f'Number of scenarios per batch (default: {DEFAULT_BATCH_SIZE})')
    
    args = parser.parse_args()
    
    # Handle --status separately
    if args.status:
        print("=== Task Status ===")
        show_status()
        return
    
    # Default to --all if no action specified
    if not any([args.split, args.force_split, args.run, args.merge, args.all]):
        args.all = True
    
    if args.force_split:
        print("=== Force Splitting tasks ===")
        split_tasks(args.batch_size, force=True)
    elif args.split or args.all:
        print("=== Splitting tasks (preserving existing results) ===")
        split_tasks(args.batch_size, force=False)
    
    if args.run or args.all:
        print("\n=== Running tasks ===")
        run_tasks()
    
    if args.merge or args.all:
        print("\n=== Merging results ===")
        merge_results()


if __name__ == "__main__":
    main()
