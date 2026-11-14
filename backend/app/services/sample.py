"""数据采样管理业务规则：状态流转、字段校验，以及四环节采样执行的装配。"""
from __future__ import annotations

from typing import Any

from app.sampling import SamplingStageError, run_pipeline
from app.store import store

MODULE = "sample"
REQUIRED_FIELDS = ["配置编号", "数据源名称", "采样算法"]
STATUS_ORDER = ["草稿", "已启用", "已暂停", "已关闭"]
ACTION_RULES = {"启用采样": "草稿", "暂停采样": "已启用", "关闭采样": "已暂停"}
NEGATIVE_ACTIONS = []


class SampleService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("配置编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"采样配置 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于数据采样管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"采样配置已{action}"

    # ------------------------------------------------------------------ #
    # 四环节采样执行：①配置读取 → ②随机种子选择 → ③分层字段拆分 → ④结果写入
    # ------------------------------------------------------------------ #
    def execute_sampling(self, entry_id: int) -> dict[str, Any]:
        entry = self.get_entry(entry_id)
        if entry is None:
            return {
                "ok": False,
                "stage": 0,
                "stage_name": "配置读取",
                "message": f"采样配置 {entry_id} 不存在或已归档，环节①配置读取无法开始",
                "trace": [],
            }

        # 写入前的归属校验：输出表名一旦被其他配置占用，就停在环节④之前，不覆盖别人的表。
        output_table = str(entry.get("输出表名") or "").strip()
        owner = self._find_output_table_owner(output_table, exclude_id=entry_id)
        if output_table and owner is not None:
            return {
                "ok": False,
                "stage": 4,
                "stage_name": "结果写入",
                "message": (
                    f"环节④结果写入失败：输出表「{output_table}」已被采样配置「{owner}」占用，"
                    "拒绝覆盖"
                ),
                "trace": [],
            }

        def writer(table_name: str, rows: list[dict[str, Any]], meta: dict[str, Any]) -> None:
            store.save_output_table(table_name, rows, meta)

        try:
            result = run_pipeline(dict(entry), writer)
        except SamplingStageError as exc:
            return {
                "ok": False,
                "stage": exc.stage,
                "stage_name": exc.stage_name,
                "message": str(exc),
                "trace": exc.trace,
            }
        result["message"] = (
            f"采样完成：{result['row_count']} 行已写入输出表「{result['output_table']}」"
        )
        return result

    def list_output_tables(self) -> list[dict[str, Any]]:
        return store.list_output_tables()

    def get_output_table(self, table_name: str) -> dict[str, Any] | None:
        return store.get_output_table(table_name)

    def _find_output_table_owner(self, output_table: str, *, exclude_id: int) -> str | None:
        if not output_table:
            return None
        for row in store.rows(MODULE):
            if int(row.get("id", 0)) == exclude_id:
                continue
            if str(row.get("输出表名") or "").strip() == output_table:
                return str(row.get("配置编号") or row.get("id"))
        return None
