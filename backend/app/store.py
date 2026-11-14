"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
"""
from __future__ import annotations

from typing import Any

from app.seed import SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    # ------------------------------------------------------------------ #
    # 采样输出表：采样环节④写入、数据准备流水线按同一张表名读取
    # ------------------------------------------------------------------ #
    def save_output_table(self, table_name: str, rows: list[dict[str, Any]], meta: dict[str, Any]) -> None:
        """按表名覆盖写入样本输出表：同配置重复执行时替换旧表，保证读到的永远是最新一次结果。"""
        self._tables.setdefault("__output_tables__", {})[table_name] = {
            "table_name": table_name,
            "rows": [dict(row) for row in rows],
            "meta": dict(meta),
        }

    def get_output_table(self, table_name: str) -> dict[str, Any] | None:
        return self._tables.get("__output_tables__", {}).get(table_name)

    def list_output_tables(self) -> list[dict[str, Any]]:
        return [
            {"table_name": table["table_name"], "row_count": len(table["rows"]), "meta": table["meta"]}
            for table in self._tables.get("__output_tables__", {}).values()
        ]

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
