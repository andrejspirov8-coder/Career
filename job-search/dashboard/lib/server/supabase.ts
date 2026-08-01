import { createClient } from '@supabase/supabase-js'

const SUPABASE_URL_ENV = 'SUPABASE_URL'
const SUPABASE_SERVICE_KEY_ENV = 'SUPABASE_SERVICE_ROLE_KEY'

export function createAdminClient() {
  const supabaseUrl = process.env[SUPABASE_URL_ENV]
  const supabaseServiceKey = process.env[SUPABASE_SERVICE_KEY_ENV]

  if (!supabaseUrl || !supabaseServiceKey) {
    throw new Error(`${SUPABASE_URL_ENV} and ${SUPABASE_SERVICE_KEY_ENV} must be set`)
  }

  return createClient(supabaseUrl, supabaseServiceKey)
}
