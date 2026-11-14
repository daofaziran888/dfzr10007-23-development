"""数据采样执行子系统：把一次采样拆成配置读取、随机种子选择、分层字段拆分、结果写入四个环节。"""
from app.sampling.engine import (
    STAGE_CONFIG,
    STAGE_LAYER,
    STAGE_SEED,
    STAGE_WRITE,
    SamplingStageError,
    run_pipeline,
)
from app.sampling.sources import SOURCE_TABLES, load_source_table

__all__ = [
    "STAGE_CONFIG",
    "STAGE_SEED",
    "STAGE_LAYER",
    "STAGE_WRITE",
    "SamplingStageError",
    "run_pipeline",
    "SOURCE_TABLES",
    "load_source_table",
]
