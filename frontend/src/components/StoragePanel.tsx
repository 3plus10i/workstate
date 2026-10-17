import { useState } from 'react'
import dayjs from 'dayjs'
import { Alert, App, Button, DatePicker, Descriptions, Divider, Modal, Radio, Space } from 'antd'
import { DeleteOutlined, FolderOpenOutlined } from '@ant-design/icons'
import { DateRange, type Range } from '../DateRange'
import { call } from '../api'
import type { CleanupPreview, CleanupResult, Storage } from '../types'
import { LegacyImportPanel } from './LegacyImportPanel'

function size(bytes: number) { return bytes < 1048576 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1048576).toFixed(1)} MB` }

export function StoragePanel({ storage, onChange, onOpenDirectory }: {
  storage: Storage; onChange: (value: Storage) => void; onOpenDirectory: () => Promise<void>
}) {
  const { message } = App.useApp()
  const today = dayjs().startOf('day')
  const [mode, setMode] = useState<'range' | 'before'>('before')
  const [before, setBefore] = useState(today.subtract(3, 'month'))
  const [range, setRange] = useState<Range>([today.subtract(1, 'month'), today.subtract(1, 'day')])
  const [preview, setPreview] = useState<CleanupPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')
  async function previewCleanup() {
    setPreviewing(true); setError('')
    try {
      const selection = mode === 'range' ? { mode, start: range[0].format('YYYY-MM-DD'), end: range[1].format('YYYY-MM-DD') } : { mode, before: before.format('YYYY-MM-DD') }
      const result = await call<CleanupPreview>('cleanupPreview', selection)
      if (result.count) setPreview(result)
      else message.info('所选范围没有记录')
    } catch (e) { setError(e instanceof Error ? e.message : '无法预览清理范围') }
    finally { setPreviewing(false) }
  }
  async function cleanup() {
    if (!preview?.token) return
    setDeleting(true); setError('')
    try {
      const result = await call<CleanupResult>('cleanup', { token: preview.token })
      onChange(result.storage)
      message.success(`已清理 ${result.deletedRows.toLocaleString()} 条记录`)
      if (!result.compacted) message.warning('记录已清理，数据库空闲空间将用于后续记录')
    } catch (e) { setError(e instanceof Error ? e.message : '清理失败，请重新查看数据状态') }
    finally { setDeleting(false); setPreview(null) }
  }
  return <>
    <Descriptions column={{ xs: 1, sm: 2 }} size="small" items={[
      { key: 'path', label: '数据目录', span: 2, children: <span className="data-path">{storage.directory}</span> },
      { key: 'retention', label: '保存期限', children: '永久保存' },
      { key: 'size', label: '数据库大小', children: size(storage.databaseBytes) },
      { key: 'count', label: '记录总数', children: `${storage.recordCount.toLocaleString()} 条` },
      { key: 'dates', label: '记录日期', children: storage.firstMinute !== null && storage.lastMinute !== null
        ? `${dayjs(storage.firstMinute * 60000).format('YYYY-MM-DD')} 至 ${dayjs(storage.lastMinute * 60000).format('YYYY-MM-DD')}` : '暂无记录' },
    ]}/>
    <Button className="storage-actions" icon={<FolderOpenOutlined/>} onClick={() => onOpenDirectory().catch(e => setError(e instanceof Error ? e.message : '无法打开数据目录'))}>打开目录</Button>
    <Divider/>
    <LegacyImportPanel onChange={onChange}/>
    <Divider/>
    <h3 className="cleanup-heading">清理历史数据</h3>
    {error && <Alert className="page-alert" type="error" title={error} showIcon/>}
    <div className="cleanup-controls">
      <Space wrap size="middle">
      <Radio.Group aria-label="清理方式" value={mode} onChange={event => setMode(event.target.value)}>
        <Radio.Button value="before">某日期之前</Radio.Button><Radio.Button value="range">日期区间</Radio.Button>
      </Radio.Group>
      {mode === 'range' ? <DateRange label="清理日期区间" value={range} onChange={setRange}/>
        : <DatePicker aria-label="清理截止日期" value={before} allowClear={false} disabledDate={value => value.isAfter(today, 'day')} onChange={value => { if (value) setBefore(value.startOf('day')) }}/>}
      </Space>
      <Space wrap><span>快捷选择</span>{[{ months: 3, label: '三个月前' }, { months: 6, label: '半年前' }, { months: 12, label: '一年前' }].map(item =>
        <Button key={item.months} onClick={() => { setMode('before'); setBefore(today.subtract(item.months, 'month')) }}>{item.label}</Button>)}
      </Space>
      <div><Button danger icon={<DeleteOutlined/>} loading={previewing} onClick={previewCleanup}>预览清理</Button></div>
    </div>
    <Modal title="确认清理历史数据" open={!!preview} okText="永久删除" cancelText="取消" okButtonProps={{ danger: true }} confirmLoading={deleting}
      closable={!deleting} cancelButtonProps={{ disabled: deleting }} onCancel={() => { if (!deleting) setPreview(null) }} onOk={cleanup}>
      <p>{preview?.mode === 'range' ? `${preview.start} 至 ${preview.end}（含起止日期）` : `${preview?.before} 之前（不含当天）`}</p>
      <p>将永久删除 <strong>{preview?.count.toLocaleString()}</strong> 条原始记录，此操作无法撤销。</p>
    </Modal>
  </>
}
