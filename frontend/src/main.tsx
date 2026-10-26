import React, { useEffect, useState } from 'react'
import { flushSync } from 'react-dom'
import ReactDOM from 'react-dom/client'
import { App as AntApp, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import updateLocale from 'dayjs/plugin/updateLocale'
import { App } from './components/App'
import './index.css'

dayjs.locale('zh-cn')
dayjs.extend(updateLocale)
dayjs.updateLocale('zh-cn', { weekStart: 1 })

function DesktopWindow() {
  const [session, setSession] = useState(0)
  useEffect(() => {
    // Replace the old page before the native window becomes visible again.
    const shown = () => flushSync(() => setSession(value => value + 1))
    window.addEventListener('workstate:shown', shown)
    return () => {
      window.removeEventListener('workstate:shown', shown)
    }
  }, [])
  return <AntApp key={session}><App/></AntApp>
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={{ token: { fontSize: 16, fontSizeSM: 14, colorText: '#1f1f1f', colorTextSecondary: '#434343', colorTextDescription: '#595959', colorPrimary: '#1677ff', colorBorder: '#d9d9d9', borderRadius: 6, controlHeight: 38, fontFamily: '"Segoe UI", "Microsoft YaHei UI", sans-serif' } }}>
      <DesktopWindow/>
    </ConfigProvider>
  </React.StrictMode>,
)
