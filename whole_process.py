#!/usr/bin/env python3
"""
Morris Elementary Effects Screening - 232 Dimensional Final Implementation
Complete 232-dimensional Morris EE sampling design implementation
Sequential reading logic: 114 EI + 118 DoF = 232 dimensions
"""

import pandas as pd
import numpy as np
from SALib.sample import morris
import collections
from io import StringIO
import argparse
import sys

# --- Command Line Arguments ---
parser = argparse.ArgumentParser(description='Morris Elementary Effects Screening - 232D Implementation')
parser.add_argument('-p', '--print-groups', action='store_true', 
                    help='Print Simplex groups information and exit')
parser.add_argument('--save_ratio_sampling', action='store_true',
                    help='Save ratio sampling values (0-1 range) before scaling transformations to CSV')
args = parser.parse_args()

print("=== Morris Elementary Effects Screening - 232D Final Implementation ===")
print("Starting 232-dimensional Morris EE sampling design generation...\n")

# --- Configuration ---
NUM_TRAJECTORIES = 6
NUM_LEVELS = 4
print(f"Number of trajectories (r): {NUM_TRAJECTORIES}")
print(f"Number of levels (p): {NUM_LEVELS}")

# --- 1. Data Loading ---
print("\n=== Data Loading ===")
try:
    df = pd.read_csv('variable_data.csv')
    print(f"Successfully loaded data from 'variable_data.csv'")
except FileNotFoundError:
    print("Error: 'variable_data.csv' not found. Please ensure the file is in the same directory.")
    exit(1)

df.columns = df.columns.str.strip()
print(f"Data shape: {df.shape}")

# Parse range values
def parse_range_values(value):
    if isinstance(value, str):
        value = value.strip()
        if '%' in value:
            try:
                return float(value.replace('%', '').strip()) / 100.0
            except ValueError:
                pass
        try:
            return float(value)
        except ValueError:
            return np.nan
    return value

df['Min formula'] = df['Min formula'].apply(parse_range_values)
df['Max formula'] = df['Max formula'].apply(parse_range_values)
print("Parsed min/max values and handled percentage strings")

# --- 2. Sequential Variable Classification ---
print("\n=== Sequential Variable Classification ===")

# Initialize lists for each category
euclidean_independent_vars = []
equivalent_vars = []  # Will store dict with var_no, equivalent_id, parent_id
simplex_groups = []  # List of groups, each group is a list of variables
synsimplex_groups = []  # List of SYNsimplex groups
static_vars = []

variable_properties = {}  # Store all variable properties

# Parent-child relationship storage
parent_ei_vars = []  # List of parent EI variable names
simplex_parent_mapping = {}  # Maps simplex group index to parent EI variable name

# Sequential reading logic
current_simplex_group = []
current_synsimplex_group = []
current_group_type = None  # Track if we're in 'Simplex' or 'SYNsimplex' group
current_range_formula_tracking = None  # Track Range formula to detect group boundaries

print("Starting sequential reading...")

valid_rows = 0
for index, row in df.iterrows():
    etm_var_no = str(row['ETM Var no.'])
    
    # Skip rows with NaN ETM Var no.
    if etm_var_no == 'nan' or pd.isna(row['ETM Var no.']):
        continue
    
    # Parse min/max values
    min_val = row['Min formula']
    max_val = row['Max formula']
    if isinstance(min_val, str) and '%' in min_val:
        min_val = float(min_val.replace('%', '').strip()) / 100.0
    if isinstance(max_val, str) and '%' in max_val:
        max_val = float(max_val.replace('%', '').strip()) / 100.0

    # Store variable properties
    variable_properties[etm_var_no] = {
        'min': pd.to_numeric(min_val, errors='coerce'),
        'max': pd.to_numeric(max_val, errors='coerce'),
        'range_formula': row['Range formula'],
        'min_formula': row['Min formula'],
        'max_formula': row['Max formula'],
        'design_var_index': int(row['Design VAR no.']) - 1,
        'simplex_group_size': row.get('Simplex group size', np.nan)
    }
    
    # Classification logic
    if row['Euclidean Independent?'] == 'Euclidean Independent':
        # Euclidean Independent variable
        euclidean_independent_vars.append(etm_var_no)
        variable_properties[etm_var_no]['type'] = 'ei'
        
    elif row['Equivalent?'] == 'Equivalent':
        # Equivalent variable - parse var no using split('.') method
        var_no = str(etm_var_no)
        parsed = False
        
        # Split by '.' to get parts: [equivalent_id, relation_type, parent_id, ...]
        parts = var_no.split('.')
        if len(parts) >= 3:
            equivalent_id = parts[0]
            relation_type = parts[1]  # 'EQ' or 'RATIOEQ'
            parent_id = parts[2]
            
            if relation_type in ['EQ', 'RATIOEQ']:
                equivalent_vars.append({
                    'var_no': var_no,
                    'equivalent_id': equivalent_id,
                    'parent_id': parent_id,
                    'relation_type': relation_type  # Added relation type
                })
                variable_properties[etm_var_no]['type'] = 'equivalent'
                variable_properties[etm_var_no]['parent_id'] = parent_id
                variable_properties[etm_var_no]['relation_type'] = relation_type
                print(f"  Parsed Equivalent: {var_no} -> {relation_type} relationship with parent_id: {parent_id}")
                parsed = True
        
        if not parsed:
            print(f"  Warning: Could not parse Equivalent variable format: {var_no}")
        
    elif pd.notna(row['Remove/set as X']) and str(row['Remove/set as X']).startswith('Set'):
        # Fixed variable (static) - only process values starting with 'Set'
        static_vars.append(etm_var_no)
        variable_properties[etm_var_no]['type'] = 'static'
        variable_properties[etm_var_no]['remove_set_value'] = str(row['Remove/set as X'])
        
        # 静态变量也应该触发 Simplex 组结束
        if current_simplex_group and current_group_type == 'Simplex':
            simplex_groups.append(current_simplex_group.copy())
            current_simplex_group = []
            current_group_type = None
        elif current_synsimplex_group and current_group_type == 'SYNsimplex':
            synsimplex_groups.append(current_synsimplex_group.copy())
            current_synsimplex_group = []
            current_group_type = None
        
    elif pd.notna(row['Simplex / SYNsimplex']):
        # Simplex or SYNsimplex variable
        simplex_type = row['Simplex / SYNsimplex']
        variable_properties[etm_var_no]['type'] = 'simplex'
        variable_properties[etm_var_no]['is_synsimplex'] = (simplex_type == 'SYNsimplex')
        
        # 获取当前变量的 Range formula
        current_range_formula = str(row.get('Range formula', '')).strip()
        
        # Correct grouping logic: group ends when we encounter a row with 'Simplex group size'
        # OR when Range formula changes (indicating different Simplex group type)
        if simplex_type == 'Simplex':
            # Start new group if not already in a Simplex group
            if current_group_type != 'Simplex':
                # Finish previous SYNsimplex group if exists
                if current_synsimplex_group and current_group_type == 'SYNsimplex':
                    synsimplex_groups.append(current_synsimplex_group.copy())
                    current_synsimplex_group = []
                current_group_type = 'Simplex'
                current_range_formula_tracking = current_range_formula  # 记录当前组的 Range formula
            else:
                # 检查 Range formula 是否变化，如果变化则结束当前组
                if current_simplex_group and current_range_formula != current_range_formula_tracking:
                    simplex_groups.append(current_simplex_group.copy())
                    current_simplex_group = []
                    current_range_formula_tracking = current_range_formula
            
            # Add current variable to the group
            current_simplex_group.append(etm_var_no)
            
            # Check if this row has 'Simplex group size' - if so, this is the end of the group
            if pd.notna(row['Simplex group size']):
                simplex_groups.append(current_simplex_group.copy())
                current_simplex_group = []
                current_group_type = None
                current_range_formula_tracking = None  # 重置 Range formula 追踪
            
        elif simplex_type == 'SYNsimplex':
            # Start new group if not already in a SYNsimplex group
            if current_group_type != 'SYNsimplex':
                # Finish previous Simplex group if exists
                if current_simplex_group and current_group_type == 'Simplex':
                    simplex_groups.append(current_simplex_group.copy())
                    current_simplex_group = []
                current_group_type = 'SYNsimplex'
                current_range_formula_tracking = current_range_formula  # 记录当前组的 Range formula
            else:
                # 检查 Range formula 是否变化，如果变化则结束当前组
                if current_synsimplex_group and current_range_formula != current_range_formula_tracking:
                    synsimplex_groups.append(current_synsimplex_group.copy())
                    current_synsimplex_group = []
                    current_range_formula_tracking = current_range_formula
            
            # Add current variable to the group
            current_synsimplex_group.append(etm_var_no)
            
            # Check if this row has 'Simplex group size' - if so, this is the end of the group
            if pd.notna(row['Simplex group size']):
                synsimplex_groups.append(current_synsimplex_group.copy())
                current_synsimplex_group = []
                current_group_type = None
                current_range_formula_tracking = None  # 重置 Range formula 追踪
    
    else:
        # Non-simplex variable encountered - finish any ongoing groups
        if current_simplex_group and current_group_type == 'Simplex':
            simplex_groups.append(current_simplex_group.copy())
            current_simplex_group = []
        elif current_synsimplex_group and current_group_type == 'SYNsimplex':
            synsimplex_groups.append(current_synsimplex_group.copy())
            current_synsimplex_group = []
        current_group_type = None
    
    valid_rows += 1

