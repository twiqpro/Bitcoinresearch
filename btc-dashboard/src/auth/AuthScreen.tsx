import { useState, type FormEvent } from "react";
import { useAuth } from "./AuthProvider";

type Mode = "login" | "signup" | "reset";

export function AuthScreen() {
  const { signIn, signUp, requestPasswordReset } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const resetForm = () => {
    setError(null);
    setMessage(null);
  };

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    resetForm();
    setBusy(true);
    try {
      const { error: err } = await signIn(email.trim(), password);
      if (err) setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleSignup = async (e: FormEvent) => {
    e.preventDefault();
    resetForm();
    if (password.length < 8) {
      setError("Use at least 8 characters for the password.");
      return;
    }
    setBusy(true);
    try {
      const { error: err, needsEmailConfirmation } = await signUp(email.trim(), password);
      if (err) setError(err.message);
      else if (needsEmailConfirmation)
        setMessage("Check your email for a confirmation link, then sign in.");
      else setMessage("Account ready — signing you in.");
    } finally {
      setBusy(false);
    }
  };

  const handleReset = async (e: FormEvent) => {
    e.preventDefault();
    resetForm();
    setBusy(true);
    try {
      const { error: err } = await requestPasswordReset(email.trim());
      if (err) setError(err.message);
      else setMessage("If that address has an account, you will receive a reset email.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#121212] p-4 text-zinc-100">
      <div className="w-full max-w-sm rounded-xl border border-zinc-800 bg-zinc-900/60 p-6 shadow-xl">
        <h1 className="text-lg font-semibold tracking-tight text-white">BTC research lab</h1>
        <p className="mt-1 text-xs text-zinc-500">Sign in with your Supabase account.</p>

        <div className="mt-4 flex gap-1 rounded-lg border border-zinc-800 bg-zinc-950 p-0.5 text-xs">
          {(
            [
              ["login", "Log in"],
              ["signup", "Sign up"],
              ["reset", "Reset password"],
            ] as const
          ).map(([m, label]) => (
            <button
              key={m}
              type="button"
              onClick={() => {
                setMode(m);
                resetForm();
              }}
              className={`flex-1 rounded-md px-2 py-1.5 font-medium transition ${
                mode === m
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {mode === "login" && (
          <form className="mt-5 space-y-3" onSubmit={handleLogin}>
            <label className="block text-[10px] font-medium uppercase tracking-wider text-zinc-500">
              Email
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-600/50"
              />
            </label>
            <label className="block text-[10px] font-medium uppercase tracking-wider text-zinc-500">
              Password
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-600/50"
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-md border border-cyan-500/40 bg-cyan-500/15 py-2 text-sm font-medium text-cyan-400 hover:bg-cyan-500/25 disabled:opacity-50"
            >
              {busy ? "…" : "Log in"}
            </button>
          </form>
        )}

        {mode === "signup" && (
          <form className="mt-5 space-y-3" onSubmit={handleSignup}>
            <label className="block text-[10px] font-medium uppercase tracking-wider text-zinc-500">
              Email
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-600/50"
              />
            </label>
            <label className="block text-[10px] font-medium uppercase tracking-wider text-zinc-500">
              Password (8+ characters)
              <input
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-600/50"
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-md border border-emerald-500/40 bg-emerald-500/15 py-2 text-sm font-medium text-emerald-400 hover:bg-emerald-500/25 disabled:opacity-50"
            >
              {busy ? "…" : "Create account"}
            </button>
          </form>
        )}

        {mode === "reset" && (
          <form className="mt-5 space-y-3" onSubmit={handleReset}>
            <label className="block text-[10px] font-medium uppercase tracking-wider text-zinc-500">
              Email
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-cyan-600/50"
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-md border border-zinc-500/30 bg-zinc-800/80 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-800 disabled:opacity-50"
            >
              {busy ? "…" : "Send reset link"}
            </button>
          </form>
        )}

        {error && <p className="mt-3 text-xs text-rose-400">{error}</p>}
        {message && <p className="mt-3 text-xs text-cyan-400/90">{message}</p>}
      </div>
    </div>
  );
}
