'use client'

import { useEffect, useState, type ReactNode } from 'react'

export type ToastKind = 'success' | 'error' | 'info'

export interface ToastMessage {
  id: string
  kind: ToastKind
  text: string
  actionLabel?: string
  onAction?: () => void
}

const queue: ToastMessage[] = []
const listeners: Set<(queue: ToastMessage[]) => void> = new Set()

let nextId = 0

export function toast(kind: ToastKind, text: string, options?: { actionLabel?: string; onAction?: () => void }): void {
  const message: ToastMessage = {
    id: String(++nextId),
    kind,
    text,
    ...(options || {}),
  }
  queue.push(message)
  notify()
  setTimeout(dismiss, 6000)
}

function dismiss(): void {
  queue.shift()
  notify()
}

export function notify(): void {
  listeners.forEach((fn) => fn([...queue]))
}

export function subscribe(fn: (queue: ToastMessage[]) => void): () => void {
  listeners.add(fn)
  return () => { void listeners.delete(fn) }
}

export function ToastContainer(): ReactNode {
  const [items, setItems] = useState<ToastMessage[]>([])

  useEffect(() => {
    return subscribe(setItems)
  }, [])

  return (
    <div className="toastContainer" aria-live="polite">
      {items.map((item) => (
        <div key={item.id} className={`toast toast-${item.kind}`} role="status">
          <span>{item.text}</span>
          {item.actionLabel ? (
            <button className="textButton" type="button" onClick={() => { item.onAction?.(); dismiss() }}>
              {item.actionLabel}
            </button>
          ) : null}
        </div>
      ))}
    </div>
  )
}