# Handle any remaining groups
if current_simplex_group and current_group_type == 'Simplex':
    simplex_groups.append(current_simplex_group)
elif current_synsimplex_group and current_group_type == 'SYNsimplex':
    synsimplex_groups.append(current_synsimplex_group)

print(f"Sequential reading completed. Processed {valid_rows} valid variables")

# --- 2.5. Parse Parent-Child Relationships ---
print(f"\n=== Parsing Parent-Child Relationships ===")

# Find Parent EI variables
parent_ei_start_row = None
for index, row in df.iterrows():
    if pd.notna(row.iloc[3]) and str(row.iloc[3]).strip() == "Parent EI D:":
        parent_ei_start_row = index
        break

if parent_ei_start_row is not None:
    print(f"Found Parent EI D: at row {parent_ei_start_row}")
    
    # Read parent EI variables from the right cell and downwards
    for index in range(parent_ei_start_row, len(df)):
        row = df.iloc[index]
        parent_ei_cell = row.iloc[4]  # Right cell (column E, index 4)
        
        if pd.notna(parent_ei_cell) and str(parent_ei_cell).strip():
            parent_ei_name = str(parent_ei_cell).strip()
            if parent_ei_name not in parent_ei_vars:
                parent_ei_vars.append(parent_ei_name)
                print(f"  Found parent EI variable: {parent_ei_name}")
        else:
            # Also check the next row for more parent EI variables
            if index < len(df) - 1:
                next_row = df.iloc[index + 1]
                next_parent_ei_cell = next_row.iloc[4]
                if pd.notna(next_parent_ei_cell) and str(next_parent_ei_cell).strip():
                    continue
            break  # Stop when no more parent EI variables found

# Find Child Simplex relationships
child_simplex_start_row = None
for index, row in df.iterrows():
    if pd.notna(row.iloc[7]) and str(row.iloc[7]).strip() == "Child Simplex D:":
        child_simplex_start_row = index
        break

if child_simplex_start_row is not None:
    print(f"Found Child Simplex D: at row {child_simplex_start_row}")
    
    # Read child-parent mappings
    processed_simplex_vars = set()  # Track processed simplex variables to avoid duplicates
    
    for index in range(child_simplex_start_row + 1, len(df)):
        row = df.iloc[index]
        simplex_var = row.iloc[7]  # Column H (index 7)
        parent_var = row.iloc[8]   # Column I (index 8)
        
        if pd.notna(simplex_var) and pd.notna(parent_var):
            simplex_var_str = str(simplex_var).strip()
            parent_var_str = str(parent_var).strip()
            
            if simplex_var_str and parent_var_str:
                # Find which group this simplex variable belongs to
                target_group_index = None
                for group_idx, group in enumerate(simplex_groups + synsimplex_groups):
                    if simplex_var_str in group:
                        target_group_index = group_idx
                        break
                
                # Only record the first variable of each group
                if target_group_index is not None and target_group_index not in simplex_parent_mapping:
                    simplex_parent_mapping[target_group_index] = parent_var_str
                    group_type = "Simplex" if target_group_index < len(simplex_groups) else "SYNsimplex"
                    print(f"  Mapped {group_type} Group {target_group_index + 1} to parent EI: {parent_var_str}")
        else:
            # Stop if we encounter empty cells
            if pd.isna(simplex_var) and pd.isna(parent_var):
                break

print(f"Parent-child relationship parsing completed:")
print(f"  - Parent EI variables: {len(parent_ei_vars)}")
print(f"  - Simplex groups with parents: {len(simplex_parent_mapping)}")

# --- 3. Print Group Statistics ---
print(f"\n=== Group Statistics ===")
print(f"Euclidean Independent variables: {len(euclidean_independent_vars)}")
print(f"Equivalent variables: {len(equivalent_vars)}")
print(f"Static variables: {len(static_vars)}")

