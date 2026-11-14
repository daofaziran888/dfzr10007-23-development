import { useCallback, useEffect, useMemo, useState } from 'react'

import { request } from '@/api/client'

const ENDPOINT = '/api/sample'
const columns = [
  "配置编号",
  "数据源名称",
  "采样算法",
  "样本比例",
  "随机种子",
  "分层字段",
  "输出表名",
  "配置状态"
]
const actions = [
  "启用采样",
  "暂停采样",
  "关闭采样"
]
const statuses = [
  "草稿",
  "已启用",
  "已暂停",
  "已关闭"
]
const stats = [
  {
    "label": "采样配置总数",
    "value": 0
  },
  {
    "label": "已启用采样",
    "value": 0
  },
  {
    "label": "已暂停采样",
    "value": 0
  }
]

type Row = Record<string, string | number | null>

type StageTrace = {
  stage: number
  stage_name: string
  action: string
  input: Record<string, unknown>
  output: Record<string, unknown>
}

type SampleRow = Record<string, string | number>

type RunResult = {
  ok: boolean
  message: string
  stage?: number | null
  stage_name?: string | null
  配置编号?: string | null
  output_table?: string | null
  row_count?: number | null
  rows?: SampleRow[] | null
  trace: StageTrace[]
}

export default function SampleView() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [runningId, setRunningId] = useState<number | null>(null)
  const [runResult, setRunResult] = useState<RunResult | null>(null)
  const filterFields = useMemo(() => columns.slice(0, 3), [])

  const reload = useCallback(async () => {
    setErrorMessage('')
    const query = new URLSearchParams(filters).toString()
    try {
      const response = await request(`${ENDPOINT}?${query}`)
      if (!response.ok) {
        throw new Error('采样配置列表读取失败')
      }
      const payload = await response.json()
      setRows(payload.items ?? [])
      setTotal(payload.total ?? 0)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '数据采样管理列表读取失败')
    }
  }, [filters])

  useEffect(() => {
    void reload()
  }, [reload])

  async function runAction(action: string, row: Row) {
    setErrorMessage('')
    try {
      const response = await request(`${ENDPOINT}/${row.id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      })
      if (!response.ok) {
        throw new Error('数据采样管理动作未生效，请稍后重试')
      }
      await reload()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '数据采样管理操作失败')
    }
  }

  // 执行一次采样：后端按 ①配置读取 → ②随机种子选择 → ③分层字段拆分 → ④结果写入 推进
  async function runSampling(row: Row) {
    setErrorMessage('')
    setRunningId(Number(row.id))
    setRunResult(null)
    try {
      const response = await request(`${ENDPOINT}/${row.id}/run`, { method: 'POST' })
      if (!response.ok) {
        throw new Error('采样执行请求失败')
      }
      const payload = (await response.json()) as RunResult
      setRunResult(payload)
      if (!payload.ok) {
        setErrorMessage(payload.message)
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '采样执行失败')
    } finally {
      setRunningId(null)
    }
  }

  const previewColumns = useMemo(() => {
    if (runResult?.rows?.length) {
      return Object.keys(runResult.rows[0])
    }
    return []
  }, [runResult])

  return (
    <section className="page" data-module="sample">
      <header className="page-head">
        <div>
          <h2>数据采样管理管理</h2>
          <p className="page-desc">维护数据采样的算法选择、比例控制与分层配置，为数据采样管理提供可验证的数据工程流程。</p>
        </div>
        <div className="page-actions">
          <button className="btn primary" type="button" onClick={() => setErrorMessage('采样配置登记入口尚未接入审批流')}>
            登记采样配置
          </button>
          <button className="btn" type="button" onClick={() => window.open(`${ENDPOINT}/export`, '_blank')}>
            导出数据采样管理清单
          </button>
        </div>
      </header>

      <div className="stat-row">
        {stats.map((item) => (
          <article key={item.label} className="stat-card">
            <span className="stat-label">{item.label}</span>
            <strong className="stat-value">{item.value}</strong>
          </article>
        ))}
      </div>

      <form className="filter-bar" onSubmit={(event) => { event.preventDefault(); void reload() }}>
        {filterFields.map((field) => (
          <label key={field} className="filter-item">
            <span>{field}</span>
            <input
              value={filters[field] ?? ''}
              placeholder={`按${field}检索`}
              onChange={(event) => setFilters((prev) => ({ ...prev, [field]: event.target.value }))}
            />
          </label>
        ))}
        <button className="btn" type="submit">查询</button>
        <button className="btn ghost" type="button" onClick={() => setFilters({})}>重置条件</button>
      </form>

      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{column}</th>)}
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row.id)}>
              {columns.map((column) => <td key={column}>{row[column] ?? '—'}</td>)}
              <td className="row-actions">
                <button
                  className="link"
                  type="button"
                  disabled={runningId === Number(row.id)}
                  onClick={() => void runSampling(row)}
                >
                  {runningId === Number(row.id) ? '采样执行中…' : '执行采样'}
                </button>
                {actions.map((action) => (
                  <button key={action} className="link" type="button" onClick={() => void runAction(action, row)}>
                    {action}
                  </button>
                ))}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="empty-state" colSpan={columns.length + 1}>暂无数据采样管理数据，可先登记采样配置</td>
            </tr>
          )}
        </tbody>
      </table>

      {runResult && (
        <section className="run-panel" style={{ marginTop: 16, background: '#fff', border: '1px solid var(--border)', borderRadius: 8, padding: 16 }}>
          <h3 style={{ margin: '0 0 8px', fontSize: 15 }}>
            采样执行结果{runResult.配置编号 ? `：${runResult.配置编号}` : ''}
          </h3>
          <p className={runResult.ok ? '' : 'error-text'} style={{ margin: '0 0 12px', fontSize: 13 }}>
            {runResult.ok
              ? `${runResult.message}（同配置重复执行逐行相同）`
              : `停在环节${runResult.stage}「${runResult.stage_name}」：${runResult.message}`}
          </p>

          <h4 style={{ margin: '0 0 6px', fontSize: 13, color: 'var(--muted)' }}>四环节调用轨迹（输入 → 输出）</h4>
          <table className="data-table" style={{ marginBottom: 12 }}>
            <thead>
              <tr>
                <th style={{ width: 60 }}>环节</th>
                <th style={{ width: 130 }}>环节名称</th>
                <th>动作</th>
                <th>输入</th>
                <th>输出</th>
              </tr>
            </thead>
            <tbody>
              {runResult.trace.map((trace) => (
                <tr key={trace.stage}>
                  <td>{trace.stage}</td>
                  <td>{trace.stage_name}</td>
                  <td>{trace.action}</td>
                  <td><code>{JSON.stringify(trace.input)}</code></td>
                  <td><code>{JSON.stringify(trace.output)}</code></td>
                </tr>
              ))}
              {!runResult.ok && runResult.stage && (
                <tr>
                  <td>{runResult.stage}</td>
                  <td className="error-text">{runResult.stage_name}（终止）</td>
                  <td className="error-text" colSpan={3}>{runResult.message}</td>
                </tr>
              )}
            </tbody>
          </table>

          {runResult.ok && runResult.rows && (
            <>
              <h4 style={{ margin: '0 0 6px', fontSize: 13, color: 'var(--muted)' }}>
                样本输出表「{runResult.output_table}」预览（{runResult.row_count} 行，数据准备流水线读取同一张表）
              </h4>
              <table className="data-table">
                <thead>
                  <tr>
                    {previewColumns.map((column) => <th key={column}>{column}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {runResult.rows.map((sampleRow, index) => (
                    <tr key={String(index)}>
                      {previewColumns.map((column) => <td key={column}>{String(sampleRow[column] ?? '')}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>
      )}

      <footer className="page-foot">
        <span>共 {total} 条数据采样管理记录</span>
        {errorMessage && <span className="error-text">{errorMessage}</span>}
      </footer>
    </section>
  )
}
