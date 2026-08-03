import csv
import copy
import os
from typing import List, Dict, Any, Optional


def is_float(value):
    if type(value) == float:
        return True
    try:
        float(value.replace(',',''))
        return True
    except:
        return False

def dfs_search(dict,key,is_min:bool):
    value = None
    if key not in dict.keys():
        return
    if key == "SYN.20":
        print(dict[key])
    if is_min:
        value = dict[key]["min_value"]
    else:
        value = dict[key]["max_value"]
    if is_float(value):
        if type(value)==float:
            return value
        else:
            return float(value.replace(',',''))
    else:
        if type(value) == str and value.split('.')[0] == "VAR":
            id = value.split('.')[1]
        else:
            id = value
        return dfs_search(dict,id,is_min)

class ScenarioList:
    """
    Manages data and operations for scenario_list.csv.
    """
    def __init__(self):
        self._headers = [
            'short_name', 'title', 'area_code', 'end_year', 'description', 
            'id', 'keep_compatible', 'curve_file'
        ]
        self._data: List[Dict[str, Any]] = []

    def add_row(self, short_name: str, title: str, area_code: str, end_year: str,
                description: str, id_val: Optional[str], keep_compatible: str, 
                curve_file: Optional[str]):
        """Add a row of data to scenario_list."""
        # Convert boolean value to uppercase string to match common CSV format
        keep_compatible_str = str(keep_compatible)
        
        # Convert None values to empty strings
        row_dict = {
            'short_name': short_name or '',
            'title': title or '',
            'area_code': area_code or '',
            'end_year': end_year or '',
            'description': description or '',
            'id': id_val or '',
            'keep_compatible': keep_compatible_str,
            'curve_file': curve_file or ''
        }
        self._data.append(row_dict)

    def save_to_csv(self, filepath: str):
        """Save data to CSV file."""
        print(f"Saving scenario_list data to {filepath}...")
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self._headers)
                writer.writeheader()
                writer.writerows(self._data)
            print("scenario_list.csv saved successfully.")
        except IOError as e:
            print(f"Error: Unable to write file {filepath}. Reason: {e}")

