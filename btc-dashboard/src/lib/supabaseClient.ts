import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL?.trim();
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim();

/** Reject untouched .env.example placeholders so we don’t silently call a fake URL. */
function looksLikeRealSupabaseEnv(u: string | undefined, k: string | undefined): boolean {
  if (!u || !k) return false;
  if (/YOUR_PROJECT_REF/i.test(u) || /your_anon_public_key/i.test(k)) return false;
  try {
    const parsed = new URL(u);
    if (parsed.protocol !== "https:") return false;
  } catch {
    return false;
  }
  // JWT-shaped anon keys are much longer than template strings
  if (k.length < 80) return false;
  return true;
}

export const isSupabaseConfigured = looksLikeRealSupabaseEnv(url, anonKey);

/** Null when URL or anon key are missing (show setup UI instead of crashing). */
export const supabase: SupabaseClient | null = isSupabaseConfigured
  ? createClient(url!, anonKey!, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : null;