# Print parsed equivalent variables
if equivalent_vars:
    print("Parsed Equivalent variables:")
    for equiv_info in equivalent_vars:
        print(f"  {equiv_info['var_no']} -> parent: {equiv_info['parent_id']}")
print(f"Simplex groups: {len(simplex_groups)} groups")
for i, group in enumerate(simplex_groups):
    print(f"  Simplex Group {i+1}: {len(group)} variables - {group}")
print(f"SYNsimplex groups: {len(synsimplex_groups)} groups")
for i, group in enumerate(synsimplex_groups):
    print(f"  SYNsimplex Group {i+1}: {len(group)} variables - {group}")

# --- Print Detailed Group Information (if -p flag is used) ---
def print_detailed_groups():
    """Print detailed information about all Simplex groups in order"""
    print(f"\n{'='*80}")
    print(f"DETAILED SIMPLEX GROUPS INFORMATION")
    print(f"{'='*80}")
    
    all_groups = simplex_groups + synsimplex_groups
    total_groups = len(all_groups)
    
    print(f"Total Groups: {total_groups}")
    print(f"  - Simplex Groups: {len(simplex_groups)}")
    print(f"  - SYNsimplex Groups: {len(synsimplex_groups)}")
    print(f"\nGroup Details (in sequential order):")
    print(f"{'-'*80}")
    
    for i, group in enumerate(all_groups):
        group_type = "Simplex" if i < len(simplex_groups) else "SYNsimplex"
        group_size = len(group)
        dof = group_size - 1
        
        print(f"\nGroup {i+1:2d} [{group_type:10s}] - Size: {group_size}, DoF: {dof}")
        print(f"  Variables: {', '.join(group)}")
        
        # Print variable properties if available
        print(f"  Variable Details:")
        for j, var in enumerate(group):
            if var in variable_properties:
                props = variable_properties[var]
                min_val = props.get('min', 'N/A')
                max_val = props.get('max', 'N/A')
                design_var = props.get('design_var_index', 'N/A')
                print(f"    {j+1:2d}. {var:20s} - Range: [{min_val}, {max_val}], Design VAR: {design_var}")
            else:
                print(f"    {j+1:2d}. {var:20s} - No properties found")
    
    print(f"\n{'-'*80}")
    print(f"Summary:")
    print(f"  Total variables in groups: {sum(len(group) for group in all_groups)}")
    print(f"  Total DoF contributed: {sum(len(group)-1 for group in all_groups)}")
    print(f"  EI variables: {len(euclidean_independent_vars)}")
    print(f"  Total sampling dimensions: {len(euclidean_independent_vars)} + {sum(len(group)-1 for group in all_groups)} = {len(euclidean_independent_vars) + sum(len(group)-1 for group in all_groups)}")
    print(f"{'='*80}")

# Check if print flag is set
if args.print_groups:
    print_detailed_groups()
    print("\nExiting after printing group information (use without -p to run full sampling).")
    sys.exit(0)

# --- 4. Calculate Degrees of Freedom ---
print(f"\n=== Calculating Degrees of Freedom ===")

total_dof = 0
all_groups = simplex_groups + synsimplex_groups

print("DoF calculation for each group:")
for i, group in enumerate(all_groups):
    group_size = len(group)
    dof = group_size - 1
    total_dof += dof
    group_type = "Simplex" if i < len(simplex_groups) else "SYNsimplex"
    print(f"  {group_type} Group {i+1}: {group_size} vars → {dof} DoF")

print(f"Total degrees of freedom from all groups: {total_dof}")
print(f"Total sampling dimensions: {len(euclidean_independent_vars)} EI + {total_dof} DoF = {len(euclidean_independent_vars) + total_dof}")
print(f"Note: Equivalent variables ({len(equivalent_vars)}) are not included in sampling - they will be derived from parent variables")

if len(euclidean_independent_vars) + total_dof == 232:
    print("Perfect! Achieved exactly 232 dimensions!")
else:
    print(f"Got {len(euclidean_independent_vars) + total_dof} dimensions, expected 232")

# --- 5. Prepare SALib Input ---
print(f"\n=== Preparing SALib Input ===")

salib_parameters = []

# Add all Euclidean Independent variables
for etm_var_no in euclidean_independent_vars:
    if etm_var_no in variable_properties:
        props = variable_properties[etm_var_no]
        salib_parameters.append({
            'name': etm_var_no,
            'bounds': [0, 1],
            'type': 'EI',
            'actual_min': props['min'],
            'actual_max': props['max']
        })

# Add DoF variables for each group
for i, group in enumerate(all_groups):
    group_size = len(group)
    dof = group_size - 1
    group_type = "Simplex" if i < len(simplex_groups) else "SYNsimplex"
    
    for dof_idx in range(dof):
        salib_parameters.append({
            'name': f"{group_type}_G{i+1}_DoF{dof_idx + 1}",
            'bounds': [0, 1],
            'type': 'DoF',
            'group_id': i + 1,
            'group_members': group,
            'group_type': group_type
        })

total_dimensions = len(salib_parameters)
print(f"Created {total_dimensions} SALib parameters:")
print(f"  - EI variables: {len(euclidean_independent_vars)}")
print(f"  - DoF variables: {total_dof}")

# --- 6. Generate Morris Samples ---
print(f"\n=== Generating Morris Samples ===")

problem = {
    'num_vars': len(salib_parameters),
    'names': [p['name'] for p in salib_parameters],
    'bounds': [p['bounds'] for p in salib_parameters]
}

sample = morris.sample(
    problem=problem,
    N=NUM_TRAJECTORIES,
    num_levels=NUM_LEVELS,
    seed=42
)

print(f"Generated Morris sample shape: {sample.shape}")

# Create DataFrame
morris_df = pd.DataFrame(sample, columns=[p['name'] for p in salib_parameters])

