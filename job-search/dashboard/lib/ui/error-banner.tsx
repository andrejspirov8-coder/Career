'use client'

export function ErrorBanner({
  message,
  onRetry,
  children,
}: {
  message?: string
  onRetry?: () => void
  children?: React.ReactNode
}) {
  return (
    <div className="banner" role="alert">
      {children || <span>{message || 'An unexpected error occurred.'}</span>}
      {onRetry ? (
        <button className="button secondary" type="button" onClick={onRetry} style={{ marginLeft: 12 }}>
          Try again
        </button>
      ) : null}
    </div>
  )
}
