import { useEffect, useRef, useState } from 'react'
import dayjs from 'dayjs'
import { Alert, Button, Descriptions, Modal } from 'antd'
import { ImportOutlined } from '@ant-design/icons'
import { call } from '../api'
import type { LegacyPreview, LegacyResult, Storage } from '../types'

export function LegacyImportPanel({ onChange }: { onChange: (storage: Storage) => void }) {
  const [preview, setPreview] = useState<LegacyPreview | null>(null)
  const [result, setResult] = useState<LegacyResult | null>(null)
  const [selecting, setSelecting] = useState(false)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState('')
  const token = useRef<string | null>(null)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      if (token.current) void call('importCancel', { token: token.current }).catch(() => {})
    }
  }, [])

  async function selectDatabase() {
    setSelecting(true); setError('')
    try {
      const data = await call<LegacyPreview | { cancelled: true }>('importPreview')
      if ('cancelled' in data) return
      if (!mounted.current) { await call('importCancel', { token: data.token }); return }
      token.current = data.token
      setPreview(data)
    } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : '无法读取旧数据库') }
    finally { if (mounted.current) setSelecting(false) }
  }
  function cancel() {
    if (token.current) void call('importCancel', { token: token.current }).catch(() => {})
    token.current = null
    setPreview(null)
  }
  async function importDatabase() {
    if (!preview) return
    setImporting(true); setError('')
    try {
      const data = await call<LegacyResult>('importCommit', { token: preview.token })
      onChange(data.storage)
      setResult(data)
    } catch (e) { setError(e instanceof Error ? e.message : '导入失败，请重试') }
    finally { token.current = null; setPreview(null); setImporting(false) }
  }
  return <>
    <h3 className="cleanup-heading">导入旧版数据库</h3>
    <p className="setting-description">选择原版 PCState 的 pcstate.db，导入活动记录。相同分钟保留本版记录，不修改旧数据库和本版设置。</p>
    {error && <Alert className="page-alert" type="error" title={error} showIcon closable onClose={() => setError('')}/>}
    <Button icon={<ImportOutlined/>} loading={selecting} onClick={selectDatabase}>选择旧版数据库</Button>
    <Modal title="导入旧版数据库" open={!!preview} okText="开始导入" cancelText="取消" confirmLoading={importing}
      closable={!importing} cancelButtonProps={{ disabled: importing }} onCancel={() => { if (!importing) cancel() }} onOk={importDatabase}>
      {preview && <>
        <Descriptions column={1} size="small" items={[
          { key:'file',label:'数据库',children:<span className="data-path">{preview.filename}</span> },
          { key:'dates',label:'记录区间',children:`${dayjs(preview.firstMinute*60000).format('YYYY-MM-DD HH:mm')} 至 ${dayjs(preview.lastMinute*60000).format('YYYY-MM-DD HH:mm')}` },
          { key:'total',label:'记录总数',children:`${preview.total.toLocaleString()} 条` },
          { key:'new',label:'预计新增',children:`${preview.newRecords.toLocaleString()} 条` },
          { key:'duplicates',label:'跳过重复',children:`${preview.duplicates.toLocaleString()} 条` },
        ]}/>
        {preview.fallbackCount > 0 && <p className="field-description">其中 {preview.fallbackCount.toLocaleString()} 条记录缺少原始进程名，将保留旧版程序名称。</p>}
      </>}
    </Modal>
    <Modal title="导入完成" open={!!result} onCancel={() => setResult(null)} footer={<Button type="primary" onClick={() => setResult(null)}>我知道了</Button>}>
      {result && <p>已新增 {result.imported.toLocaleString()} 条记录，跳过 {result.duplicates.toLocaleString()} 条重复记录。</p>}
      <Alert type="warning" showIcon title="请停用旧版的开机自启" description="请关闭旧版 PCState 的开机启动，并从托盘退出旧版，避免两个版本同时运行。"/>
    </Modal>
  </>
}
