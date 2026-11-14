"""数据源登记表：采样环节①按「数据源名称」从这里取数。

真实项目里这里会换成数据库/对象存储访问；当前用标准库构造一份稳定的内存明细表，
保证不依赖外部环境、且每次取到的数据行顺序完全一致，采样结果才能逐行复现。
"""
from __future__ import annotations

from typing import Any

# 客户画像明细表：60 行，含 region 分层字段，供 SAMP-0001 按地区分层抽样。
_REGIONS = ["华东", "华北", "华南", "西南"]
_LEVELS = ["普通", "银卡", "金卡", "钻石"]


def _build_customer_profile() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(60):
        rows.append(
            {
                "customer_id": f"C{index + 1:04d}",
                "region": _REGIONS[index % len(_REGIONS)],
                "level": _LEVELS[index % len(_LEVELS)],
                # 固定公式生成数值字段，避免随机数让源数据本身变得不可复现。
                "age": 18 + (index * 7) % 45,
                "annual_amount": 1000 + index * 137,
            }
        )
    return rows


# 数据源名称 -> 明细表（与采样配置里的「数据源名称」字段对应）。
SOURCE_TABLES: dict[str, list[dict[str, Any]]] = {
    "客户画像明细表": _build_customer_profile(),
}


def load_source_table(source_name: str) -> list[dict[str, Any]]:
    """环节①调用：按数据源名称取数；未登记的数据源抛出 KeyError，由调用方归入环节①失败。"""
    if source_name not in SOURCE_TABLES:
        raise KeyError(source_name)
    # 返回深拷贝，采样过程不会污染登记表里的原始数据。
    return [dict(row) for row in SOURCE_TABLES[source_name]]
