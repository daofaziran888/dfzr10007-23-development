"""数据采样执行引擎：一次采样严格按四个环节顺序推进。

环节① 配置读取：读采样配置，校验必填字段与口径，输出规范化后的配置。
环节② 随机种子选择：取配置里的「随机种子」，用它构造独立 Random 实例（随机种子落在这一步）。
环节③ 分层字段拆分：按「分层字段」把源数据拆成层，再在每层内用环节②的随机源抽样（分层字段落在这一步）。
环节④ 结果写入：把样本行写入「输出表名」对应的输出表，数据准备流水线随后读同一张表。

约定：
- 同一配置 + 同一源数据，两次执行的样本表逐行相同（确定性抽样）；
- 任一环节缺字段/口径非法时立即终止，返回截至当前的环节轨迹，后续环节不再执行。
"""
from __future__ import annotations

import random
from typing import Any, Callable

from app.sampling.errors import SamplingStageError
from app.sampling.sources import load_source_table

STAGE_CONFIG = 1
STAGE_SEED = 2
STAGE_LAYER = 3
STAGE_WRITE = 4

STAGE_NAMES = {
    STAGE_CONFIG: "配置读取",
    STAGE_SEED: "随机种子选择",
    STAGE_LAYER: "分层字段拆分",
    STAGE_WRITE: "结果写入",
}

# 环节①必须读全的配置字段：缺任何一个都无法说明「怎样得到样本输出表」。
REQUIRED_CONFIG_FIELDS = [
    "配置编号",
    "数据源名称",
    "采样算法",
    "样本比例",
    "随机种子",
    "分层字段",
    "输出表名",
]
SUPPORTED_ALGORITHMS = {"分层随机抽样", "简单随机抽样"}


def _trace_entry(stage: int, action: str, input_data: Any, output: Any) -> dict[str, Any]:
    return {
        "stage": stage,
        "stage_name": STAGE_NAMES[stage],
        "action": action,
        "input": input_data,
        "output": output,
    }


def _fail(stage: int, message: str, trace: list[dict[str, Any]]) -> SamplingStageError:
    return SamplingStageError(stage, STAGE_NAMES[stage], message, trace)


# --------------------------------------------------------------------------- #
# 环节① 配置读取
# --------------------------------------------------------------------------- #
def read_config(raw_config: dict[str, Any], trace: list[dict[str, Any]]) -> dict[str, Any]:
    """读取并规范化采样配置；必填字段缺失或比例/算法非法时停在环节①。"""
    missing = [
        field
        for field in REQUIRED_CONFIG_FIELDS
        if str(raw_config.get(field) or "").strip() == ""
    ]
    if missing:
        raise _fail(STAGE_CONFIG, f"环节①配置读取缺少字段：{'、'.join(missing)}，无法继续", trace)

    config = {field: str(raw_config[field]).strip() for field in REQUIRED_CONFIG_FIELDS}

    algorithm = config["采样算法"]
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise _fail(
            STAGE_CONFIG,
            f"环节①配置读取失败：采样算法「{algorithm}」不在支持范围"
            f"（{ '、'.join(sorted(SUPPORTED_ALGORITHMS)) }）",
            trace,
        )

    try:
        ratio = float(config["样本比例"])
    except ValueError as exc:
        raise _fail(
            STAGE_CONFIG,
            f"环节①配置读取失败：样本比例「{config['样本比例']}」不是数字",
            trace,
        ) from exc
    if not 0 < ratio <= 1:
        raise _fail(
            STAGE_CONFIG,
            f"环节①配置读取失败：样本比例 {ratio} 超出 (0, 1] 范围",
            trace,
        )
    config["_样本比例数值"] = ratio

    # 分层随机抽样必须带分层字段（字段本身存在性在环节③对着源表校验）。
    if algorithm == "分层随机抽样" and not config["分层字段"]:
        raise _fail(STAGE_CONFIG, "环节①配置读取失败：分层随机抽样必须指定分层字段", trace)

    trace.append(
        _trace_entry(
            STAGE_CONFIG,
            "读取并规范化采样配置",
            {field: raw_config.get(field) for field in REQUIRED_CONFIG_FIELDS},
            {
                "配置编号": config["配置编号"],
                "数据源名称": config["数据源名称"],
                "采样算法": config["采样算法"],
                "样本比例": ratio,
                "分层字段": config["分层字段"],
                "输出表名": config["输出表名"],
            },
        )
    )
    return config


# --------------------------------------------------------------------------- #
# 环节② 随机种子选择
# --------------------------------------------------------------------------- #
def prepare_seed(config: dict[str, Any], trace: list[dict[str, Any]]) -> random.Random:
    """取「随机种子」并构造独立随机源；种子缺失/非整数时停在环节②。"""
    raw_seed = str(config.get("随机种子") or "").strip()
    if not raw_seed:
        raise _fail(STAGE_SEED, "环节②随机种子选择失败：配置缺少随机种子，无法继续", trace)
    try:
        seed = int(raw_seed)
    except ValueError as exc:
        raise _fail(
            STAGE_SEED,
            f"环节②随机种子选择失败：随机种子「{raw_seed}」不是整数",
            trace,
        ) from exc

    # 每次执行新建 Random 实例：同样的种子产出同样的随机序列，且不污染全局随机状态。
    rng = random.Random(seed)
    trace.append(
        _trace_entry(
            STAGE_SEED,
            "用随机种子构造独立随机源",
            {"随机种子": seed},
            {"随机源": f"random.Random(seed={seed})", "可复现": True},
        )
    )
    return rng