# --- 6.5. Define Dirichlet Function (needed for ratio sampling) ---
def dof_to_dirichlet_simplex(dof_values, group_size, random_seed=None):
    """
    Convert Morris DoF values to Simplex variables using Dirichlet distribution
    
    Args:
        dof_values: array of shape (n_samples, n_dof) where n_dof = group_size - 1
        group_size: number of variables in the Simplex group
        random_seed: random seed for reproducibility
    
    Returns:
        simplex_values: array of shape (n_samples, group_size) satisfying Simplex constraints
                       Sum of each row = 1.0
    """
    if random_seed is not None:
        np.random.seed(random_seed)
    
    n_samples = dof_values.shape[0]
    n_dof = group_size - 1
    
    results = []
    
    for i in range(n_samples):
        dof_vals = dof_values[i]  # Length: n_dof
        
        # Convert DoF values to Dirichlet alpha parameters
        alpha_params = []
        
        # Map DoF values [0,1] to alpha parameters [0.1, 5.0]
        # This ensures reasonable variability while avoiding alpha=0
        alpha_base = 0.1
        alpha_range = 4.9
        
        for dof_val in dof_vals:
            alpha = alpha_base + alpha_range * dof_val
            alpha_params.append(alpha)
        
        # Add alpha parameter for the last variable (original group member)
        # Use mean of other alphas to ensure balanced distribution
        if len(alpha_params) > 0:
            last_alpha = alpha_base + np.mean([a - alpha_base for a in alpha_params])
        else:
            last_alpha = 1.0
        alpha_params.append(last_alpha)
        
        # Sample from Dirichlet distribution
        # This automatically satisfies Simplex constraints (sum=1, all>0)
        simplex_sample = np.random.dirichlet(alpha_params)
        
        # === 截断修复：确保总和精确为 1.0 ===
        # 对前 n-1 个值截断到指定小数位数，最后一个值通过计算得出
        decimal_places = 3  # 截断到三位小数
        
        if len(simplex_sample) > 1:
            # 截断前 n-1 个值
            truncated_values = np.floor(simplex_sample[:-1] * (10 ** decimal_places)) / (10 ** decimal_places)
            
            # 计算最后一个值，确保总和为 1.0
            last_value = 1.0 - np.sum(truncated_values)
            
            # 确保最后一个值不为负（边界情况处理）
            if last_value < 0:
                # 如果最后一个值为负，需要调整前面的值
                last_value = 0.0
                # 重新归一化前面的值
                if np.sum(truncated_values) > 0:
                    truncated_values = truncated_values / np.sum(truncated_values)
            
            # 截断最后一个值到相同精度
            last_value = round(last_value, decimal_places)
            
            # 组合结果
            simplex_sample = np.concatenate([truncated_values, [last_value]])
        
        results.append(simplex_sample)
    
    return np.array(results)

# --- 6.5. Save Ratio Sampling (if requested) ---
if args.save_ratio_sampling:
    print(f"\n=== Saving Ratio Sampling Values ===")
    
    # Create a copy of the original Morris sample (0-1 range) before any transformations
    ratio_df = morris_df.copy()
    
    # Add all target variables with their 0-1 ratio values before scaling
    # This includes EI variables (still in 0-1 range) and DoF variables (also 0-1 range)
    
    # For Simplex groups, we need to reconstruct the ratio values before scaling
    # We'll save the DoF values and the reconstructed Simplex proportions (before scaling)
    temp_ratio_df = ratio_df.copy()
    
    # Add Simplex variables as proportions (0-1 range, sum=1 per group) before scaling
    for i, group in enumerate(all_groups):
        group_size = len(group)
        dof = group_size - 1
        group_type = "Simplex" if i < len(simplex_groups) else "SYNsimplex"
        
        # Get DoF values for this group
        dof_cols = [f"{group_type}_G{i+1}_DoF{j+1}" for j in range(dof)]
        available_dof_cols = [col for col in dof_cols if col in temp_ratio_df.columns]
        
        if available_dof_cols and dof > 0:
            dof_values = temp_ratio_df[available_dof_cols].values
            
            # Use the same Dirichlet distribution to get ratio values
            # With placeholder: sum < 1, Without placeholder: sum = 1
            full_group_values = dof_to_dirichlet_simplex(
                dof_values, 
                group_size, 
                random_seed=42,  # Same seed for consistency
            )
            
            # Add to ratio DataFrame - these are proportions
            # If using placeholder, sum < 1 (placeholder takes the rest)
            for j, var in enumerate(group):
                temp_ratio_df[var] = full_group_values[:, j]
    
    # Add equivalent variables as ratios (copy from parent ratios)
    for equiv_info in equivalent_vars:
        var_no = equiv_info['var_no']
        parent_id = equiv_info['parent_id']
        relation_type = equiv_info['relation_type']
        
        # Find parent variable in temp_ratio_df
        parent_col = None
        if parent_id in temp_ratio_df.columns:
            parent_col = parent_id
        else:
            # Try to find column that starts with parent_id
            for col in temp_ratio_df.columns:
                if col.startswith(parent_id + '.') or col.startswith(parent_id):
                    parent_col = col
                    break
        
        if parent_col:
            # For ratio sampling, both EQ and RATIOEQ use the same ratio values
            temp_ratio_df[var_no] = temp_ratio_df[parent_col].copy()
    
    # Add static variables as their ratio values (0 or 1)
    for static_var in static_vars:
        if static_var in variable_properties:
            props = variable_properties[static_var]
            if 'remove_set_value' in props:
                setting = props['remove_set_value']
                if setting == 'Set as 0' or setting == 'Set to OFF':
                    temp_ratio_df[static_var] = 0.0
                elif setting in ['Set to ON', 'Set as ON']:
                    temp_ratio_df[static_var] = 1.0
                else:
                    temp_ratio_df[static_var] = 0.0
    
    # Filter to target columns (same logic as final output)
    ratio_target_columns = []
    
    # Add Euclidean Independent variables
    for var in euclidean_independent_vars:
        if var in temp_ratio_df.columns:
            ratio_target_columns.append(var)
    
    # Add all Simplex variables
    for group in simplex_groups + synsimplex_groups:
        for var in group:
            if var in temp_ratio_df.columns:
                ratio_target_columns.append(var)
    
    # Add static variables
    for static_var in static_vars:
        if static_var in temp_ratio_df.columns:
            ratio_target_columns.append(static_var)
    
    # Add equivalent variables
    for equiv_info in equivalent_vars:
        var_no = equiv_info['var_no']
        if var_no in temp_ratio_df.columns:
            ratio_target_columns.append(var_no)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_ratio_columns = []
    for col in ratio_target_columns:
        if col not in seen:
            unique_ratio_columns.append(col)
            seen.add(col)
    
    # Filter to numeric ID columns and synthetic control columns, then sort
    def extract_numeric_id(column_name):
        """Extract the leading numeric part from column name for sorting"""
        import re
        match = re.match(r'^(\d+)', str(column_name))
        if match:
            return int(match.group(1))
        return float('inf')
    
    def is_synthetic_control(column_name):
        """Check if column is a Synthetic control element (starts with SYN.)"""
        return str(column_name).startswith('SYN.')
    
    # Separate numeric and synthetic control columns
    numeric_ratio_columns = [col for col in unique_ratio_columns if extract_numeric_id(col) != float('inf')]
    synthetic_ratio_columns = [col for col in unique_ratio_columns if is_synthetic_control(col)]
    
    # Sort and combine
    sorted_numeric_ratio = sorted(numeric_ratio_columns, key=extract_numeric_id)
    sorted_synthetic_ratio = sorted(synthetic_ratio_columns)
    sorted_ratio_columns = sorted_numeric_ratio + sorted_synthetic_ratio
    
    # Create final ratio DataFrame
    ratio_output_df = temp_ratio_df[sorted_ratio_columns]
    
    # Save ratio sampling to CSV
    ratio_filename = 'morris_sampling_design_ratios.csv'
    ratio_output_df.to_csv(ratio_filename, index=False)
    
    print(f"Saved ratio sampling values to: {ratio_filename}")
    print(f"  - Shape: {ratio_output_df.shape}")
    print(f"  - All values in 0-1 range (EI variables: 0-1, Simplex proportions: 0-1 sum=1, Static: 0 or 1)")
    print(f"  - Columns: {len(sorted_ratio_columns)} variables ({len(sorted_numeric_ratio)} numeric + {len(sorted_synthetic_ratio)} synthetic controls)")
    if sorted_synthetic_ratio:
        print(f"  - Synthetic controls included: {sorted_synthetic_ratio}")
    
    # Show sample statistics
    print(f"\nRatio sampling statistics:")
    print(f"  - EI variables range: [0, 1] (uniform)")
    print(f"  - Simplex variables: proportions summing to 1 per group")
    print(f"  - Static variables: fixed at 0 or 1")
    print(f"  - Equivalent variables: same ratios as parent variables")

