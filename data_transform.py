#!/usr/bin/env python3
"""
Data Transformation Script: Convert morris_sampling_design_ratios.csv to specified format
Transform from original format (columns=variables, rows=samples) to new format (rows=variables, columns=samples)
Converts ratio values (0-1) to actual values using min/max ranges from variable_data.csv

Features:
- Synthetic control elements: caps child values by parent values
- Outputs: param_encoding_real.csv (without controls) and param_encoding_full.csv (with controls)
"""

import pandas as pd
import numpy as np

print("=== Morris EE Sampling Data Transformation ===")
print("Converting morris_sampling_design_ratios.csv to specified format...\n")

# --- 1. Load Original Data ---
print("=== Step 1: Loading Original Data ===")
try:
    # Read ratio sampling file
    df = pd.read_csv('morris_sampling_design_ratios.csv')
    print(f"Successfully loaded morris_sampling_design_ratios.csv")
    print(f"Original data shape: {df.shape}")
    print(f"Number of variables: {df.shape[1]}")
    print(f"Number of samples: {df.shape[0]}")
    
    # Read variable_data.csv to get actual min/max ranges and variable properties
    var_data = pd.read_csv('variable_data.csv')
    var_data.columns = var_data.columns.str.strip()
    print(f"Successfully loaded variable_data.csv with {len(var_data)} rows")
    
    # Read synthetic_refer.csv for parent-child relationships
    synthetic_refer = pd.read_csv('synthetic_refer.csv')
    synthetic_refer.columns = synthetic_refer.columns.str.strip()
    print(f"Successfully loaded synthetic_refer.csv with {len(synthetic_refer)} rows")
    
except FileNotFoundError as e:
    print(f"Error: File not found - {e}")
    exit(1)

# --- 1.5. Build Variable Range Lookup and Identify Special Variables ---
print(f"\n=== Step 1.5: Building Variable Range Lookup ===")

def parse_value(val):
    """Parse min/max value, handling percentage strings and comma-separated numbers"""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.strip()
        if '%' in val:
            try:
                return float(val.replace('%', '').strip()) / 100.0
            except ValueError:
                return np.nan
        try:
            return float(val.replace(',', ''))
        except ValueError:
            return np.nan
    return np.nan

# Build lookup dictionary and identify special variables
var_ranges = {}
synthetic_controls = {}  # Synthetic control elements (column 8 = "Synthetic")
simplex_groups = {}  # Track simplex group membership

for _, row in var_data.iterrows():
    var_no = row.get('ETM Var no.')
    if pd.isna(var_no):
        continue
    var_no = str(var_no).strip()
    if not var_no or var_no == 'nan':
        continue
    
    min_val = parse_value(row.get('Min formula'))
    max_val = parse_value(row.get('Max formula'))
    var_ranges[var_no] = {'min': min_val, 'max': max_val}
    
    # Check if this is a Synthetic control element (column 8)
    synthetic_val = row.get('Synthetic?')
    if pd.notna(synthetic_val) and str(synthetic_val).strip() == 'Synthetic':
        synthetic_controls[var_no] = {'min': min_val, 'max': max_val}
    
    # Track simplex group membership
    simplex_type = row.get('Simplex / SYNsimplex')
    if pd.notna(simplex_type) and str(simplex_type).strip() in ['Simplex', 'SYNsimplex']:
        group_size = row.get('Simplex group size')
        if pd.notna(group_size):
            simplex_groups[var_no] = {
                'type': str(simplex_type).strip(),
                'group_size': int(group_size)
            }

print(f"Built range lookup for {len(var_ranges)} variables")
print(f"Found {len(synthetic_controls)} Synthetic control elements in variable_data.csv:")
for ctrl_id, ctrl_range in synthetic_controls.items():
    print(f"  {ctrl_id}: Min={ctrl_range['min']}, Max={ctrl_range['max']}")

# --- 1.6. Build Parent-Child Mapping from synthetic_refer.csv ---
print(f"\n=== Step 1.6: Building Parent-Child Mapping ===")

