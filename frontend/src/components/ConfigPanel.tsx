import { useEffect, useState } from 'react'
import dayjs from 'dayjs'
import { Alert, Button, Collapse, Form, Input, InputNumber, Popconfirm, Radio, Select, Space, Switch, Tooltip } from 'antd'
import { DeleteOutlined, DownloadOutlined, InfoCircleOutlined, PlusOutlined } from '@ant-design/icons'
import type { ActivityPreview, Bootstrap, Settings, Storage } from '../types'
import { call } from '../api'
import { duration } from '../chartData'
import { DateRange, type Range } from '../DateRange'
import { canExport } from '../dateRules'
import { StoragePanel } from './StoragePanel'

interface NameRow { process: string; name: string; id: number }
interface Props {
  activeSection: string
  onSectionChange: (section: string) => void
  bootstrap: Bootstrap
  onSave: (value: Settings) => Promise<void>
  onStartup: (enabled: boolean) => Promise<void>
  onStorageChange: (value: Storage) => void
  onOpenDirectory: () => Promise<void>
  onExport: (range: Range) => Promise<void>
  onBack: () => void
}
function Info({ children }: { children: string }) { return <Tooltip title={children}><InfoCircleOutlined className="help-icon" /></Tooltip> }

export function ConfigPanel({ activeSection, onSectionChange, bootstrap, onSave, onStartup, onStorageChange, onOpenDirectory, onExport, onBack }: Props) {
  const settings = bootstrap.settings
  const [draft, setDraft] = useState(settings)
  const [names, setNames] = useState<NameRow[]>([])
  const [blacklist, setBlacklist] = useState(settings.excludedProcesses.join('\n'))
  const [sites, setSites] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<ActivityPreview | null>(null)
  const [previewError, setPreviewError] = useState(false)
  const [exportRange, setExportRange] = useState<Range>([dayjs().subtract(6,'day'), dayjs()])
  function reset() {
    setDraft(settings)
    setNames(Object.entries(settings.displayNames).map(([process, name], id) => ({ process, name, id })))
    setBlacklist(settings.excludedProcesses.join('\n'))
    setSites(settings.siteNames.join('\n'))
    setError('')
  }
  useEffect(reset, [settings])
  useEffect(() => {
    if (activeSection !== 'recording') return
    let active = true
    setPreview(null); setPreviewError(false)
    call<ActivityPreview>('activityPreview', { dayStartHour: draft.dayStartHour, excludedProcesses: blacklist.split('\n').map(s => s.trim()).filter(Boolean) })
      .then(value => { if (active) setPreview(value) })
      .catch(() => { if (active) setPreviewError(true) })
    return () => { active = false }
  }, [activeSection, draft.dayStartHour, blacklist])
  const dirty = JSON.stringify(draft) !== JSON.stringify(settings) || JSON.stringify(names.map(row => [row.process,row.name])) !== JSON.stringify(Object.entries(settings.displayNames)) || blacklist !== settings.excludedProcesses.join('\n') || sites !== settings.siteNames.join('\n')
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : '操作失败') } finally { setBusy(false) }
  }
  async function save() {
    const displayNames: Record<string, string> = {}
    for (const row of names) {
      if (!row.process.trim() || !row.name.trim()) throw new Error('请填写完整的进程名和显示名')
      const key = row.process.trim().toLowerCase().replace(/\.exe$/i, '')
      if (key in displayNames) throw new Error(`进程名重复：${row.process}`)
      displayNames[key] = row.name.trim()
    }
    await onSave({ ...draft, displayNames, excludedProcesses: blacklist.split('\n').map(s => s.trim()).filter(Boolean), siteNames: sites.split('\n').map(s => s.trim()).filter(Boolean) })
  }
  return <div className="settings-content">
    {error && <Alert type="error" title={error} showIcon closable onClose={() => setError('')}/>}
    <Collapse accordion destroyOnHidden activeKey={activeSection ? [activeSection] : []} onChange={keys => onSectionChange((Array.isArray(keys) ? keys[0] : keys) || '')} items={[
      { key: 'recording', label: '记录设置', children: <><p className="setting-description">设置报表的一天起始时间、活跃时长统计粒度和开机启动。</p><Form layout="vertical">
        <div className="form-grid"><Form.Item label={<span>一天起始时间 <Info>修改报表显示的一天起始时间</Info></span>}><Radio.Group value={draft.dayStartHour} onChange={e => setDraft({ ...draft, dayStartHour: e.target.value })}><Radio.Button value={0}>午夜 0 时</Radio.Button><Radio.Button value={4}>凌晨 4 时</Radio.Button></Radio.Group></Form.Item>
</div>
        <Form.Item label="活跃时长统计粒度"><Space wrap size="middle"><Radio.Group aria-label="活跃时长统计粒度" value={draft.activityGranularity} onChange={e => setDraft({ ...draft, activityGranularity: e.target.value })}><Radio.Button value={1}>1 分钟</Radio.Button><Radio.Button value={5}>5 分钟</Radio.Button></Radio.Group><span className="setting-hint" aria-live="polite">{preview ? `今日预览：1 分钟 ${duration(preview.oneMinute)} · 5 分钟 ${duration(preview.fiveMinutes)}` : previewError ? '今日预览暂不可用' : '正在读取今日预览…'}</span></Space><p className="setting-hint">5 分钟小片内有活动即计 5 分钟，按各程序实际活动比例分配。热力图格子保留实际记录，原始数据不变。</p></Form.Item>
        <Form.Item label="开机启动"><Space><Switch checked={bootstrap.startup} disabled={bootstrap.status.demo || busy} onChange={enabled => perform(() => onStartup(enabled))} checkedChildren="开启" unCheckedChildren="关闭"/><span className="setting-hint">建议开启</span></Space></Form.Item>
      </Form></> },
      { key: 'aggregation', label: '富内容程序细分', children: <><p className="setting-description">可在报表中进一步细分显示部分程序的活动情况，例如显示具体项目名、文档名或网站名。</p><Form layout="vertical">
        <Form.Item label="启用富内容程序细分"><Switch checked={draft.expandContexts} onChange={value => setDraft({ ...draft, expandContexts: value })} checkedChildren="开启" unCheckedChildren="关闭"/></Form.Item>
        <div className="aggregation-options"><Form.Item label="细分程序类型"><p className="field-description">可增删程序进程名（不含.exe），输入后按 Enter 确认。进程名可在近期数据中查看。</p><Space orientation="vertical" size="middle" className="program-types">
          {([
            { key:'ideProcesses', toggle:'splitIde', label:'IDE 项目', input:'IDE 程序', placeholder:'例如 trae，输入后按 Enter 添加' },
            { key:'documentProcesses', toggle:'splitDocuments', label:'Office 文档', input:'Office 程序', placeholder:'例如 wps，输入后按 Enter 添加' },
            { key:'browserProcesses', toggle:'splitSites', label:'浏览器网站', input:'浏览器程序', placeholder:'例如 brave，输入后按 Enter 添加' },
          ] as const).map(item => <div className="program-rule" key={item.key}>
            <div className="program-rule-heading"><label className="switch-label"><Switch checked={draft[item.toggle]} onChange={value => setDraft({...draft,[item.toggle]:value})} aria-label={item.label}/>{item.label}</label>
              <Popconfirm title={`恢复${item.input}默认名单？`} description="这会清除该类别的当前名单，替换为默认程序。保存设置后生效。" okText="恢复默认" cancelText="取消" onConfirm={() => setDraft(value => ({...value,[item.key]:[...bootstrap.programDefaults[item.key]]}))}>
                <Button size="small" aria-label={`恢复${item.input}默认`}>恢复默认</Button>
              </Popconfirm>
            </div>
            <Select mode="tags" aria-label={item.input} value={draft[item.key]} tokenSeparators={[',','，',';','；']} onChange={value => setDraft({...draft,[item.key]:value})} placeholder={item.placeholder}/>
          </div>)}
        </Space></Form.Item>
        <Form.Item label={<span>细分单列门槛 <Info>同一内容单日实际活跃时长超过门槛时，才在当天的报表中单独显示。</Info></span>}><Space><InputNumber aria-label="细分单列门槛" min={1} max={120} precision={0} value={draft.detailThreshold} onChange={value => { if (value !== null) setDraft({ ...draft, detailThreshold: value }) }}/>分钟</Space></Form.Item></div>
        <Form.Item label="网站名关键词"><p className="field-description">浏览器窗口标题中包含以下关键词时，将被细分到对应网站。每行一个关键词，识别时按长度降序自动排列（长匹配优先）</p><Input.TextArea aria-label="网站名关键词" rows={6} value={sites} onChange={e => setSites(e.target.value)} placeholder="每行一个关键词，例如 GitHub"/></Form.Item>
      </Form></> },
      { key: 'blacklist', label: '进程黑名单', children: <><p className="setting-description">黑名单中的进程不会被WorkState记录。每行一个进程名（不含.exe）。可通过近期数据查看程序名。支持用双斜杠“//”做行内注释。</p><Input.TextArea aria-label="进程黑名单" rows={4} value={blacklist} onChange={e => setBlacklist(e.target.value)} placeholder="每行一个进程名，例如 LockApp"/></> },
      { key: 'displayNames', label: '自定义显示名', children: <><p className="setting-description">自定义程序在报表中的显示名。左列为原始进程名（不含.exe），右列为希望在图表中使用的对应显示名。</p><div className="name-table-heading"><span>进程名</span><span>显示名</span><span/></div>{names.map((row,index) => <div className="name-row" key={row.id}><Input aria-label={`进程名 ${index+1}`} value={row.process} placeholder="WINWORD" onChange={e => setNames(values => values.map(item => item.id === row.id ? { ...item, process: e.target.value } : item))}/><Input aria-label={`显示名 ${index+1}`} value={row.name} placeholder="Word" onChange={e => setNames(values => values.map(item => item.id === row.id ? { ...item, name: e.target.value } : item))}/><Popconfirm title="删除这条映射？" onConfirm={() => setNames(values => values.filter(item => item.id !== row.id))}><Button danger type="text" aria-label={`删除映射 ${index+1}`} icon={<DeleteOutlined/>}/></Popconfirm></div>)}<Button type="dashed" icon={<PlusOutlined/>} onClick={() => setNames(values => [...values, { process: '', name: '', id: Math.max(-1,...values.map(row => row.id))+1 }])}>添加映射</Button></> },
      { key: 'storage', label: '数据存储', children: <StoragePanel storage={bootstrap.storage} onChange={onStorageChange} onOpenDirectory={onOpenDirectory}/> },
      { key: 'export', label: '导出数据', children: <><p className="setting-description">单次导出最长一年。导出文件包含窗口标题等原始信息，可能含有隐私数据（网页标题、文档名等）。请在分享导出文件前检查内容，避免隐私泄露。</p>{!canExport(...exportRange) && <Alert className="page-alert" type="warning" title="导出区间最长为一年，请缩小日期区间" showIcon/>}<Space wrap size="middle"><DateRange label="导出日期区间" value={exportRange} onChange={setExportRange}/><Button type="primary" icon={<DownloadOutlined/>} loading={busy} disabled={!canExport(...exportRange)} onClick={() => perform(() => onExport(exportRange))}>导出 CSV</Button></Space></> },
    ]}/>
    <div className="settings-actions"><Space><Button type="primary" disabled={!dirty} loading={busy} onClick={() => perform(save)}>保存设置</Button><Button disabled={!dirty || busy} onClick={reset}>撤销修改</Button></Space><Button onClick={onBack}>返回报表</Button></div>
  </div>
}
