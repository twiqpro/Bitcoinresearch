/** Shown when VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are not set. */
export function SupabaseSetupScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#121212] p-4 text-zinc-100">
      <div className="w-full max-w-lg rounded-xl border border-amber-500/30 bg-zinc-900/60 p-6">
        <h1 className="text-lg font-semibold text-amber-200">Supabase not configured</h1>
        <p className="mt-2 text-sm text-zinc-400">
          In <code className="text-cyan-400">btc-dashboard/.env</code>, set your real Supabase URL and anon key
          from Project Settings → API. Replace placeholders like{" "}
          <code className="text-zinc-500">YOUR_PROJECT_REF</code> /
          <code className="text-zinc-500">your_anon_public_key</code>, save, then restart{" "}
          <code className="text-zinc-400">npm run dev</code>.
        </p>
        <ul className="mt-4 list-inside list-disc space-y-1 font-mono text-xs text-zinc-300">
          <li>VITE_SUPABASE_URL</li>
          <li>VITE_SUPABASE_ANON_KEY</li>
        </ul>
        <p className="mt-4 text-xs text-zinc-500">
          In the Supabase dashboard: Authentication → URL configuration → set Site URL to your app origin
          (e.g. <code className="text-zinc-400">http://localhost:5173</code> for local dev).
        </p>
      </div>
    </div>
  );
}