class ScenarioSettings:
    """
    Manages data and operations for scenario_settings.csv.
    """
    def __init__(self):
        self._input_column: List[str] = []
        self._data_columns: List[List[Any]] = []

    def set_input_column(self, data: List[str]):
        """Set data for the first 'input' column."""
        if not self._input_column:
            self._input_column = data

    def add_column(self, column_name: str, data: List[Any]):
        """Add a scenario's data by column."""
        self._data_columns[column_name] = data
    
    def convert(self, scenario_name_list: List[str], scaneria_data: Dict[str, List[Any]],scanerio_minmax: Dict[str, Dict[str, Any]],minmax_index_var_id_hash: Dict[str, int]):
        min_max_error_index = []
        self._input_column = scenario_name_list
        for key in scaneria_data.keys():
            scaneria_data_item_copy = copy.deepcopy(scaneria_data[key])
            scaneria_data[key] = [min(scanerio_minmax[key]["max_value"], value) for value in scaneria_data[key]]
            scaneria_data[key] = [max(scanerio_minmax[key]["min_value"], value) for value in scaneria_data[key]]
            # Check if data has changed due to min/max constraints
            if scaneria_data_item_copy != scaneria_data[key]:
                min_max_error_index.append([minmax_index_var_id_hash[key], key])
            self._data_columns.append([key,scaneria_data[key]])
        # Save min_max_error_index to CSV file
        if min_max_error_index:
            error_filepath = "query/min_max_errors.csv"
            try:
                with open(error_filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['index', 'variable_name'])  # Write header
                    writer.writerows(min_max_error_index)  # Write error data
                print(f"min_max_errors.csv saved successfully to {error_filepath}")
            except IOError as e:
                print(f"Error: Unable to write file {error_filepath}. Reason: {e}")
        print(min_max_error_index)
        
    def extra_dict(self,len_column):        
        interconnection_header = "electricity_interconnector"
        interconnection_value_type = ["capacity","import_availability","export_availability","co2_emissions_present","co2_emissions_future","marginal_costs"]
        interconnection_id = ["1","2","3","4","5","6","7","8","9","10","11","12"]
        interconnection_dict = {}
        interconnection_value = [0,0,0,0,0,0.1]
        for i in range(len(interconnection_value_type)):
            for id in interconnection_id:
                interconnection_dict[interconnection_header+f"_{id}_"+interconnection_value_type[i]] = [interconnection_value[i]] * len_column
        
        interconnection_dict["agriculture_lpg_in_crude_oil_share"] = [0.0] * len_column
        interconnection_dict["industry_final_demand_for_other_food_steam_hot_water_share"] = [0.0] * len_column
        interconnection_dict["transport_truck_using_gasoline_mix_share"] = [0.0] * len_column
        interconnection_dict["industry_final_demand_for_other_paper_steam_hot_water_share"] = [0.0] * len_column
        interconnection_dict["industry_final_demand_for_chemical_other_steam_hot_water_share"] = [0.0] * len_column
        interconnection_dict["industry_lpg_in_crude_oil_share"] = [0.0] * len_column
        interconnection_dict["transport_ship_using_electricity_share"] = [0.0] * len_column
        interconnection_dict["agriculture_final_demand_ht_central_steam_hot_water_share"] = [0.0] * len_column
        interconnection_dict["industry_final_demand_for_chemical_refineries_steam_hot_water_share"] = [0.0] * len_column
        
        # interconnection_dict[""] = [0.0] * len_column
        return interconnection_dict


    def save_to_csv(self, filepath: str,add_extra_data:bool=True):
        """Restructure and save data to CSV file."""
        print(f"Saving scenario_settings data to {filepath}...")
        if not self._input_column:
            print("Error: 'input' column data is empty, cannot save scenario_settings.csv.")
            return
            
        # Sort by column names to ensure consistent output order
        column_names = self._input_column
        headers = ['input'] + column_names

        # print(self._input_column)
        # for item in self._data_columns:
        #     if len(item[1]) != len(self._input_column):
        #         print(item[0],len(item[1]))
        # return

        

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                
                # Write data row by row (updated variable data)
                for i in range(len(self._data_columns)):
                    row = [self._data_columns[i][0]]  # First element as input column
                    if self._data_columns[i][0] == 'electricity_interconnector_1_capacity':
                        continue
                    if self._data_columns[i][0] == 'settings_enable_storage_optimisation_households_flexibility_p2p_electricity':
                        for _ in range(len(self._data_columns[i][1])):
                            row.append("optimizing_storage_households")
                        writer.writerow(row)
                        continue
                    for j in range(1, len(self._data_columns[i])):
                        # if len(self._data_columns[i])>1:
                        #     print(self._data_columns[i])
                        # Perform numerical conversion on variable values, self._data_columns[i][1] is a list containing multiple data items
                        data_list = self._data_columns[i][1]
                        for k in range(len(data_list)):
                            converted_value = data_list[k]
                            row.append(converted_value)
                    writer.writerow(row)
                # Write additional data
                if add_extra_data:
                    extra_data_dict = self.extra_dict(len(column_names))
                    for key in extra_data_dict.keys():
                        row = [key]
                        for j in range(0, len(extra_data_dict[key])):
                            row.append(extra_data_dict[key][j])
                        writer.writerow(row)
            print("scenario_settings.csv saved successfully.")
        except IOError as e:
            print(f"Error: Unable to write file {filepath}. Reason: {e}")
