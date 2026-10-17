declare global {
  interface Window {
    pywebview?: { api: { dispatch(method: string, payload: unknown): Promise<{ ok: boolean; data?: unknown; error?: string }> } }
  }
}

export async function call<T>(method: string, payload: unknown = {}): Promise<T> {
  let result
  if (window.pywebview?.api) {
    result = await window.pywebview.api.dispatch(method, payload)
  } else if (location.protocol === 'http:' || location.protocol === 'https:') {
    const response = await fetch('/api', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ method, payload }) })
    if (!response.ok) throw new Error('无法连接本地服务，请重试')
    result = await response.json()
  } else {
    // The native bridge is injected after the document starts loading.
    await new Promise<void>((resolve, reject) => {
      const ready = () => { clearTimeout(timeout); resolve() }
      const timeout = setTimeout(() => { window.removeEventListener('pywebviewready', ready); reject(new Error('桌面连接未就绪，请重新打开 WorkState')) }, 15000)
      window.addEventListener('pywebviewready', ready, { once: true })
    })
    return call<T>(method, payload)
  }
  if (!result.ok) throw new Error(result.error || '操作未完成')
  return result.data as T
}