parent_child_map = {}  # Key: child variable, Value: parent control element
child_parent_map = {}  # Key: parent, Value: list of children

for _, row in synthetic_refer.iterrows():
    child_col = row.iloc[0] if len(row) > 0 else None
    parent_col = row.iloc[1] if len(row) > 1 else None
    
    if pd.notna(child_col) and pd.notna(parent_col):
        child = str(child_col).strip()
        parent = str(parent_col).strip()
        
        if child and parent:
            parent_child_map[child] = parent
            if parent not in child_parent_map:
                child_parent_map[parent] = []
            child_parent_map[parent].append(child)

print(f"Built parent-child mapping: {len(parent_child_map)} children mapped to parents")
for parent, children in child_parent_map.items():
    print(f"  {parent} controls {len(children)} children: {children}")

# --- 2. Data Transformation Preparation ---
print(f"\n=== Step 2: Data Transformation Preparation ===")

# Get variable ID list (column names from original data)
variable_ids = list(df.columns)
print(f"First 10 variable IDs: {variable_ids[:10]}")
print(f"Last 10 variable IDs: {variable_ids[-10:]}")

# Check which control elements are in the ratio file
print(f"\nChecking control elements in morris_sampling_design_ratios.csv:")
controls_in_ratios = []
controls_not_in_ratios = []
for ctrl_id in synthetic_controls.keys():
    if ctrl_id in variable_ids:
        controls_in_ratios.append(ctrl_id)
        print(f"  [FOUND] {ctrl_id}")
    else:
        controls_not_in_ratios.append(ctrl_id)
        print(f"  [NOT FOUND] {ctrl_id}")

if controls_not_in_ratios:
    print(f"\nWARNING: {len(controls_not_in_ratios)} control elements are NOT in the ratios file!")
    print(f"  These control elements will NOT be included in the output.")
    print(f"  Missing controls: {controls_not_in_ratios}")
    print(f"  This is likely because whole_process.py did not include them in the output.")

# Get sample data (each row from original data)
sample_data = df.values  # shape: (num_samples, num_variables)
num_samples = sample_data.shape[0]
num_variables = sample_data.shape[1]

print(f"Sample data shape: {sample_data.shape}")

# --- 3. Get Actual Min/Max for Each Variable ---
print(f"\n=== Step 3: Getting Actual Min/Max for Each Variable ===")

# Get actual min/max values from variable_data.csv lookup
variable_stats = []
missing_vars = []
var_id_to_index = {}  # Map variable ID to its index in variable_stats

for i, var_id in enumerate(variable_ids):
    # Look up actual min/max from variable_data.csv
    if var_id in var_ranges:
        actual_min = var_ranges[var_id]['min']
        actual_max = var_ranges[var_id]['max']
    else:
        # Fallback: use 0-1 range for variables not found
        actual_min = 0.0
        actual_max = 1.0
        missing_vars.append(var_id)
    
    variable_stats.append({
        'var_id': var_id,
        'min': actual_min,
        'max': actual_max,
        'is_control': var_id in synthetic_controls
    })
    var_id_to_index[var_id] = i

print(f"Retrieved actual ranges for {len(variable_stats)} variables")
if missing_vars:
    print(f"Warning: {len(missing_vars)} variables not found in variable_data.csv, using 0-1 range:")
    for v in missing_vars[:10]:  # Show first 10
        print(f"  - {v}")
    if len(missing_vars) > 10:
        print(f"  ... and {len(missing_vars) - 10} more")

# --- 4. Create Transformed Data Structure ---
print(f"\n=== Step 4: Creating Transformed Data Structure ===")

# Create new data structure
transformed_data = []

# First row: first column is "Sam", remaining columns are empty
first_row = ['Sam'] + [''] * (num_samples + 3)  # +3 for Var no., Formula, Min, Max
transformed_data.append(first_row)

# Second row: header row
header_row = ['Var no.', 'Formula', 'Min', 'Max']
for i in range(num_samples):
    header_row.append(f'Sample {i+1}')
transformed_data.append(header_row)