def is_special_row(row: List[str],var_no: int) -> bool:
    """
    Special check function to determine whether a row of data needs to be processed.
    
    Args:
        row: A row of data from CSV file
        
    Returns:
        bool: True means the row needs processing, False means skip the row
    """
    pass_var = [160,163,170,172,176,177,190,192,196,198,252,253,254,255,674,675,676,677,705,717,924,925,927]
    pass_var1 = list(range(678, 694))
    pass_var2 = list(range(698, 703))
    # print(row)
    if row[8]== 'Interconnector 2 to 12':
        return True
    elif row[9]== 'Merit order':
        return True
    elif row[7]== 'Merit order':
        return True
    elif row[9].startswith('Merit order'):
        return True
    elif var_no in pass_var or var_no in pass_var1 or var_no in pass_var2:
        return True
    elif row[12] == "InVar":
        return True
    else:
        return False

def process_data(all_var_path: str, param_encoding_path: str, database_index_path: str,start_sample_index: int=0):
    """
    Main processing function that executes all data conversion steps.
    """
    # 1. Initialize
    print("Starting data processing...")
    scenario_list = ScenarioList()
    scenario_settings = ScenarioSettings()
    
    database_index = {}
    with open(database_index_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        for row in reader:
            if len(row) >= 8 and row[7] != '':  # Ensure row has at least 2 columns (A and H)
                database_index[int(row[0])] = row[7]  # Column A is row[0], column H is row[7]
    
    # 2. Create output directory
    output_dir = 'data/input'
    os.makedirs(output_dir, exist_ok=True)

    # 3. First read param_encoding to confirm var no. of variables that need to be modified
    variable_var_no = []
    print(f"Reading {param_encoding_path} and confirming var no. that need to be processed...")
    try:
        with open(param_encoding_path, 'r', encoding='utf-8') as f:
            param_data = list(csv.reader(f))
    except FileNotFoundError:
        print(f"Error: Input file {param_encoding_path} not found.")
        return
    except Exception as e:
        print(f"Error occurred while processing {param_encoding_path}: {e}")
        return

    # Identify valid modification rows in param_encoding
    variable_var_no = []
    if len(param_data) > 1:
        for i, row in enumerate(param_data[2:], start=2):
            try:
                # Column A must be an integer
                var_no_str = row[0].strip()
                # Handle variable names that may contain '.' separator, take the number from the first part
                if '.' in var_no_str:
                    full_data_index = int(var_no_str.split('.')[0])
                else:
                    full_data_index = int(var_no_str)
                variable_var_no.append(full_data_index)
            except (ValueError, IndexError):
                continue
    

    # 5. Read param_encoding.csv
    print(f"Reading {param_encoding_path}...")
    try:
        with open(param_encoding_path, 'r', encoding='utf-8') as f:
            param_data = list(csv.reader(f))
    except FileNotFoundError:
        print(f"Error: Input file {param_encoding_path} not found.")
        return
    except Exception as e:
        print(f"Error occurred while processing {param_encoding_path}: {e}")
        return

    # Identify valid modification rows in param_encoding
    valid_param_rows = []
    min_max_dict={}
    minmax_var_id_index_hash={}
    minmax_index_var_id_hash={}
    if len(param_data) > 1:
        for i, row in enumerate(param_data[1:], start=1):
            try:
                # Column A must be an integer
                var_no_str = row[0].strip()
                if var_no_str == "SYNCOM.39":
                    print(row[2],row[3])
                min_max_dict[var_no_str] = {"min_value": row[2], "max_value": row[3]}
                # Handle variable names that may contain '.' separator, take the number from the first part
                if '.' in var_no_str:
                    full_data_index = int(var_no_str.split('.')[0])
                elif var_no_str == '' or var_no_str == 'END':
                    break
                else:
                    full_data_index = int(var_no_str)
                min_max_dict[var_no_str] = {"min_value": row[2], "max_value": row[3]}
                # Build a hashtable, this is a subset
                try:
                    id = int(var_no_str.split('.')[0])
                    minmax_var_id_index_hash[id] =  var_no_str
                except:
                    pass

                valid_param_rows.append({'row_index': i, 'full_data_index': full_data_index})
            except (ValueError, IndexError):
                continue
    
    # Perform depth-first traversal to modify minmax_dict data
    for key in min_max_dict.keys():
        min_max_dict[key]["min_value"] = dfs_search(min_max_dict,key,True)
        min_max_dict[key]["max_value"] = dfs_search(min_max_dict,key,False)
    # print(min_max_dict)
    # print(minmax_var_id_index_hash)
    # Save min_max_dict to CSV file
    min_max_csv_path = "query/min_max_data.csv"
    print(f"Saving min_max_dict data to {min_max_csv_path}...")
    try:
        with open(min_max_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(['variable_key', 'min_value', 'max_value'])
            # Write data
            for id , index in minmax_var_id_index_hash.items():
                key = index
                value_dict = min_max_dict[key]
                writer.writerow([key, value_dict['min_value'], value_dict['max_value']])
        print(f"min_max_dict data saved to {min_max_csv_path}")
    except IOError as e:
        print(f"Error: Unable to write file {min_max_csv_path}. Reason: {e}")
    # print(minmax_var_id_index_hash)
    # exit()


    # Transpose data for column-wise traversal
    transposed_param_data = list(map(list, zip(*param_data)))

    # 6. Traverse scenario columns and generate data
    # First create a dictionary based on static data
    scaneria_data = {}
    scanerio_minmax={}
    scanerio_name_list = []
    # for item in static_data:
    #     scaneria_data[item[2]] = []
    for var_no in variable_var_no:
        if var_no in database_index.keys():
            scaneria_data[database_index[var_no]] = []
    if len(transposed_param_data) < 5:
        print("Warning: No scenario data columns found in param_encoding.csv.")
    else:
        # Start traversing from the 4th column
        
        for k, column_data in enumerate(transposed_param_data[(4+start_sample_index):]):
            # Actually need to traverse each sample at a time
            if len(column_data) < 2 or  column_data[1].strip() =='':
                break # Stop if the fourth row of the column is empty

            scenario_name = f"sample_{k}"
            scanerio_name_list.append(scenario_name)
            print(f"Processing scenario: {scenario_name}...")
            

            # Add static constants
            # for item in static_data:
            #     scaneria_data[item[2]].append(item[1])
            # print(scaneria_data)
            
            # Add variables
            for param_info in valid_param_rows:
                # Look up database name in full_data by index
                if param_info['full_data_index'] not in database_index.keys():
                    # print(f"not found {param_info['full_data_index']}")
                    continue
                db_name = database_index[param_info['full_data_index']]
                db_val = float(column_data[param_info['row_index']].strip().replace(',',''))
                scaneria_data[db_name].append(db_val)
                
                minmax_index_var_id_hash[db_name] = param_info['full_data_index']
                min_max_index = minmax_var_id_index_hash[param_info['full_data_index']]
                min_value,max_value = min_max_dict[min_max_index]["min_value"],min_max_dict[min_max_index]["max_value"]
                scanerio_minmax[db_name] = {"min_value": min_value, "max_value": max_value}
                if k==0:
                    print("minmax",param_info['full_data_index'],min_value,max_value)

            # c. 更新 scenario_list
            scenario_list.add_row(
                short_name=scenario_name,
                title="Scenario_sample",
                area_code="UK_united_kingdom",
                end_year="2020",
                description="sample",
                id_val="1362080",
                keep_compatible="False",
                curve_file=None
            )
            
        # print(valid_param_rows)
        scenario_settings.convert(scanerio_name_list, scaneria_data,scanerio_minmax,minmax_index_var_id_hash)

    # 6. Save final results
    scenario_list.save_to_csv(os.path.join(output_dir, 'scenario_list.csv'))
    scenario_settings.save_to_csv(os.path.join(output_dir, 'scenario_settings.csv'))
    
    print("\nAll processing completed!")


if __name__ == '__main__':
    # Define input filenames
    all_var_file = 'query/all_var_real.csv'
    param_encoding_file = 'query/param_encoding_real.csv'
    database_index_file = 'query/database_index.csv'

    # Execute main function
    start_sample_index=0
    process_data(all_var_file, param_encoding_file, database_index_file,start_sample_index)





    