# --- 7. Apply Transformations ---
print(f"\n=== Applying Transformations ===")

# Scale EI variables to actual ranges
for param in salib_parameters:
    if param['type'] == 'EI':
        etm_var = param['name']
        actual_min = param['actual_min']
        actual_max = param['actual_max']
        
        if not pd.isna(actual_min) and not pd.isna(actual_max):
            morris_df[etm_var] = actual_min + morris_df[etm_var] * (actual_max - actual_min)

# Reconstruct Simplex variables from DoF using Dirichlet distribution (function defined above)

print("Reconstructing Simplex variables from DoF using Dirichlet distribution...")

# Add all Simplex variables to the DataFrame
for i, group in enumerate(all_groups):
    group_size = len(group)
    dof = group_size - 1
    group_type = "Simplex" if i < len(simplex_groups) else "SYNsimplex"
    
    # Get DoF values for this group
    dof_cols = [f"{group_type}_G{i+1}_DoF{j+1}" for j in range(dof)]
    available_dof_cols = [col for col in dof_cols if col in morris_df.columns]
    
    if available_dof_cols and dof > 0:
        dof_values = morris_df[available_dof_cols].values
        
        # Use Dirichlet distribution to reconstruct Simplex variables
        # With placeholder: sum < 1 (placeholder takes the rest)
        # Without placeholder: sum = 1
        full_group_values = dof_to_dirichlet_simplex(
            dof_values, 
            group_size, 
            random_seed=42,  # For reproducibility
        )
        
        # Add to DataFrame using pd.concat for better performance
        group_df = pd.DataFrame(full_group_values, columns=group, index=morris_df.index)
        morris_df = pd.concat([morris_df, group_df], axis=1)
        
        # Check if this group has a parent EI variable
        has_parent_ei = i in simplex_parent_mapping
        parent_ei_var = simplex_parent_mapping.get(i) if has_parent_ei else None
        
        if has_parent_ei and parent_ei_var:
            print(f"  Group {i+1} ({group_type}) has parent EI variable: {parent_ei_var}")
            
            # Find the parent EI variable in the morris_df
            parent_ei_values = None
            if parent_ei_var in morris_df.columns:
                parent_ei_values = morris_df[parent_ei_var].values
                print(f"    Using parent EI values from column: {parent_ei_var}")
            else:
                # Try to find the parent EI variable with different naming
                for col in morris_df.columns:
                    if parent_ei_var in col or col in parent_ei_var:
                        parent_ei_values = morris_df[col].values
                        print(f"    Using parent EI values from column: {col}")
                        break
            
            if parent_ei_values is not None:
                # Scale using parent EI variable: min + proportion * (parent_EI_value - min)
                for var in group:
                    if var in variable_properties:
                        props = variable_properties[var]
                        min_val = props.get('min', 0)
                        if pd.isna(min_val):
                            min_val = 0
                        
                        # New scaling formula: min + proportion * (parent_EI_value - min)
                        morris_df[var] = min_val + morris_df[var] * (parent_ei_values - min_val)
                print(f"    Applied parent-child scaling for group {i+1}")
            else:
                print(f"    Warning: Parent EI variable {parent_ei_var} not found, using default scaling")
                # Fall back to default scaling
                for var in group:
                    if var in variable_properties:
                        props = variable_properties[var]
                        min_val = props.get('min', 0)
                        max_val = props.get('max', 1)
                        if pd.isna(min_val):
                            min_val = 0
                        if pd.isna(max_val):
                            max_val = 1
                        morris_df[var] = min_val + (max_val - min_val) * morris_df[var]
        else:
            # No parent EI variable, use default scaling: min + (max-min) * proportion
            for var in group:
                if var in variable_properties:
                    props = variable_properties[var]
                    min_val = props.get('min', 0)
                    max_val = props.get('max', 1)
                    # If min or max is NaN, default to 0 and 1
                    if pd.isna(min_val):
                        min_val = 0
                    if pd.isna(max_val):
                        max_val = 1
                    morris_df[var] = min_val + (max_val - min_val) * morris_df[var]
    
    elif group_size == 1:
        # Single variable group - scale to actual max value (since sum = 1 for single variable)
        var = group[0]
        if var in variable_properties:
            props = variable_properties[var]
            actual_max = props['max']
            
            # Scale to actual max value if available, otherwise use 1.0
            if not pd.isna(actual_max) and actual_max != 1:
                morris_df[var] = actual_max  # Single variable gets the full max value
            else:
                morris_df[var] = 1.0
        else:
            morris_df[var] = 1.0

print("Applied transformations and reconstructed Simplex variables using Dirichlet distribution")

# --- 8. Process Equivalent Variables ---
print(f"\n=== Processing Equivalent Variables ===")

