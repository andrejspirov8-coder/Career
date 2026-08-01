import type { ReactNode } from 'react'
import { redirect } from 'next/navigation'
import { headers } from 'next/headers'
import { safeDashboardNextPath } from '@/lib/dashboard-auth'
import { isDashboardPageAuthenticated } from '@/lib/dashboard-page-auth'
import AppNavigation from './app-navigation'

export default async function DashboardLayout({
  children,
}: {
  children: ReactNode
}) {
  const headersList = await headers()

  if (!(await isDashboardPageAuthenticated())) {
    const nextPath = safeDashboardNextPath(headersList.get('x-next-pathname') || '/')
    redirect(`/login?next=${encodeURIComponent(nextPath)}`)
  }

  return (
    <div className="appShell">
      <AppNavigation />
      <div className="appContent">{children}</div>
    </div>
  )
}
