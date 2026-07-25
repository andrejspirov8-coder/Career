import type { ReactNode } from 'react'
import { redirect } from 'next/navigation'
import { cookies, headers } from 'next/headers'
import { dashboardTokenFromEnv, isDashboardHeadersAuthorized, safeDashboardNextPath } from '@/lib/dashboard-auth'
import AppNavigation from './app-navigation'

export default async function DashboardLayout({
  children,
}: {
  children: ReactNode
}) {
  const expectedToken = dashboardTokenFromEnv()
  const headersList = await headers()
  
  if (!isDashboardHeadersAuthorized(expectedToken, headersList)) {
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
