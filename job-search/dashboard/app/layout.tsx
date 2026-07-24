import '../app.css'
import type { Metadata } from 'next'

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
        <link rel="icon" href="/icon.svg" sizes="any" type="image/svg+xml" />
      </head>
      <body>{children}</body>
    </html>
  )
}