# Build a matrix to store all computed values for later parent-child check
# This will be indexed by [variable_index][sample_index]
computed_values = {}

# Third row onwards: one row per variable
for i, var_stat in enumerate(variable_stats):
    var_id = var_stat['var_id']
    actual_min = var_stat['min']
    actual_max = var_stat['max']
    
    # Get sample values for this variable
    sample_values = [sample_data[j, i] for j in range(num_samples)]
    
    # If min or max is NaN, calculate from sample values
    if pd.isna(actual_min) or pd.isna(actual_max):
        if pd.isna(actual_min):
            actual_min = min(sample_values)
            print(f"  Warning: {var_id} missing min, using sample min: {actual_min:.6f}")
        if pd.isna(actual_max):
            actual_max = max(sample_values)
            print(f"  Warning: {var_id} missing max, using sample max: {actual_max:.6f}")
        
        # Update var_stat for later use
        var_stat['min'] = actual_min
        var_stat['max'] = actual_max
    
    # Format min/max values - now guaranteed to have values
    min_str = f'{actual_min:.6f}'
    max_str = f'{actual_max:.6f}'
    
    # Create data row for this variable
    data_row = [
        var_id,    # Var no.
        '',        # Formula (blank)
        min_str,   # Min (actual range from variable_data.csv)
        max_str,   # Max (actual range from variable_data.csv)
    ]
    
    # Compute values for this variable across all samples
    computed_values[var_id] = []
    
    for j in range(num_samples):
        ratio_value = sample_data[j, i]
        
        # Convert ratio to actual value (now min/max are guaranteed valid)
        actual_value = actual_min + ratio_value * (actual_max - actual_min)
        
        computed_values[var_id].append(actual_value)
        data_row.append(f'{actual_value:.6f}')
    
    transformed_data.append(data_row)

print(f"Created initial transformed data structure with {len(transformed_data)} rows")

# --- 4.5. Special Handling for Variable 717 (Solar PV FLH) ---
print(f"\n=== Step 4.5: Special Handling for Variable 717 (Solar PV FLH) ===")

# Define the four new variables to generate from variable 717
SOLAR_PV_FLH_VARIABLES = [
    'flh_of_buildings_solar_pv_solar_radiation',
    'flh_of_energy_power_solar_pv_offshore',
    'flh_of_energy_power_solar_pv_solar_radiation',
    'flh_of_households_solar_pv_solar_radiation',
]

# Check if variable 717 exists
var_717_id = '717'
if var_717_id in computed_values:
    print(f"Variable 717 found! Generating 4 Solar PV FLH variables...")
    
    # Get the values from variable 717
    var_717_values = computed_values[var_717_id]
    
    # Get the min/max for variable 717
    var_717_min = var_ranges.get(var_717_id, {}).get('min', 0.0)
    var_717_max = var_ranges.get(var_717_id, {}).get('max', 1.0)
    
    # Handle NaN values
    if pd.isna(var_717_min):
        var_717_min = min(var_717_values) if var_717_values else 0.0
    if pd.isna(var_717_max):
        var_717_max = max(var_717_values) if var_717_values else 1.0
    
    print(f"  Variable 717 range: Min={var_717_min:.6f}, Max={var_717_max:.6f}")
    
    # Generate 4 new variables with the same values as variable 717
    for new_var_id in SOLAR_PV_FLH_VARIABLES:
        # Add to computed_values for consistency
        computed_values[new_var_id] = var_717_values.copy()
        
        # Add to var_ranges
        var_ranges[new_var_id] = {'min': var_717_min, 'max': var_717_max}
        
        # Create data row for this new variable
        new_data_row = [
            new_var_id,                    # Var no.
            '',                            # Formula (blank)
            f'{var_717_min:.6f}',          # Min (same as 717)
            f'{var_717_max:.6f}',          # Max (same as 717)
        ]
        
        # Add sample values (same as variable 717)
        for val in var_717_values:
            new_data_row.append(f'{val:.6f}')
        
        # Append to transformed_data
        transformed_data.append(new_data_row)
        
        # Add to variable_stats for tracking
        variable_stats.append({
            'var_id': new_var_id,
            'min': var_717_min,
            'max': var_717_max,
            'is_control': False
        })
        
        print(f"  Created: {new_var_id}")
    
    # Remove original variable 717 from transformed_data (it's replaced by the 4 new variables)
    # Find and remove the row for variable 717
    row_to_remove = None
    for idx, row in enumerate(transformed_data):
        if idx >= 2 and row[0] == var_717_id:  # Skip header rows (first 2 rows)
            row_to_remove = idx
            break
    
    if row_to_remove is not None:
        removed_row = transformed_data.pop(row_to_remove)
        print(f"  Removed original variable 717 from output (replaced by 4 new variables)")
    
    # Also remove from variable_stats to keep consistency
    variable_stats[:] = [vs for vs in variable_stats if vs['var_id'] != var_717_id]
    
    # Note: Keep 717 in computed_values for potential parent-child constraint checks
    
    print(f"Successfully replaced variable 717 with 4 Solar PV FLH variables")
