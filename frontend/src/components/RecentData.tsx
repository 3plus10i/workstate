import { useEffect, useRef, useState } from 'react'
import dayjs from 'dayjs'
import { Alert, Table, Tag } from 'antd'
import { call } from '../api'
import type { Recent, RecentRow } from '../types'

export function RecentData({ revision, loading, onLoadingChange }: { revision: number; loading: boolean; onLoadingChange: (loading: boolean) => void }) {
  const [data, setData] = useState<Recent | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(30)
  const [error, setError] = useState('')
  const snapshot = useRef<{ revision: number; endMinute?: number }>({ revision })
  const request = useRef(0)
  useEffect(() => {
    if (snapshot.current.revision !== revision) snapshot.current = { revision }
    const id = ++request.current
    onLoadingChange(true); setError('')
    call<Recent>('recent', { page, pageSize, ...(snapshot.current.endMinute === undefined ? {} : { endMinute: snapshot.current.endMinute }) })
      .then(result => {
        if (id !== request.current) return
        snapshot.current.endMinute = result.endMinute
        setData(result)
      })
      .catch(e => { if (id === request.current) setError(e instanceof Error ? e.message : '无法读取近期数据') })
      .finally(() => { if (id === request.current) onLoadingChange(false) })
    return () => { request.current++; onLoadingChange(false) }
  }, [page, pageSize, revision, onLoadingChange])
  return <section className="recent-card" aria-label="近期原始数据">
    <div className="recent-heading"><h2>最近 8 小时</h2>{data && <span>{dayjs(data.start).format('MM-DD HH:mm')} 至 {dayjs(data.end).format('MM-DD HH:mm')}</span>}</div>
    <p className="recent-notice">更多数据可通过导出功能查看</p>
    {error && <Alert className="page-alert" type="error" showIcon title={error}/>}
    <Table<RecentRow> rowKey="minute" loading={loading} dataSource={data?.rows || []} scroll={{ x: 900, y: 'calc(100vh - 350px)' }} locale={{ emptyText: '最近 8 小时暂无记录' }}
      pagination={{ current: data?.page || page, pageSize, total: data?.total || 0, showSizeChanger: true, pageSizeOptions: [30, 60, 120], showTotal: total => `共 ${total} 条`, onChange: (next, size) => { setPage(size !== pageSize ? 1 : next); setPageSize(size) } }}
      columns={[
        { title: '时间', dataIndex: 'time', width: 180, render: value => dayjs(value).format('MM-DD HH:mm') },
        { title: '状态', dataIndex: 'active', width: 100, render: value => <Tag color={value ? 'success' : 'default'}>{value ? '活跃' : '闲置'}</Tag> },
        { title: '进程名', dataIndex: 'process', width: 210, ellipsis: true },
        { title: '窗口标题', dataIndex: 'title', ellipsis: true },
      ]}/>
  </section>
}
