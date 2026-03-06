/**
 * Supabase client factory for edge functions.
 * Uses service role key for write operations.
 */

import { createClient, SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

let _serviceClient: SupabaseClient | null = null;

/** Service-role client — full read/write access. */
export function getServiceClient(): SupabaseClient {
  if (_serviceClient) return _serviceClient;

  const url = Deno.env.get("SUPABASE_URL");
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !key) {
    throw new Error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY");
  }

  _serviceClient = createClient(url, key, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
  return _serviceClient;
}
