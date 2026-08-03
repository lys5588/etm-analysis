# ETM Data Sampling and Collection Guide

This directory is a standalone package for ETM Morris sampling and API data collection. Run every command from this directory—the directory containing `whole_process.py`—because the code relies on relative paths. Do not start the scripts from the parent directory.

## 1. Environment setup

Python 3.9–3.11 is recommended. The original dependencies pin `pyyaml==6.0`, which may need to be built from source and fail to install on Python 3.12. Install the dependencies with:

```bash
python -m pip install -r requirements.txt
```

Before making real ETM requests, copy `config/local.settings.yml.example` to `config/local.settings.yml` and enter your personal ETM token. Do not share or commit `local.settings.yml`.

By default, the program uses the ETM production API. The area, end year, and base scenario ID are currently hard-coded in `generate_input_addup.py` as `UK_united_kingdom`, `2020`, and `1362080`. If you are running a different project, ask the maintainer to confirm these values first.

## 2. Initial input files

### Main variable definition

`variable_data.csv`

This is the main input for the complete workflow. It defines the variables to sample, their minimum and maximum values, Euclidean Independent variables, Equivalent variables, Simplex/SYNsimplex groups, fixed values, and Synthetic control elements.

Simplex grouping depends on the row order in this CSV. Do not sort or reorder the rows without checking the grouping logic.

### Parent-child constraints

`synthetic_refer.csv`

This file defines the relationships between Synthetic control variables and their child variables. During post-processing, a child value is capped so that it does not exceed its parent value.

### ETM mappings and query configuration

- `query/database_index.csv`: maps numeric variable IDs to ETM API `database_item` names.
- `query/all_var_real.csv`: the ETM variable reference table included with the package. The current function interface retains this path, but the actual mapping is performed with `database_index.csv`.
- `data/input/queries.csv`: lists the ETM gqueries requested for every sample.
- `data/input/data_downloads.csv`: defines the downloads requested for every sample. It currently requests `energy_flow` and `merit_order`.
- `data/input/heat_network_orders.csv`: optional configuration used by the scenario tools.

## 3. Complete workflow

### Step 1: Generate the Morris design and within-group ratios

```bash
python whole_process.py --save_ratio_sampling
```

Input:

- `variable_data.csv`

Outputs:

- `morris_sampling_design_ratios.csv`: the 0–1 ratio sampling design used by the next step.
- `morris_sampling_design.csv`: the sampling design after range and variable-relation transformations; mainly used for verification.

With the included `variable_data.csv`, the expected result is 226 sampling dimensions and 1,362 samples. These numbers may change if the variable definitions are modified.

Always include `--save_ratio_sampling`. Without it, the downstream ratio file is not regenerated and a stale file may be used.

### Step 2: Generate `param_encoding`

```bash
python data_transform.py
```

Inputs:

- `morris_sampling_design_ratios.csv`
- `variable_data.csv`
- `synthetic_refer.csv`

This step converts ratios to actual variable values, transposes the design to “rows = variables, columns = samples,” and applies the Synthetic parent-child limits.

Outputs:

- `query/param_encoding_real.csv`: used by the next step and excludes the Synthetic control rows.
- `query/param_encoding_full.csv`: includes the control rows and is intended for verification.

### Step 3: Generate ETM scenario input files

```bash
python generate_input_addup.py
```

Inputs:

- `query/param_encoding_real.csv`
- `query/database_index.csv`

Outputs:

- `data/input/scenario_list.csv`: the list of sample scenarios.
- `data/input/scenario_settings.csv`: the ETM input values for every sample.
- `query/min_max_data.csv`: the minimum and maximum values used for this run.
- `query/min_max_errors.csv`: generated or updated only when values are clipped.

Later task execution repeatedly overwrites `data/input/scenario_list.csv` and `data/input/scenario_settings.csv`. If you need to retain the complete master input, back up both files before splitting the tasks.

### Step 4: Split the samples into tasks

For the first run, or after confirming that you are starting a completely new run, execute:

```bash
python scenario_from_csv_opt.py --force-split --batch-size 1
```

Inputs:

- `data/input/scenario_list.csv`
- `data/input/scenario_settings.csv`

Expected structure:

```text
data/tasks/1/scenario_list.csv
data/tasks/1/scenario_settings.csv
data/tasks/2/...
```

`--force-split` deletes all existing tasks and task results under `data/tasks`. Use it only after backing up the previous results or when you explicitly intend to start a new run.

### Step 5: Run the ETM requests sequentially

```bash
python scenario_from_csv_opt.py --run
```

Check progress with:

```bash
python scenario_from_csv_opt.py --status
```

Each task invokes `scenario_from_csv.py`, updates the ETM scenario, executes the queries in `queries.csv`, and downloads the datasets defined in `data_downloads.csv`.

Expected outputs:

- `data/tasks/<task_number>/scenario_outcomes.csv`
- `data/output/sample_<sample_number>/sample_<sample_number>_energy_flow.csv`
- `data/output/sample_<sample_number>/sample_<sample_number>_merit_order.csv`

The tasks sequentially modify the same base ETM scenario. Do not start multiple `--run` processes at the same time.

Failed tasks retry every five seconds without a retry limit. If a task continues to fail, stop the process manually and check the token, network connection, ETM access, and variable settings.

### Step 6: Merge the query results

```bash
python merge_sample_outcomes.py
```

Input:

- `data/tasks/*/scenario_outcomes.csv`

Final output:

- `data/output/sample_outcomes_merged.csv`

This is the main deliverable. Its layout is “rows = ETM query metrics, columns = samples, final column = unit.”

Do not use the vertically appended file created by `scenario_from_csv_opt.py --merge` as the final analysis dataset.

## 4. Final deliverables

After a complete run, deliver at least the following files:

1. `data/output/sample_outcomes_merged.csv`: the final ETM metric matrix.
2. `variable_data.csv`: the variable definitions and ranges used for the run.
3. `query/param_encoding_real.csv`: the final sample parameter matrix before the ETM inputs are generated.

If the energy-flow and merit-order details are required, also deliver:

- `data/output/sample_*/sample_*_energy_flow.csv`
- `data/output/sample_*/sample_*_merit_order.csv`

It is recommended to copy the three core deliverables into `report/` before packaging the run. The detailed files under `data/output` may be very large and should normally be archived separately.

## 5. Command summary

```bash
python -m pip install -r requirements.txt
python whole_process.py --save_ratio_sampling
python data_transform.py
python generate_input_addup.py
python scenario_from_csv_opt.py --force-split --batch-size 1
python scenario_from_csv_opt.py --run
python scenario_from_csv_opt.py --status
python merge_sample_outcomes.py
```

Do not run `scenario_from_csv_opt.py` without arguments. With no arguments, it defaults to splitting, running, and using its built-in vertical merger, which is not the standard handover workflow.
