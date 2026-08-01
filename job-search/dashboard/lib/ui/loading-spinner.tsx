export function LoadingSpinner({
  size = 16,
  label = 'Loading',
}: {
  size?: number
  label?: string
}) {
  return (
    <span className="loadingSpinner" role="status" aria-label={label}>
      <span className="srOnly">{label}…</span>
    </span>
  )
}
