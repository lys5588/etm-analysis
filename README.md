# ETM 数据采样与采集运行指南

本目录是可独立运行的 ETM Morris 采样与 API 数据采集包。所有命令都应在本目录（即包含 `whole_process.py` 的目录）执行，代码依赖相对路径，不要从上级目录启动。

## 1. 环境准备

建议使用 Python 3.9–3.11，然后安装依赖。原始依赖固定了 `pyyaml==6.0`，在 Python 3.12 上可能需要编译并安装失败，因此交接运行环境优先使用 Python 3.9–3.11：

```bash
python -m pip install -r requirements.txt
```

真实请求 ETM 前，将 `config/local.settings.yml.example` 复制为 `config/local.settings.yml`，并填写个人 ETM token。不要把 `local.settings.yml` 发送给其他人或提交到 Git。

程序默认请求 ETM production API。当前场景地区、年份和基础 scenario ID 写在 `generate_input_addup.py` 中，分别为 `UK_united_kingdom`、`2020` 和 `1362080`。如运行对象不同，需要先由维护人员确认这些值。

## 2. 初始输入文件

### 核心变量设定

`variable_data.csv`

这是整个流程的主要输入，定义需要采样的变量、变量 Min/Max、Euclidean Independent、Equivalent、Simplex/SYNsimplex 分组、固定值和 Synthetic 控制元素。Simplex 分组依赖 CSV 中的行顺序，不要随意排序。

### 父子约束

`synthetic_refer.csv`

定义 Synthetic 控制变量与子变量的对应关系，用于后处理时限制子变量不能超过父变量。

### ETM 变量映射与查询配置

- `query/database_index.csv`：将数字变量编号映射为 ETM API 的 `database_item` 名称。
- `query/all_var_real.csv`：随包保留的 ETM 变量参考表；当前代码接口保留该路径，但实际映射使用 `database_index.csv`。
- `data/input/queries.csv`：每个样本要请求的 ETM gquery 指标。
- `data/input/data_downloads.csv`：每个样本要下载的数据，目前为 `energy_flow` 和 `merit_order`。
- `data/input/heat_network_orders.csv`：场景工具的可选配置文件。

## 3. 完整运行流程

### 第一步：生成 Morris 采样和组内 ratio

```bash
python whole_process.py --save_ratio_sampling
```

输入：

- `variable_data.csv`

输出：

- `morris_sampling_design_ratios.csv`：0–1 ratio 采样，下一步真正使用。
- `morris_sampling_design.csv`：经过范围和变量关系转换后的采样结果，主要用于检查。

当前随包的 `variable_data.csv` 预期得到 226 个采样维度和 1362 个样本。修改变量设定后，维度和样本数可能变化。

### 第二步：生成 param_encoding

```bash
python data_transform.py
```

输入：

- `morris_sampling_design_ratios.csv`
- `variable_data.csv`
- `synthetic_refer.csv`

处理内容：将 ratio 转成变量实际值，转置为“行=变量、列=样本”，并执行 Synthetic 父子上限处理。

输出：

- `query/param_encoding_real.csv`：下一步使用，不含 Synthetic 控制行。
- `query/param_encoding_full.csv`：包含控制行，用于核对。

### 第三步：生成 ETM 场景输入

```bash
python generate_input_addup.py
```

输入：

- `query/param_encoding_real.csv`
- `query/database_index.csv`

输出：

- `data/input/scenario_list.csv`：样本场景列表。
- `data/input/scenario_settings.csv`：每个样本对应的 ETM input 设置。
- `query/min_max_data.csv`：本轮使用的 Min/Max 数据。
- `query/min_max_errors.csv`：仅在发生截断时生成或更新。

注意：后续 task 执行会反复覆盖 `data/input/scenario_list.csv` 和 `data/input/scenario_settings.csv`。如果需要保留完整主输入，应在拆分前另行备份这两个文件。

### 第四步：拆分 task

首次运行或确认开始全新一轮任务后执行：

```bash
python scenario_from_csv_opt.py --force-split --batch-size 1
```

输入：

- `data/input/scenario_list.csv`
- `data/input/scenario_settings.csv`

输出结构：

```text
data/tasks/1/scenario_list.csv
data/tasks/1/scenario_settings.csv
data/tasks/2/...
```

`--force-split` 会删除 `data/tasks` 中已有的 task 和 task 结果。只有在已备份旧结果或明确开始新一轮运行时才可使用。

### 第五步：顺序请求 ETM

```bash
python scenario_from_csv_opt.py --run
```

查看进度：

```bash
python scenario_from_csv_opt.py --status
```

每个 task 会调用 `scenario_from_csv.py`，更新 ETM 场景、执行 `queries.csv` 中的查询，并下载 `data_downloads.csv` 中定义的数据。

预期输出：

- `data/tasks/<task编号>/scenario_outcomes.csv`
- `data/output/sample_<样本编号>/sample_<样本编号>_energy_flow.csv`
- `data/output/sample_<样本编号>/sample_<样本编号>_merit_order.csv`

任务按顺序修改同一个基础 ETM scenario，不要同时启动多个 `--run` 进程。失败任务会每 5 秒持续重试；如果持续失败，应手动停止并检查 token、网络和变量设置。

### 第六步：合并查询结果

```bash
python merge_sample_outcomes.py
```

输入：

- `data/tasks/*/scenario_outcomes.csv`

最终输出：

- `data/output/sample_outcomes_merged.csv`

该文件是主要交付结果，格式为“行=ETM 查询指标、列=sample、最后一列=unit”。不要使用 `scenario_from_csv_opt.py --merge` 生成的纵向追加文件作为最终分析数据。

## 4. 最终交付文件

完整运行后，至少交付以下文件：

1. `data/output/sample_outcomes_merged.csv`：最终 ETM 指标矩阵。
2. `variable_data.csv`：本轮变量设定和范围。
3. `query/param_encoding_real.csv`：本轮实际发送前的样本参数矩阵。

如果需要能量流和 merit order 明细，还应同时交付：

- `data/output/sample_*/sample_*_energy_flow.csv`
- `data/output/sample_*/sample_*_merit_order.csv`

建议将本轮需要交付的三个核心文件复制到 `report/`，再统一打包；`data/output` 明细文件体积可能很大，应单独归档。

## 5. 推荐命令汇总

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

不要直接无参数运行 `scenario_from_csv_opt.py`；无参数会默认执行拆分、请求和内置纵向合并，不适合作为交接后的标准运行方式。