if equivalent_vars:
    successful_equivalent_mappings = 0
    failed_equivalent_mappings = []
    
    for equiv_info in equivalent_vars:
        var_no = equiv_info['var_no']
        parent_id = equiv_info['parent_id']
        relation_type = equiv_info['relation_type']
        
        # Find parent variable in morris_df
        parent_col = None
        if parent_id in morris_df.columns:
            parent_col = parent_id
        else:
            # Try to find column that starts with parent_id
            for col in morris_df.columns:
                if col.startswith(parent_id + '.') or col.startswith(parent_id):
                    parent_col = col
                    break
        
        if parent_col:
            if relation_type == 'EQ':
                # EQ type: copy parent variable values directly
                morris_df[var_no] = morris_df[parent_col].copy()
                successful_equivalent_mappings += 1
                print(f"  {var_no} -> copied values directly from {parent_col} (EQ relationship)")
            elif relation_type == 'RATIOEQ':
                # RATIOEQ type: copy parent ratio and apply to own min/max range
                if var_no in variable_properties and parent_col in variable_properties:
                    # Get parent variable's range
                    parent_props = variable_properties[parent_col]
                    parent_min = parent_props.get('min', 0)
                    parent_max = parent_props.get('max', 1)
                    
                    # Get equivalent variable's range
                    equiv_props = variable_properties[var_no]
                    equiv_min = equiv_props.get('min', 0)
                    equiv_max = equiv_props.get('max', 1)
                    
                    if not pd.isna(parent_min) and not pd.isna(parent_max) and not pd.isna(equiv_min) and not pd.isna(equiv_max):
                        # Calculate parent's ratio: (value - min) / (max - min)
                        parent_values = morris_df[parent_col].values
                        parent_ratios = (parent_values - parent_min) / (parent_max - parent_min)
                        
                        # Apply ratio to equivalent variable's range: min + ratio * (max - min)
                        morris_df[var_no] = equiv_min + parent_ratios * (equiv_max - equiv_min)
                        successful_equivalent_mappings += 1
                        print(f"  {var_no} -> applied ratio from {parent_col} to own range [{equiv_min}, {equiv_max}] (RATIOEQ relationship)")
                    else:
                        # Fallback to direct copy if range data is missing
                        morris_df[var_no] = morris_df[parent_col].copy()
                        successful_equivalent_mappings += 1
                        print(f"  {var_no} -> fallback to direct copy from {parent_col} (missing range data)")
                else:
                    # Fallback to direct copy if properties are missing
                    morris_df[var_no] = morris_df[parent_col].copy()
                    successful_equivalent_mappings += 1
                    print(f"  {var_no} -> fallback to direct copy from {parent_col} (missing properties)")
        else:
            # Parent not found, use default value based on variable properties
            failed_equivalent_mappings.append(f"{var_no} -> parent {parent_id} not found")
            
            if var_no in variable_properties:
                props = variable_properties[var_no]
                min_val = props.get('min', 0)
                max_val = props.get('max', 1)
                
                if not pd.isna(min_val) and not pd.isna(max_val):
                    default_value = (min_val + max_val) / 2
                    morris_df[var_no] = default_value
                    print(f"  Warning: {var_no} -> using default value {default_value} (parent {parent_id} not found)")
                else:
                    morris_df[var_no] = 0.5
                    print(f"  Warning: {var_no} -> using default value 0.5 (parent {parent_id} not found, no range data)")
            else:
                morris_df[var_no] = 0.5
                print(f"  Warning: {var_no} -> using default value 0.5 (parent {parent_id} not found, no properties)")
    
    print(f"Equivalent variable processing completed:")
    print(f"  - Successful mappings: {successful_equivalent_mappings}/{len(equivalent_vars)}")
    print(f"  - Failed mappings: {len(failed_equivalent_mappings)}")
    
    if failed_equivalent_mappings:
        print("  Failed mappings:")
        for failure in failed_equivalent_mappings:
            print(f"    - {failure}")
else:
    print("No equivalent variables to process")

# --- 9. Apply Parent-Child Scaling for SYNsimplex ---
print(f"\n=== Applying SYNsimplex Parent-Child Scaling ===")

# Parent-child mapping for SYNsimplex scaling
parent_child_mapping = {
    'SYN.29': ['118', '119.COM.118'],
    'SYN.GEN': ['370', '379', '384', '385', '386', '388', '389', '390', '391', '392', '394', '395', '398', '400', '401'],
    'SYN.STOR-MW': ['619', '624', '629', '634']
}

# Apply parent-child scaling (skip variables already processed by new parent-child logic)
for parent_name, child_vars in parent_child_mapping.items():
    # Find parent EI variable
    parent_var = None
    for var in euclidean_independent_vars:
        if parent_name in var:
            parent_var = var
            break
    
    if parent_var and parent_var in morris_df.columns:
        # Find child variables that exist in the DataFrame
        existing_children = [child for child in child_vars if child in morris_df.columns]
        
        if existing_children:
            parent_values = morris_df[parent_var].values
            
            # Check if any of these children were already processed by the new parent-child logic
            already_processed = False
            for group_idx, parent_ei_var in simplex_parent_mapping.items():
                if parent_ei_var == parent_name:
                    # This parent's children were already processed by new logic
                    all_groups = simplex_groups + synsimplex_groups
                    if group_idx < len(all_groups):
                        processed_group = all_groups[group_idx]
                        # Check if any child variable is in the processed group
                        if any(child in processed_group for child in existing_children):
                            already_processed = True
                            print(f"  Skipping {parent_name} children - already processed by new parent-child logic")
                            break
            
            # Only apply old scaling logic if not already processed by new logic
            if not already_processed:
                # Scale each child by parent value
                for child in existing_children:
                    morris_df[child] = morris_df[child] * parent_values
                print(f"  Applied old parent-child scaling for {parent_name} -> {existing_children}")

print("Applied SYNsimplex parent-child scaling")

# --- 10. Apply Linear Transformation Step C (Legacy Equivalent Variables) ---
print(f"\n=== Applying Linear Transformation Step C (Legacy Equivalent Variables) ===")
print("Note: This step is now mostly handled by the new Equivalent Variables processing above.")
print("Keeping this for any remaining equivalent variables that use old naming patterns.")

# Create comprehensive equivalent variable mapping for any remaining old-style equivalent variables
equivalent_variable_mapping = {}

# Build mapping for any old-style equivalent variables (this should be empty now)
# Since we now handle all equivalent variables in the new processing step above,
# this section is kept for compatibility but should not process any variables
old_style_equivalent_vars = []  # Empty list since all equivalent variables are now handled above

print(f"Built equivalent variable mapping for {len(equivalent_variable_mapping)} variables:")

# Track successful and failed mappings
successful_mappings = 0
failed_mappings = []
default_fallbacks = []

