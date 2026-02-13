/**
 * 可复用的 WebSocket 客户端
 * 支持自动重连、心跳、消息回调
 */

export interface WSOptions {
  /** 重连间隔（毫秒），0 表示不重连 */
  reconnectInterval?: number
  /** 最大重连次数，-1 表示无限 */
  maxReconnects?: number
  /** 心跳间隔（毫秒），0 表示不发心跳 */
  heartbeatInterval?: number
  /** 收到消息的回调 */
  onMessage?: (data: any) => void
  /** 连接成功回调 */
  onConnected?: () => void
  /** 断开连接回调 */
  onDisconnected?: () => void
}

export class ChatWebSocket {
  private ws: WebSocket | null = null
  private url: string = ''
  private options: Required<WSOptions>
  private reconnectCount = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  private manualClose = false

  constructor(options: WSOptions = {}) {
    this.options = {
      reconnectInterval: options.reconnectInterval ?? 3000,
      maxReconnects: options.maxReconnects ?? 10,
      heartbeatInterval: options.heartbeatInterval ?? 25000,
      onMessage: options.onMessage ?? (() => {}),
      onConnected: options.onConnected ?? (() => {}),
      onDisconnected: options.onDisconnected ?? (() => {}),
    }
  }

  connect(url: string) {
    this.url = url
    this.manualClose = false
    this.reconnectCount = 0
    this._doConnect()
  }

  private _doConnect() {
    if (this.ws) {
      try { this.ws.close() } catch {}
      this.ws = null
    }

    try {
      this.ws = new WebSocket(this.url)
    } catch {
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this.reconnectCount = 0
      this._startHeartbeat()
      this.options.onConnected()
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'pong') return // 心跳响应，忽略
        this.options.onMessage(data)
      } catch {
        // 非 JSON 消息，忽略
      }
    }

    this.ws.onerror = () => {
      // onerror 之后通常会触发 onclose
    }

    this.ws.onclose = () => {
      this._stopHeartbeat()
      this.options.onDisconnected()
      if (!this.manualClose) {
        this._scheduleReconnect()
      }
    }
  }

  private _scheduleReconnect() {
    if (this.options.reconnectInterval <= 0) return
    if (this.options.maxReconnects >= 0 && this.reconnectCount >= this.options.maxReconnects) return

    this.reconnectTimer = setTimeout(() => {
      this.reconnectCount++
      this._doConnect()
    }, this.options.reconnectInterval)
  }

  private _startHeartbeat() {
    this._stopHeartbeat()
    if (this.options.heartbeatInterval <= 0) return
    this.heartbeatTimer = setInterval(() => {
      this.send({ type: 'ping' })
    }, this.options.heartbeatInterval)
  }

  private _stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  send(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }

  disconnect() {
    this.manualClose = true
    this._stopHeartbeat()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }
}

/**
 * 构建 WebSocket URL
 */
export function buildWsUrl(path: string, token: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}?token=${encodeURIComponent(token)}`
}
