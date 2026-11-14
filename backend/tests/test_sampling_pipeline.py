"""采样四环节测试：不依赖 httpx/TestClient，直接驱动服务层与引擎。

覆盖：
1. SAMP-0001（seed=42、layer=region）两次执行逐行相同；
2. 随机种子落在环节②、分层字段落在环节③，轨迹顺序与输入输出完整；
3. 缺字段分别停在环节①/②/③；
4. 数据准备流水线读取同一张输出表，内容与采样结果一致。
"""
from __future__ import annotations

import unittest

from app.sampling import SamplingStageError, run_pipeline
from app.services.etl import EtlService
from app.services.sample import SampleService
from app.store import store

SAMP_0001 = {
    "配置编号": "SAMP-0001",
    "数据源名称": "客户画像明细表",
    "采样算法": "分层随机抽样",
    "样本比例": "0.2",
    "随机种子": "42",
    "分层字段": "region",
    "输出表名": "test_samp_0001_output",
}


class SamplingPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        # 每个用例独立的内存写入器，避免用例间互相污染。
        self.written: dict[str, dict] = {}

        def writer(table_name: str, rows: list[dict], meta: dict) -> None:
            self.written[table_name] = {"rows": rows, "meta": meta}

        self.writer = writer

    def test_samp_0001_runs_four_stages_in_order(self) -> None:
        result = run_pipeline(dict(SAMP_0001), self.writer)
        self.assertTrue(result["ok"])
        stages = [item["stage"] for item in result["trace"]]
        self.assertEqual(stages, [1, 2, 3, 4])
        names = [item["stage_name"] for item in result["trace"]]
        self.assertEqual(names, ["配置读取", "随机种子选择", "分层字段拆分", "结果写入"])
        # 60 行源表、4 个 region 层、每层 15 行 × 20% => 每层 3 行，共 12 行。
        self.assertEqual(result["row_count"], 12)
        self.assertEqual(result["output_table"], "test_samp_0001_output")

    def test_seed_lives_in_stage_two_and_layer_in_stage_three(self) -> None:
        result = run_pipeline(dict(SAMP_0001), self.writer)
        seed_trace = result["trace"][1]
        self.assertEqual(seed_trace["stage"], 2)
        self.assertEqual(seed_trace["input"], {"随机种子": 42})
        self.assertTrue(seed_trace["output"]["可复现"])

        layer_trace = result["trace"][2]
        self.assertEqual(layer_trace["stage"], 3)
        self.assertEqual(layer_trace["input"]["分层字段"], "region")
        self.assertEqual(layer_trace["output"]["层数"], 4)
        # 每个地区层 15 行，抽 20% => 3 行。
        self.assertTrue(all(item["抽样行数"] == 3 for item in layer_trace["output"]["各层抽样"]))

    def test_same_config_reproduces_row_by_row(self) -> None:
        first = run_pipeline(dict(SAMP_0001), self.writer)
        second = run_pipeline(dict(SAMP_0001), self.writer)
        self.assertEqual(first["rows"], second["rows"])
        # 逐行比较 customer_id 序列，明确「逐行相同」而不仅是集合相同。
        first_ids = [row["customer_id"] for row in first["rows"]]
        second_ids = [row["customer_id"] for row in second["rows"]]
        self.assertEqual(first_ids, second_ids)

    def test_different_seed_changes_sample(self) -> None:
        other = dict(SAMP_0001, 随机种子="43")
        first = run_pipeline(dict(SAMP_0001), self.writer)
        changed = run_pipeline(other, self.writer)
        self.assertNotEqual(
            [row["customer_id"] for row in first["rows"]],
            [row["customer_id"] for row in changed["rows"]],
        )

    def test_missing_required_field_stops_at_stage_one(self) -> None:
        broken = dict(SAMP_0001)
        del broken["数据源名称"]
        with self.assertRaises(SamplingStageError) as ctx:
            run_pipeline(broken, self.writer)
        self.assertEqual(ctx.exception.stage, 1)
        self.assertIn("数据源名称", str(ctx.exception))
        # 停在环节①：后面三个环节都没有轨迹。
        self.assertEqual(ctx.exception.trace, [])
        self.assertEqual(self.written, {})

    def test_bad_seed_stops_at_stage_two(self) -> None:
        broken = dict(SAMP_0001, 随机种子="自动")
        with self.assertRaises(SamplingStageError) as ctx:
            run_pipeline(broken, self.writer)
        self.assertEqual(ctx.exception.stage, 2)
        # 环节①已完成、环节②失败：轨迹里只保留环节①。
        self.assertEqual([item["stage"] for item in ctx.exception.trace], [1])
        self.assertEqual(self.written, {})

    def test_missing_layer_field_stops_at_stage_three(self) -> None:
        broken = dict(SAMP_0001, 分层字段="city")
        with self.assertRaises(SamplingStageError) as ctx:
            run_pipeline(broken, self.writer)
        self.assertEqual(ctx.exception.stage, 3)
        self.assertIn("city", str(ctx.exception))
        # 环节①②已完成、环节③失败：轨迹保留前两步。
        self.assertEqual([item["stage"] for item in ctx.exception.trace], [1, 2])
        self.assertEqual(self.written, {})

    def test_etl_reads_the_same_output_table(self) -> None:
        sample_service = SampleService()
        etl_service = EtlService()
        run = sample_service.execute_sampling(1)  # 种子数据里的 SAMP-0001
        self.assertTrue(run["ok"], run["message"])
        table_name = run["output_table"]

        table, message = etl_service.read_sampling_output(table_name)
        self.assertEqual(message, "")
        self.assertIsNotNone(table)
        # 同一张表：行数与逐行内容完全一致。
        self.assertEqual(len(table["rows"]), run["row_count"])
        self.assertEqual(table["rows"], run["rows"])

        missing, miss_message = etl_service.read_sampling_output("not_exists_table")
        self.assertIsNone(missing)
        self.assertIn("尚未生成", miss_message)

    def test_service_run_samp_0002_stops_at_seed_stage(self) -> None:
        result = SampleService().execute_sampling(2)  # 随机种子=自动
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], 2)
        self.assertEqual(result["stage_name"], "随机种子选择")

    def test_service_run_samp_0003_stops_at_layer_stage(self) -> None:
        result = SampleService().execute_sampling(3)  # 分层字段=city，源表无此列
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], 3)
        self.assertEqual(result["stage_name"], "分层字段拆分")

    def test_output_table_conflict_stops_at_stage_four(self) -> None:
        service = SampleService()
        # 先让 SAMP-0001 正常落表。
        first = service.execute_sampling(1)
        self.assertTrue(first["ok"], first.get("message"))
        original_table = store.get_output_table("samp_0001_customer_sample")
        self.assertIsNotNone(original_table)

        # 再造一条指向同一张输出表的配置：环节④拒绝覆盖，停在结果写入。
        extra = {
            "id": 99,
            "配置编号": "SAMP-0099",
            "数据源名称": "客户画像明细表",
            "采样算法": "分层随机抽样",
            "样本比例": "0.1",
            "随机种子": "1",
            "分层字段": "region",
            "输出表名": "samp_0001_customer_sample",
        }
        sample_rows = store.rows("sample")
        sample_rows.append(extra)
        try:
            conflict = service.execute_sampling(99)
            self.assertFalse(conflict["ok"])
            self.assertEqual(conflict["stage"], 4)
            self.assertEqual(conflict["stage_name"], "结果写入")
            self.assertIn("已被采样配置", conflict["message"])
            # 原表内容未被覆盖。
            self.assertEqual(store.get_output_table("samp_0001_customer_sample"), original_table)
        finally:
            sample_rows.remove(extra)


if __name__ == "__main__":
    unittest.main()