# Apply mapping to each old-style equivalent variable (should be none)
for equiv_var in old_style_equivalent_vars:
    if equiv_var not in variable_properties:
        continue
        
    props = variable_properties[equiv_var]
    actual_min = props['min']
    actual_max = props['max']
    
    # Check if we have a mapping
    if equiv_var in equivalent_variable_mapping:
        underlying_var = equivalent_variable_mapping[equiv_var]
        
        if underlying_var in morris_df.columns and underlying_var in variable_properties:
            # Get underlying variable data
            underlying_values = morris_df[underlying_var].values
            underlying_props = variable_properties[underlying_var]
            underlying_min = underlying_props['min']
            underlying_max = underlying_props['max']
            
            # Verify we have valid ranges for both variables
            if (not pd.isna(actual_min) and not pd.isna(actual_max) and
                not pd.isna(underlying_min) and not pd.isna(underlying_max)):
                
                # Normalize underlying variable to [0,1] then scale to equivalent range
                normalized_values = (underlying_values - underlying_min) / (underlying_max - underlying_min)
                morris_df[equiv_var] = actual_min + normalized_values * (actual_max - actual_min)
                successful_mappings += 1
                print(f"  OK {equiv_var} mapped to {underlying_var}")
            else:
                # Missing range data
                failed_mappings.append(f"{equiv_var} -> {underlying_var} (missing range data)")
                if not pd.isna(actual_min) and not pd.isna(actual_max):
                    morris_df[equiv_var] = (actual_min + actual_max) / 2
                    default_fallbacks.append(equiv_var)
                else:
                    morris_df[equiv_var] = 0.5
                    default_fallbacks.append(equiv_var)
        else:
            # Underlying variable not found in dataset
            failed_mappings.append(f"{equiv_var} -> {underlying_var} (underlying var not found)")
            if not pd.isna(actual_min) and not pd.isna(actual_max):
                morris_df[equiv_var] = (actual_min + actual_max) / 2
                default_fallbacks.append(equiv_var)
            else:
                morris_df[equiv_var] = 0.5
                default_fallbacks.append(equiv_var)
    else:
        # No mapping found
        failed_mappings.append(f"{equiv_var} (no mapping pattern found)")
        if not pd.isna(actual_min) and not pd.isna(actual_max):
            morris_df[equiv_var] = (actual_min + actual_max) / 2
            default_fallbacks.append(equiv_var)
        else:
            morris_df[equiv_var] = 0.5
            default_fallbacks.append(equiv_var)

print(f"\n=== Legacy Equivalent Variable Mapping Results ===")
print(f"Successful mappings: {successful_mappings}/{len(old_style_equivalent_vars)}")
print(f"Failed mappings: {len(failed_mappings)}")
print(f"Variables using default fallbacks: {len(default_fallbacks)}")

if failed_mappings:
    print(f"\nFailed mappings:")
    for failure in failed_mappings:
        print(f"  - {failure}")

if default_fallbacks:
    print(f"\nVariables using default fallbacks (may have wrong magnitudes):")
    for var in default_fallbacks:
        print(f"  - {var}")

print("Applied legacy equivalent variables transformation")

# --- 11. Apply Static Variable Handling ---
print(f"\n=== Handling Static Variables ===")

# Process fixed variables with proper values
fixed_variable_assignments = {}
for static_var in static_vars:
    if static_var in variable_properties:
        props = variable_properties[static_var]
        
        # Get the setting value that was stored during reading
        if 'remove_set_value' in props:
            setting = props['remove_set_value']
            
            # Determine fixed value based on setting
            if setting == 'Set as 0':
                fixed_value = 0.0
            elif setting in ['Set to ON', 'Set as ON']:
                fixed_value = 1.0
            elif setting == 'Set to OFF':
                fixed_value = 0.0
            else:
                # For any other 'Set' values, default to 0.0
                print(f"  Warning: Unknown setting '{setting}' for variable {static_var}, defaulting to 0.0")
                fixed_value = 0.0
                
            fixed_variable_assignments[static_var] = fixed_value
            print(f"  Fixed variable {static_var}: {setting} -> {fixed_value}")
            
            # Add to DataFrame - all rows will have the same fixed value
            morris_df[static_var] = fixed_value

print(f"Processed {len(fixed_variable_assignments)} fixed variables")

# --- 12. Save Results ---
import time
import re

# Filter to save target variable types: EI, Simplex, SYNsimplex, and optionally Static
target_columns = []

# Add Euclidean Independent variables
for var in euclidean_independent_vars:
    if var in morris_df.columns:
        target_columns.append(var)

# Add all Simplex variables (from all groups)
for group in simplex_groups + synsimplex_groups:
    for var in group:
        if var in morris_df.columns:
            target_columns.append(var)

# Add static variables (now properly handled)
for static_var in static_vars:
    if static_var in morris_df.columns:
        target_columns.append(static_var)

# Add equivalent variables (now properly handled)
for equiv_info in equivalent_vars:
    var_no = equiv_info['var_no']
    if var_no in morris_df.columns:
        target_columns.append(var_no)

# Remove duplicates while preserving order
seen = set()
unique_target_columns = []
for col in target_columns:
    if col not in seen:
        unique_target_columns.append(col)
        seen.add(col)

# Sort columns by the numeric ID part
def extract_numeric_id(column_name):
    """Extract the leading numeric part from column name for sorting"""
    match = re.match(r'^(\d+)', str(column_name))
    if match:
        return int(match.group(1))
    return float('inf')  # Put non-numeric at the end

def is_synthetic_control(column_name):
    """Check if column is a Synthetic control element (starts with SYN.)"""
    return str(column_name).startswith('SYN.')

# Filter to keep columns that have numeric IDs OR are Synthetic control elements
numeric_id_columns = []
synthetic_control_columns = []
for col in unique_target_columns:
    if extract_numeric_id(col) != float('inf'):  # Has valid numeric ID
        numeric_id_columns.append(col)
    elif is_synthetic_control(col):  # Is a Synthetic control element
        synthetic_control_columns.append(col)

# Sort numeric columns by their numeric ID
sorted_numeric_columns = sorted(numeric_id_columns, key=extract_numeric_id)

# Sort synthetic control columns alphabetically
sorted_synthetic_columns = sorted(synthetic_control_columns)

# Combine: numeric columns first, then synthetic controls
sorted_target_columns = sorted_numeric_columns + sorted_synthetic_columns

print(f"\nColumn filtering:")
print(f"  - Numeric ID columns: {len(sorted_numeric_columns)}")
print(f"  - Synthetic control columns: {len(sorted_synthetic_columns)}")
if sorted_synthetic_columns:
    print(f"  - Synthetic controls included: {sorted_synthetic_columns}")

filtered_df = morris_df[sorted_target_columns]

# --- 12.5. Range Validation and Clipping ---
print(f"\n=== Range Validation and Clipping ===")

# Apply range clipping to ensure all values are within specified bounds
clipped_variables = 0
total_clipped_values = 0

for col in filtered_df.columns:
    if col in variable_properties:
        props = variable_properties[col]
        min_val = props['min']
        max_val = props['max']
        
        # Only apply clipping if we have valid min/max values
        if not pd.isna(min_val) and not pd.isna(max_val):
            original_values = filtered_df[col].copy()
            
            # Count values outside range before clipping
            below_min = (original_values < min_val).sum()
            above_max = (original_values > max_val).sum()
            
            if below_min > 0 or above_max > 0:
                # Apply clipping
                filtered_df[col] = np.clip(filtered_df[col], min_val, max_val)
                clipped_variables += 1
                total_clipped_values += below_min + above_max
                
                print(f"  Clipped {col}: {below_min} values below min ({min_val:.4f}), {above_max} values above max ({max_val:.4f})")

