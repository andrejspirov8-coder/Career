'use client'

type SkeletonVariant = 'text' | 'circle' | 'card' | 'row'

export function Skeleton({
  width,
  height,
  variant = 'text',
  className = '',
  ...props
}: {
  width?: string | number
  height?: string | number
  variant?: SkeletonVariant
  className?: string
} & React.HTMLAttributes<HTMLDivElement>) {
  const style: React.CSSProperties = {
    ...(width ? { width: typeof width === 'number' ? width : width } : {}),
    ...(height ? { height: typeof height === 'number' ? height : height } : {}),
    ...(variant === 'circle' ? { borderRadius: '50%' } : variant === 'card' ? { borderRadius: 12, height: height || 72 } : variant === 'row' ? { borderRadius: 8, height: height || 36 } : { borderRadius: 4 }),
  }
  return <div className={`skeleton ${className}`} style={style} {...props} />
}

export function SkeletonList({
  count = 3,
  variant = 'row',
  height,
}: {
  count?: number
  variant?: SkeletonVariant
  height?: number
}) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} variant={variant} height={height} width="100%" style={{ marginTop: 8 }} />
      ))}
    </>
  )
}
