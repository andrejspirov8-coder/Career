export function EmptyState({
  message,
  action,
  actionHref,
}: {
  message: string
  action?: string
  actionHref?: string
}) {
  return (
    <div className="emptyState">
      <p>{message}</p>
      {action && actionHref ? (
        <a className="buttonLink" href={actionHref}>{action}</a>
      ) : null}
    </div>
  )
}