print(f"Range validation completed:")
print(f"  - Variables with clipping applied: {clipped_variables}")
print(f"  - Total values clipped: {total_clipped_values}")

output_filename = 'morris_sampling_design.csv'
filtered_df.to_csv(output_filename, index=False)

print(f"\nFiltered output to include EI, Simplex, SYNsimplex, Static, and Equivalent variables with numeric IDs")
print(f"Original columns: {morris_df.shape[1]}, Filtered columns: {filtered_df.shape[1]}")
print(f"  - Target variables (EI/Simplex/SYNsimplex/Static/Equivalent): {len(unique_target_columns)}")
print(f"  - Variables with numeric IDs: {len(numeric_id_columns)}")
print(f"  - Variables filtered out (no numeric ID): {len(unique_target_columns) - len(numeric_id_columns)}")

# Show which variables were filtered out
filtered_out_vars = [col for col in unique_target_columns if extract_numeric_id(col) == float('inf')]
if filtered_out_vars:
    print(f"  - Filtered out variables: {filtered_out_vars}")

# Show static variables status
static_in_output = [var for var in static_vars if var in filtered_df.columns]
if static_in_output:
    print(f"  - Static variables included: {static_in_output}")
if fixed_variable_assignments:
    print(f"  - Fixed variable assignments: {fixed_variable_assignments}")

# Show first 10 columns to verify sorting
print(f"\nFirst 10 columns after sorting by numeric ID:")
for i, col in enumerate(sorted_target_columns[:10]):
    numeric_id = extract_numeric_id(col)
    # Determine variable type
    if col in euclidean_independent_vars:
        var_type = "EI"
    elif any(col == equiv_info['var_no'] for equiv_info in equivalent_vars):
        var_type = "Equivalent"
    else:
        var_type = "Simplex/SYNsimplex"
    print(f"  {i+1}. {col} (ID: {numeric_id}, Type: {var_type})")

print(f"\nLast 10 columns after sorting by numeric ID:")
for i, col in enumerate(sorted_target_columns[-10:]):
    numeric_id = extract_numeric_id(col)
    # Determine variable type
    if col in euclidean_independent_vars:
        var_type = "EI"
    elif any(col == equiv_info['var_no'] for equiv_info in equivalent_vars):
        var_type = "Equivalent"
    else:
        var_type = "Simplex/SYNsimplex"
    print(f"  {len(sorted_target_columns)-9+i}. {col} (ID: {numeric_id}, Type: {var_type})")

# Count final variables in output
total_output_vars = len(euclidean_independent_vars) + len([var for group in all_groups for var in group]) + len(equivalent_vars)

print(f"\n=== FINAL RESULTS ===")
print(f"Successfully completed all transformation steps!")
print(f"   Step 1: Generated {total_dimensions}D Morris EE sequence (6 trajectories, 4 levels)")
print(f"   Step 2: Applied stick breaking to {len(all_groups)} simplex groups")
print(f"   Step 3: Scaled {len(euclidean_independent_vars)} EI variables to parameter ranges")
print(f"   Step 4: Applied parent-child scaling for SYNsimplex variables")
print(f"   Step 5: Processed {len(equivalent_vars)} equivalent variables")
print(f"   Step 6: Handled {len(fixed_variable_assignments)} fixed variables")
if args.save_ratio_sampling:
    print(f"   Step 6.5: Saved ratio sampling values (0-1 range) to morris_sampling_design_ratios.csv")

print(f"\nFinal Output Statistics:")
print(f"   - Sampling dimensions: {total_dimensions} (232D as required)")
print(f"   - EI variables: {len(euclidean_independent_vars)}")
print(f"   - Simplex groups: {len(simplex_groups)}")
print(f"   - SYNsimplex groups: {len(synsimplex_groups)}")
print(f"   - Equivalent variables: {len(equivalent_vars)}")
print(f"   - Static variables: {len(static_vars)}")
print(f"   - Total DoF: {total_dof}")
print(f"   - Total samples: {filtered_df.shape[0]}")
print(f"   - Total variables in output: {filtered_df.shape[1]} (filtered to numeric-named variables)")
print(f"   - Saved to: {output_filename}")
if args.save_ratio_sampling:
    print(f"   - Ratio sampling saved to: morris_sampling_design_ratios.csv")

print("\nFirst 5 rows of the sampling design (numeric columns only):")
print(filtered_df.head())

# Show some statistics
print(f"\nVariable Range Verification:")
ei_cols = [col for col in morris_df.columns if col in euclidean_independent_vars]
print(f"EI variables (first 3):")
for col in ei_cols[:3]:
    if col in variable_properties:
        expected_min = variable_properties[col]['min']
        expected_max = variable_properties[col]['max']
        actual_min = morris_df[col].min()
        actual_max = morris_df[col].max()
        print(f"  {col}: expected [{expected_min:.4f}, {expected_max:.4f}], actual [{actual_min:.4f}, {actual_max:.4f}]")

# Verify Simplex constraints
expected_sum = "~1.0"
print(f"\nSimplex Constraint Verification (first 3 groups):")
print(f"  Expected sum: {expected_sum}")
for i, group in enumerate(all_groups[:3]):
    if len(group) > 1:
        group_vars_in_df = [var for var in group if var in morris_df.columns]
        if group_vars_in_df:
            group_sums = morris_df[group_vars_in_df].sum(axis=1)
            group_type = "Simplex" if i < len(simplex_groups) else "SYNsimplex"
            print(f"  {group_type} Group {i+1}: sum range [{group_sums.min():.4f}, {group_sums.max():.4f}]")

# Show equivalent variables
if equivalent_vars:
    print(f"\nEquivalent Variables (first 3):")
    for equiv_info in equivalent_vars[:3]:
        var_no = equiv_info['var_no']
        if var_no in morris_df.columns:
            print(f"  {var_no}: range [{morris_df[var_no].min():.4f}, {morris_df[var_no].max():.4f}]")

print(f"\n=== Morris EE Sampling Design Complete ===")
print(f"Successfully implemented 5-step workflow:")
print(f"   Step 1: 232D Morris EE generation")
print(f"   Step 2: Dirichlet for simplex groups") 
print(f"   Step 3: EI variable scaling")
print(f"   Step 4: Parent-child SYNsimplex scaling")
print(f"   Step 5: Equivalent variable transformation")
print(f"Output saved to: {output_filename}")
if args.save_ratio_sampling:
    print(f"Ratio sampling (0-1 values) saved to: morris_sampling_design_ratios.csv")