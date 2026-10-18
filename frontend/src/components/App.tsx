import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { version as APP_VERSION } from '../../package.json'
import dayjs from 'dayjs'
import { Alert, App as AntApp, Button, Dropdown, Empty, Pagination, Segmented, Space, Spin, Switch, Tabs, Tag, Tooltip } from 'antd'
import { BarChartOutlined, CheckOutlined, DownOutlined, AppstoreOutlined, InfoCircleOutlined, LoadingOutlined, PieChartOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { ReportChart } from './ReportChart'
import { RecentData } from './RecentData'
import { ConfigPanel } from './ConfigPanel'
import { About } from './About'
import { DateRange, type Range } from '../DateRange'
import { call } from '../api'
import { chartDescription } from '../chartData'
import { canExport } from '../dateRules'
import { PAUSE_OPTIONS, resumeTimeLabel } from '../recording'
import type { Bootstrap, ExportResult, Report, Settings, Status, Storage } from '../types'

type Chart = 'heatmap' | 'pie' | 'bar'
const CHART_ICONS = { heatmap: AppstoreOutlined, pie: PieChartOutlined, bar: BarChartOutlined }

export function App() {
  const { message } = AntApp.useApp()
  const [bootstrap,setBootstrap] = useState<Bootstrap | null>(null)
  const [page,setPage] = useState('report')
  const [aboutBack,setAboutBack] = useState('report')
  const [settingsSection,setSettingsSection] = useState('recording')
  const [range,setRange] = useState<Range>([dayjs().startOf('day'),dayjs().startOf('day')])
  const [report,setReport] = useState<Report | null>(null)
  const [chart,setChart] = useState<Chart>('heatmap')
  const [expanded,setExpanded] = useState(false)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const [refresh,setRefresh] = useState(0)
  const [chartPage,setChartPage] = useState(1)
  const [statusError,setStatusError] = useState(false)
  const [recordingBusy,setRecordingBusy] = useState(false)
  const request = useRef(0)
  const recordingRevision = useRef(0)
  const [recentRevision,setRecentRevision] = useState(0)
  const [recentBusy,setRecentBusy] = useState(false)
  const settings = bootstrap?.settings
  const initialize = useCallback(async () => {
    setError(''); setBusy(true)
    try {
      const data = await call<Bootstrap>('bootstrap')
      setBootstrap(data); setExpanded(data.settings.expandContexts)
      const today = dayjs(data.status.now).subtract(data.settings.dayStartHour,'hour').startOf('day')
      setRange([today,today])
    } catch(e) { setError(e instanceof Error ? e.message : '无法打开数据') }
    finally { setBusy(false) }
  },[])
  useEffect(() => { initialize() },[initialize])
  useEffect(() => {
    if (!settings) return
    const id = ++request.current
    setBusy(true); setError(''); setReport(null)
    call<Report>('report',{start:range[0].format('YYYY-MM-DD'),end:range[1].format('YYYY-MM-DD'),expanded})
      .then(data => { if (request.current === id) setReport(data) })
      .catch(e => { if (request.current === id) setError(e instanceof Error ? e.message : '无法读取记录') })
      .finally(() => { if (request.current === id) setBusy(false) })
  },[settings,range,expanded,refresh])
  useEffect(() => { setChartPage(1) },[range])
  useEffect(() => {
    const timer = setInterval(async () => {
      const revision = recordingRevision.current
      try {
        const status = await call<Status>('status')
        if (revision === recordingRevision.current) { setBootstrap(data => data ? {...data,status} : data); setStatusError(false) }
      } catch { if (revision === recordingRevision.current) setStatusError(true) }
    },15000)
    return () => clearInterval(timer)
  },[])
  useEffect(() => {
    let mounted = true
    const refreshStatus = () => {
      const revision = recordingRevision.current
      return call<Status>('status').then(status => {
        if (mounted && revision === recordingRevision.current) { setBootstrap(data => data ? {...data,status} : data); setStatusError(false) }
      }).catch(() => { if (mounted && revision === recordingRevision.current) setStatusError(true) })
    }
    const resumeAt = bootstrap?.status.resumeAt
    const timer = resumeAt ? setTimeout(refreshStatus, Math.max(0, dayjs(resumeAt).valueOf() - Date.now() + 150)) : undefined
    window.addEventListener('focus', refreshStatus)
    return () => { mounted = false; clearTimeout(timer); window.removeEventListener('focus', refreshStatus) }
  },[bootstrap?.status.resumeAt])
  const description = useMemo(() => report ? chartDescription(report,chart) : null,[report,chart])
  const numDays = report?.days.length || 1
  const start = (chartPage-1)*31
  async function run(action: () => Promise<unknown>) {
    try { await action() } catch(e) { message.error(e instanceof Error ? e.message : '操作失败') }
  }
  async function exportRange(value: Range) {
    if (!canExport(...value)) throw new Error('导出区间最长为一年，请缩小日期区间')
    const result = await call<ExportResult>('export',{start:value[0].format('YYYY-MM-DD'),end:value[1].format('YYYY-MM-DD')})
    if (result.cancelled) return
    if (result.content) {
      const url = URL.createObjectURL(new Blob([result.content],{type:'text/csv;charset=utf-8'}))
      const link = document.createElement('a'); link.href=url; link.download=result.filename; link.click()
      setTimeout(() => URL.revokeObjectURL(url),1000)
    }
    message.success(`已导出 ${result.count.toLocaleString()} 条记录`)
  }
  async function saveSettings(value: Settings) {
    const settings = await call<Settings>('saveSettings',value)
    setBootstrap(data => data ? {...data,settings} : data)
    setExpanded(settings.expandContexts)
    message.success('设置已保存')
  }
  const status = bootstrap?.status
  async function changeRecording(payload: { pauseMinutes: number } | { paused: false }) {
    const revision = ++recordingRevision.current
    setRecordingBusy(true)
    await run(async () => {
      const status = await call<Status>('recording', payload)
      if (revision === recordingRevision.current) { setBootstrap(data => data ? {...data,status} : data); setStatusError(false) }
    })
    if (revision === recordingRevision.current) setRecordingBusy(false)
  }
  const ChartIcon = CHART_ICONS[chart]
  const recordingTag = <button type="button" className="recording-toggle" disabled={!bootstrap || recordingBusy} aria-busy={recordingBusy} aria-label={status?.paused ? '恢复记录' : '暂停记录'} title={status?.paused ? '点击恢复记录' : '暂停记录'} aria-haspopup={status?.paused ? undefined : 'menu'} onClick={status?.paused ? () => changeRecording({paused:false}) : undefined}>
    <Tag color={status?.paused ? 'default' : status?.demo ? 'gold' : status?.collecting ? 'success' : 'default'} icon={recordingBusy ? <LoadingOutlined/> : status?.paused ? <PlayCircleOutlined/> : <CheckOutlined/>}>
      {status?.paused ? resumeTimeLabel(status.resumeAt, status.now) : status?.demo ? '演示数据' : status?.collecting ? '记录中' : bootstrap ? '开发预览' : '正在连接'}
      {!status?.paused && <DownOutlined/>}
    </Tag>
  </button>
  const recordingControls = <Space size="small" className="recording-controls">
    {status?.paused ? recordingTag : <Dropdown trigger={['click']} menu={{ items: PAUSE_OPTIONS, onClick: ({key}) => changeRecording({pauseMinutes:Number(key)}) }} disabled={!bootstrap || recordingBusy}>{recordingTag}</Dropdown>}
    {(page === 'report' || page === 'recent') && <Button icon={<ReloadOutlined/>} loading={page === 'report' ? busy : recentBusy} aria-label={page === 'report' ? '刷新报表' : '刷新近期数据'} onClick={() => page === 'report' ? setRefresh(v => v+1) : setRecentRevision(v => v+1)}>刷新</Button>}
  </Space>
  return <div className="app-layout">
    <Tabs className="main-tabs" size="large" activeKey={page === 'about' ? '' : page} tabBarExtraContent={{ right: recordingControls }} onChange={key => { setPage(key); if (key === 'config') run(async () => { const storage = await call<Storage>('storage'); setBootstrap(data => data ? {...data,storage} : data) }) }} items={[{ key:'report',label:'时间报表' },{ key:'recent',label:'近期数据' },{ key:'config',label:'设置' }]}/>
    {error && <Alert className="page-alert" type="error" title={error} showIcon action={<Button size="small" onClick={() => !bootstrap ? initialize() : setRefresh(v => v+1)}>重试</Button>}/>}
    {statusError && <Alert className="page-alert" type="warning" title="连接异常，正在重试" showIcon/>}
    {status?.error && <Alert className="page-alert" type="error" title={status.error} showIcon/>}
    {page === 'report' && <>
      <section className="report-toolbar" aria-label="报表选项"><Space wrap size="middle"><DateRange value={range} onChange={setRange}/><Segmented value={chart} onChange={value => setChart(value as Chart)} options={[{value:'heatmap',label:'热力图',icon:<AppstoreOutlined/>},{value:'pie',label:'饼图',icon:<PieChartOutlined/>},{value:'bar',label:'柱状图',icon:<BarChartOutlined/>}]}/></Space><Space wrap size="middle"><label className="switch-label"><Switch aria-label="细分内容" checked={expanded} onChange={setExpanded}/>细分内容</label><Tooltip title="单日活跃时长超过细分单列门槛的项目、文档和网站会单独显示。"><InfoCircleOutlined className="help-icon"/></Tooltip></Space></section>
      <section className="chart-card"><Spin spinning={busy}><div className="chart-scroll" aria-label="图表区域">
        {report ? <ReportChart report={report} chart={chart} page={chartPage} today={dayjs(status?.now).format('YYYY-MM-DD')}/> : !busy && <Empty description="没有可用记录"/>}
      </div></Spin>
      {numDays > 31 && chart !== 'pie' && <div className="chart-pagination"><span>图中显示第 {start+1}–{Math.min(start+31,numDays)} 天</span><Pagination size="small" pageSize={31} total={numDays} current={chartPage} onChange={setChartPage} showSizeChanger={false}/></div>}
      {description && <div className="chart-description"><p><ChartIcon className="chart-description-icon" aria-hidden/>{description.info}</p><p>{description.explanation}</p></div>}
      </section>
    </>}
    {page === 'recent' && bootstrap && <RecentData revision={recentRevision} loading={recentBusy} onLoadingChange={setRecentBusy}/>}
    {page === 'config' && bootstrap && <ConfigPanel activeSection={settingsSection} onSectionChange={setSettingsSection} bootstrap={bootstrap} onSave={saveSettings} onBack={() => setPage('report')} onExport={exportRange} onOpenDirectory={async () => {await call('openData')}} onStartup={async enabled => { const startup = await call<boolean>('startup',{enabled}); setBootstrap(data => data ? {...data,startup} : data) }} onStorageChange={storage => { setBootstrap(data => data ? {...data,storage} : data); setRefresh(v => v+1) }}/>}
    {!bootstrap && busy && <div className="initial-loading"><Spin size="large"/></div>}
    {page === 'about' && <About version={status?.version || APP_VERSION} onBack={() => setPage(aboutBack)}/>}
    <footer><span>WorkState {status?.version || APP_VERSION}</span><button className="footer-about" onClick={() => { if (page !== 'about') { setAboutBack(page); setPage('about') } }}>关于</button></footer>
  </div>
}
