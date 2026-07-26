import '../app.css'
import type { Metadata } from 'next'

import { ErrorBoundary } from '@/lib/error-boundary'
import { ToastContainer } from '@/lib/toast'

export const metadata: Metadata = {
  title: 'Career Workspace',
  description: 'Private local job-search operations dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <link rel="icon" href="/icon.svg" sizes="any" type="image/svg+xml" />
      </head>
      <body>
        <ErrorBoundary>
          {children}
          <ToastContainer />
        </ErrorBoundary>
      </body>
    </html>
  )
}
