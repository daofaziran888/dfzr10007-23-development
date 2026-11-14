import { useCallback, useEffect, useMemo, useState } from 'react'

import { request } from '@/api/client'

const ENDPOINT = '/api/etl'
const columns = [
  "任务编号",
  "任务名称",
  "输入源",
  "转换步骤",
  "输出目标",
  "调度周期",
  "依赖关系",
  "任务状态"
]
const actions = [
  "启动任务",
  "暂停任务",
  "归档任务"
]
const statuses = [
  "草稿",
  "运行中",
  "已暂停",
  "已完成"
]
const stats = [
  {
    "label": "准备任务总数",
    "value": 0
  },
  {
    "label": "运行中任务",
    "value": 0
  },
  {
    "label": "已暂停任务",
    "value": 0
  }
]

type Row = Record<string, string | number | null>
type SampleRow = Record<string, string | number>

type OutputTable = {
  table_name: string
  rows: SampleRow[]
  meta: Record<string, unknown>
}

type ReadResult = {
  ok: boolean
  message: string
  table: OutputTable | null
}

export default function EtlView() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [inputTable, setInputTable] = useState('samp_0001_customer_sample')
  const [readResult, setReadResult] = useState<ReadResult | null>(null)
  const filterFields = useMemo(() => columns.slice(0, 3), [])

  const reload = useCallback(async () => {
    setErrorMessage('')
    const query = new URLSearchParams(filters).toString()
    try {
      const response = await request(`${ENDPOINT}?${query}`)
      if (!response.ok) {
        throw new Error('准备任务列表读取失败')
      }
      const payload = await response.json()
      setRows(payload.items ?? [])
      setTotal(payload.total ?? 0)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '数据准备流水线列表读取失败')
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
        throw new Error('数据准备流水线动作未生效，请稍后重试')
      }
      await reload()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '数据准备流水线操作失败')
    }
  }

  // 数据准备流水线按表名读取采样环节④写出的同一张样本输出表
  async function readSamplingOutput() {
    setErrorMessage('')
    setReadResult(null)
    try {
      const response = await request(`${ENDPOINT}/inputs/${encodeURIComponent(inputTable.trim())}`)
      const payload = (await response.json()) as ReadResult
      setReadResult(payload)
      if (!payload.ok) {
        setErrorMessage(payload.message)
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '采样输出表读取失败')
    }
  }

  const previewColumns = useMemo(() => {
    if (readResult?.table?.rows.length) {
      return Object.keys(readResult.table.rows[0])
    }
    return []
  }, [readResult])

  return (
    <section className="page" data-module="etl">
      <header className="page-head">
        <div>
          <h2>数据准备流水线管理</h2>
          <p className="page-desc">维护数据准备的转换步骤、调度配置与依赖管理，为数据准备流水线提供可验证的数据工程流程。</p>
        </div>
        <div className="page-actions">
          <button className="btn primary" type="button" onClick={() => setErrorMessage('准备任务登记入口尚未接入审批流')}>
            登记准备任务
          </button>
          <button className="btn" type="button" onClick={() => window.open(`${ENDPOINT}/export`, '_blank')}>
            导出数据准备流水线清单
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

      <form
        className="filter-bar"
        onSubmit={(event) => { event.preventDefault(); void readSamplingOutput() }}
        style={{ background: '#fff', border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}
      >
        <label className="filter-item">
          <span>采样输出表名（读取同一张表）</span>
          <input
            value={inputTable}
            placeholder="例如 samp_0001_customer_sample"
            onChange={(event) => setInputTable(event.target.value)}
            style={{ minWidth: 260 }}
          />
        </label>
        <button className="btn primary" type="submit">读取采样结果</button>
      </form>

      {readResult?.ok && readResult.table && (
        <section style={{ marginBottom: 12, background: '#fff', border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
          <h3 style={{ margin: '0 0 4px', fontSize: 14 }}>
            已接入输入表「{readResult.table.table_name}」（{readResult.table.rows.length} 行）
          </h3>
          <p style={{ margin: '0 0 8px', fontSize: 12, color: 'var(--muted)' }}>
            表来源 meta：<code>{JSON.stringify(readResult.table.meta)}</code>
          </p>
          <table className="data-table">
            <thead>
              <tr>
                {previewColumns.map((column) => <th key={column}>{column}</th>)}
              </tr>
            </thead>
            <tbody>
              {readResult.table.rows.map((sampleRow, index) => (
                <tr key={String(index)}>
                  {previewColumns.map((column) => <td key={column}>{String(sampleRow[column] ?? '')}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

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
              <td className="empty-state" colSpan={columns.length + 1}>暂无数据准备流水线数据，可先登记准备任务</td>
            </tr>
          )}
        </tbody>
      </table>

      <footer className="page-foot">
        <span>共 {total} 条数据准备流水线记录</span>
        {errorMessage && <span className="error-text">{errorMessage}</span>}
      </footer>
    </section>
  )
}