else:
    print(f"Variable 717 not found in the data. Skipping Solar PV FLH variable generation.")

print(f"Updated transformed data structure with {len(transformed_data)} rows")

# --- 5. Apply Parent-Child Constraint Check (Final Check) ---
print(f"\n=== Step 5: Applying Parent-Child Constraint Check ===")

capped_count = 0
capped_details = []

for child_id, parent_id in parent_child_map.items():
    # Check if both child and parent exist in our computed values
    if child_id not in computed_values:
        continue
    if parent_id not in computed_values:
        print(f"  Warning: Parent {parent_id} not found in computed values for child {child_id}")
        continue
    
    child_values = computed_values[child_id]
    parent_values = computed_values[parent_id]
    
    # Find the row index for this child variable (offset by 2 for header rows)
    child_row_idx = None
    for idx, stat in enumerate(variable_stats):
        if stat['var_id'] == child_id:
            child_row_idx = idx + 2  # +2 for header rows
            break
    
    if child_row_idx is None:
        continue
    
    # Check each sample and cap if necessary
    for sample_idx in range(num_samples):
        child_val = child_values[sample_idx]
        parent_val = parent_values[sample_idx]
        
        if child_val > parent_val:
            # Cap child value to parent value
            capped_details.append({
                'child': child_id,
                'parent': parent_id,
                'sample': sample_idx + 1,
                'original': child_val,
                'capped_to': parent_val
            })
            
            # Update the computed values
            computed_values[child_id][sample_idx] = parent_val
            
            # Update the transformed data row (sample columns start at index 4)
            transformed_data[child_row_idx][4 + sample_idx] = f'{parent_val:.6f}'
            capped_count += 1

print(f"Parent-child constraint check completed:")
print(f"  - Total values capped: {capped_count}")
if capped_details:
    print(f"  - Sample capped entries (first 10):")
    for detail in capped_details[:10]:
        print(f"    {detail['child']} (sample {detail['sample']}): {detail['original']:.4f} -> {detail['capped_to']:.4f} (parent: {detail['parent']})")
    if len(capped_details) > 10:
        print(f"    ... and {len(capped_details) - 10} more")

# --- 6. Prepare Data for Two Output Files ---
print(f"\n=== Step 6: Preparing Output Files ===")

# Separate control elements from regular variables
control_data = []  # Rows for control elements only
regular_data = []  # Rows for non-control elements

for i, row in enumerate(transformed_data):
    if i < 2:  # Header rows - include in both
        control_data.append(row)
        regular_data.append(row)
    else:
        var_id = row[0]
        if var_id in synthetic_controls:
            control_data.append(row)
        else:
            regular_data.append(row)

print(f"Separated data:")
print(f"  - Control elements: {len(control_data) - 2} variables")  # -2 for headers
print(f"  - Regular elements: {len(regular_data) - 2} variables")

# --- 7. Save Output Files ---
print(f"\n=== Step 7: Saving Output Files ===")

