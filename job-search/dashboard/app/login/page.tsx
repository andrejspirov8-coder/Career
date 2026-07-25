import { dashboardTokenFromEnv, safeDashboardNextPath } from '@/lib/dashboard-auth'
import LoginForm from './login-form'

export const dynamic = 'force-dynamic'

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>
}) {
  const params = await searchParams
  const nextPath = safeDashboardNextPath(params.next)

  return (
    <main className="loginPage">
      <LoginForm nextPath={nextPath} configured={Boolean(dashboardTokenFromEnv())} />
    </main>
  )
}
