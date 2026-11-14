"""采样执行环节级异常：出错时携带已经走到的环节轨迹，方便前端按环节展示卡点。"""
from __future__ import annotations

from typing import Any


class SamplingStageError(Exception):
    """在某个采样环节终止时抛出，stage 为环节编号（1~4），trace 为截至失败前的环节轨迹。"""

    def __init__(self, stage: int, stage_name: str, message: str, trace: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.stage = stage
        self.stage_name = stage_name
        self.trace = trace
