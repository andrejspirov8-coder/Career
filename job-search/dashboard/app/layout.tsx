import '../app.css'
import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import { isDashboardPageAuthenticated } from '../lib/dashboard-page-auth'
import AppNavigation from './app-navigation'

export const metadata: Metadata = {
  title: 'Career Workspace',
  description: 'Private local job-search operations dashboard',
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const authenticated = await isDashboardPageAuthenticated()
  return (
    <html lang="en">
      <body>
        {authenticated ? (
          <div className="appShell">
            <AppNavigation />
            <div className="appContent">{children}</div>
          </div>
        ) : children}
      </body>
    </html>
  )
}