# Save param_encoding_real.csv (regular variables only, without control elements)
output_real = 'query/param_encoding_real.csv'
regular_df = pd.DataFrame(regular_data)
regular_df.to_csv(output_real, index=False, header=False)
print(f"Saved {output_real}: {len(regular_data)} rows (regular variables)")

# Save param_encoding_full.csv (all variables including control elements)
output_full = 'query/param_encoding_full.csv'
full_df = pd.DataFrame(transformed_data)
full_df.to_csv(output_full, index=False, header=False)
print(f"Saved {output_full}: {len(transformed_data)} rows (all variables including controls)")

# --- 8. Verification and Statistics ---
print(f"\n=== Step 8: Verification and Statistics ===")

print(f"Output file statistics:")
print(f"  param_encoding_real.csv:")
print(f"    - Total rows: {len(regular_data)}")
print(f"    - Variables (data rows): {len(regular_data) - 2}")
print(f"    - Samples (data columns): {num_samples}")
print(f"  param_encoding_full.csv:")
print(f"    - Total rows: {len(transformed_data)}")
print(f"    - Variables (data rows): {len(transformed_data) - 2}")
print(f"    - Control elements: {len(synthetic_controls)}")
print(f"    - Samples (data columns): {num_samples}")

# Display first few rows of transformed data as examples
print(f"\nFirst 5 rows of transformed data:")
for i in range(min(5, len(transformed_data))):
    row = transformed_data[i]
    # Only display first 10 columns to avoid lengthy output
    display_row = row[:10] if len(row) > 10 else row
    if len(row) > 10:
        display_row.append('...')
    print(f"  Row {i+1}: {display_row}")

print(f"\nFirst 5 variables with conversion verification (Sample 1):")
print(f"  {'Variable':<20} {'Ratio':<12} {'Min':<12} {'Max':<12} {'Actual':<12}")
print(f"  {'-'*20} {'-'*12} {'-'*12} {'-'*12} {'-'*12}")
for i in range(min(5, len(variable_stats))):
    var_stat = variable_stats[i]
    var_id = var_stat['var_id']
    actual_min = var_stat['min']
    actual_max = var_stat['max']
    
    # Get original ratio value (Sample 1)
    ratio_val = sample_data[0, i]
    
    # Get converted actual value
    row_idx = i + 2  # +2 because first row is Sam, second row is headers
    if row_idx < len(transformed_data):
        data_row = transformed_data[row_idx]
        actual_val = data_row[4]  # Sample 1 value
        
        min_str = f"{actual_min:.4f}" if not pd.isna(actual_min) else "N/A"
        max_str = f"{actual_max:.4f}" if not pd.isna(actual_max) else "N/A"
        print(f"  {var_id:<20} {ratio_val:<12.4f} {min_str:<12} {max_str:<12} {actual_val:<12}")

# Show control element values
print(f"\nControl elements verification (Sample 1):")
for ctrl_id in synthetic_controls.keys():
    if ctrl_id in computed_values:
        ctrl_val = computed_values[ctrl_id][0]  # Sample 1
        ctrl_range = synthetic_controls[ctrl_id]
        children = child_parent_map.get(ctrl_id, [])
        print(f"  {ctrl_id}: value={ctrl_val:.4f}, range=[{ctrl_range['min']:.4f}, {ctrl_range['max']:.4f}], controls {len(children)} children")

print(f"\n=== Data Transformation Complete ===")
print(f"Successfully converted morris_sampling_design_ratios.csv")
print(f"Output files:")
print(f"  - {output_real}: Regular variables (without control elements)")
print(f"  - {output_full}: All variables (including control elements)")
print(f"Applied transformations:")
print(f"  - Ratio values (0-1) converted to actual values using min/max from variable_data.csv")
print(f"  - Parent-child constraints applied: {capped_count} values capped")
print(f"Format: Rows=variables, Columns=samples (with metadata columns)")
print(f"  - Column 1: Variable IDs")
print(f"  - Column 2: Formula (empty)")  
print(f"  - Column 3: Min values (actual range from variable_data.csv)")
print(f"  - Column 4: Max values (actual range from variable_data.csv)")
print(f"  - Columns 5+: Sample values (actual values)")
