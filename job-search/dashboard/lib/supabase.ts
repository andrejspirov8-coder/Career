import { createClient as _createClient } from '@supabase/supabase-js'

const SUPABASE_URL_ENV = 'NEXT_PUBLIC_SUPABASE_URL'
const SUPABASE_ANON_KEY_ENV = 'NEXT_PUBLIC_SUPABASE_ANON_KEY'

export function createClient() {
  const supabaseUrl = process.env[SUPABASE_URL_ENV]
  const supabaseAnonKey = process.env[SUPABASE_ANON_KEY_ENV]

  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error(`${SUPABASE_URL_ENV} and ${SUPABASE_ANON_KEY_ENV} must be set`)
  }

  return _createClient(supabaseUrl, supabaseAnonKey)
}
