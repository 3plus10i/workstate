import { useEffect, useState } from 'react'
import { Alert, App, Button, Progress, Space, Tag } from 'antd'
import { call } from '../api'
import type { UpdateStatus } from '../types'

export const PROJECT_HOME = 'https://github.com/3plus10i/workstate'

export function About({ version, onBack }: { version: string; onBack: () => void }) {
  const { message, modal } = App.useApp()
  const [update, setUpdate] = useState<UpdateStatus | null>(null)
  const [checking, setChecking] = useState(false)
  useEffect(() => {
    let active = true
    call<UpdateStatus>('updateStatus').then(value => { if (active) setUpdate(value) }).catch(() => {})
    return () => { active = false }
  }, [])
  useEffect(() => {
    if (!update || !['checking', 'downloading', 'installing'].includes(update.phase)) return
    let active = true
    const timer = window.setInterval(() => {
      call<UpdateStatus>('updateStatus').then(value => { if (active) setUpdate(value) }).catch(() => {})
    }, 700)
    return () => { active = false; window.clearInterval(timer) }
  }, [update?.phase])
  async function action(method: string) {
    try { setUpdate(await call<UpdateStatus>(method)) }
    catch (error) { message.error(String((error as Error).message)) }
  }
  async function check() {
    setChecking(true)
    await action('updateCheck')
    setChecking(false)
  }
  const busy = checking || !!update && ['checking', 'downloading', 'installing'].includes(update.phase)
  const available = update?.version && ['available', 'downloading', 'ready', 'installing', 'error'].includes(update.phase)
  return <section className="about-card" aria-label="关于 WorkState">
    <h2>关于 WorkState</h2>
    <div className="about-copy">
      <p>WorkState 按分钟记录应用活动，以热力图、饼图和柱状图帮助你回顾电脑使用时间。</p>
      <ul>
        <li>记录包含程序名和窗口标题，仅保存在本机，不会上传。</li>
        <li>不想记录的程序可加入进程黑名单。历史记录长期保留，可手动清理或导出。</li>
        <li>导出文件可能含有网页标题、文档名等个人信息，分享前请检查。</li>
      </ul>
    </div>
    <Space wrap size="large" className="about-meta"><span>版本 {version}</span><Button loading={checking || update?.phase === 'checking'} disabled={busy} onClick={check}>检查更新</Button><a href={PROJECT_HOME} target="_blank" rel="noreferrer">项目主页</a></Space>
    {update?.phase === 'latest' && <Alert className="update-notice" type="success" showIcon title="当前已是最新版本"/>}
    {update?.phase === 'unpublished' && <Alert className="update-notice" type="info" showIcon title="暂未发布可更新的正式版本"/>}
    {update?.error && <Alert className="update-notice" type="error" showIcon title={update.error}/>}
    {available && <section className="update-panel" aria-label="软件更新">
      <Space wrap><strong>新版本 {update.version}</strong><Tag>{update.source === 'ghproxy' ? 'ghproxy' : 'GitHub'}</Tag></Space>
      {update.notes && <div className="update-notes">{update.notes}</div>}
      {update.phase === 'downloading' && <><Progress percent={Math.min(100, Math.floor(update.received / Math.max(1, update.total) * 100))}/><p className="setting-hint">已下载 {(update.received / 1048576).toFixed(1)} / {(update.total / 1048576).toFixed(1)} MB</p></>}
      {['available', 'error'].includes(update.phase) && <Button type="primary" disabled={!update.supported} onClick={() => action('updateDownload')}>下载更新</Button>}
      {update.phase === 'ready' && <Button type="primary" onClick={() => modal.confirm({ title: '重启并更新？', content: '程序将退出并安装已下载的更新，保留现有数据和设置。', okText: '重启并更新', cancelText: '取消', onOk: () => action('updateInstall') })}>重启并更新</Button>}
      {update.phase === 'installing' && <Button loading>正在重启更新</Button>}
      {!update.supported && <p className="setting-hint">开发和演示模式可检查版本，安装更新请使用正式桌面程序。</p>}
    </section>}
    <div><Button onClick={onBack}>返回</Button></div>
  </section>
}