# --------------------------------------------------------------------------- #
# 环节③ 分层字段拆分
# --------------------------------------------------------------------------- #
def _layer_sample_size(layer_size: int, ratio: float) -> int:
    """每层按比例取整，至少保留 1 行（层非空时），保证小层不被整体丢掉。"""
    return max(1, int(layer_size * ratio))


def split_and_sample(
    config: dict[str, Any],
    rng: random.Random,
    trace: list[dict[str, Any]],
    source_loader: Callable[[str], list[dict[str, Any]]] = load_source_table,
) -> list[dict[str, Any]]:
    """按分层字段拆层并在层内抽样；源表/分层字段缺失时停在环节③。"""
    source_name = config["数据源名称"]
    try:
        source_rows = source_loader(source_name)
    except KeyError as exc:
        raise _fail(
            STAGE_LAYER,
            f"环节③分层字段拆分失败：数据源「{source_name}」未登记，无法读取源数据",
            trace,
        ) from exc
    if not source_rows:
        raise _fail(STAGE_LAYER, f"环节③分层字段拆分失败：数据源「{source_name}」为空表", trace)

    layer_field = config["分层字段"]
    if layer_field not in source_rows[0]:
        raise _fail(
            STAGE_LAYER,
            f"环节③分层字段拆分失败：源表「{source_name}」不存在分层字段「{layer_field}」，无法继续",
            trace,
        )

    # 按字段值拆层：dict 按首次出现顺序保留层顺序，层内行保持源表顺序——两次执行顺序一致。
    layers: dict[Any, list[dict[str, Any]]] = {}
    for row in source_rows:
        layers.setdefault(row[layer_field], []).append(row)

    ratio = config["_样本比例数值"]
    sampled: list[dict[str, Any]] = []
    layer_summary: list[dict[str, Any]] = []
    for layer_value in sorted(layers, key=lambda value: str(value)):
        layer_rows = layers[layer_value]
        take = min(_layer_sample_size(len(layer_rows), ratio), len(layer_rows))
        # rng 在各层间按固定顺序消耗：同种子 + 同源数据 => 同序列 => 逐行可复现。
        chosen = rng.sample(layer_rows, take)
        sampled.extend(chosen)
        layer_summary.append(
            {"分层值": layer_value, "层内行数": len(layer_rows), "抽样行数": take}
        )

    trace.append(
        _trace_entry(
            STAGE_LAYER,
            f"按分层字段「{layer_field}」拆层并在每层内随机抽样",
            {
                "数据源名称": source_name,
                "源表行数": len(source_rows),
                "分层字段": layer_field,
                "样本比例": ratio,
            },
            {"层数": len(layer_summary), "各层抽样": layer_summary, "样本行数": len(sampled)},
        )
    )
    return sampled


# --------------------------------------------------------------------------- #
# 环节④ 结果写入
# --------------------------------------------------------------------------- #
def write_output(
    config: dict[str, Any],
    sampled_rows: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    writer: Callable[[str, list[dict[str, Any]], dict[str, Any]], None],
) -> str:
    """把样本行写入输出表；输出表名缺失时停在环节④。"""
    output_table = str(config.get("输出表名") or "").strip()
    if not output_table:
        raise _fail(STAGE_WRITE, "环节④结果写入失败：配置缺少输出表名，无法落表", trace)

    meta = {
        "配置编号": config["配置编号"],
        "采样算法": config["采样算法"],
        "随机种子": int(config["随机种子"]),
        "分层字段": config["分层字段"],
        "样本比例": config["_样本比例数值"],
    }
    writer(output_table, sampled_rows, meta)
    trace.append(
        _trace_entry(
            STAGE_WRITE,
            "样本行写入输出表（数据准备流水线读取同一张表）",
            {"输出表名": output_table, "待写入行数": len(sampled_rows)},
            {"输出表名": output_table, "已写入行数": len(sampled_rows)},
        )
    )
    return output_table


# --------------------------------------------------------------------------- #
# 串联四个环节
# --------------------------------------------------------------------------- #
def run_pipeline(
    raw_config: dict[str, Any],
    writer: Callable[[str, list[dict[str, Any]], dict[str, Any]], None],
    source_loader: Callable[[str], list[dict[str, Any]]] = load_source_table,
) -> dict[str, Any]:
    """按 ①配置读取 → ②随机种子选择 → ③分层字段拆分 → ④结果写入 顺序执行一次采样。

    成功返回 trace / output_table / row_count / rows；
    失败抛 SamplingStageError，携带截至失败环节的轨迹（失败环节本身也记录在 message 语义里）。
    """
    trace: list[dict[str, Any]] = []

    config = read_config(raw_config, trace)          # 环节①
    rng = prepare_seed(config, trace)                 # 环节②：随机种子落在这一步
    sampled_rows = split_and_sample(config, rng, trace, source_loader)  # 环节③：分层字段落在这一步
    output_table = write_output(config, sampled_rows, trace, writer)     # 环节④

    return {
        "ok": True,
        "配置编号": config["配置编号"],
        "output_table": output_table,
        "row_count": len(sampled_rows),
        "rows": sampled_rows,
        "trace": trace,
    }
