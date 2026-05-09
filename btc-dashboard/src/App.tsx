import { useCallback, useEffect, useMemo, useState } from "react";
import { Line, LineChart, ResponsiveContainer } from "recharts";
import type { DashboardPayload } from "./types";
import { TradingViewWidget } from "./TradingViewWidget";

function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function fmtNum(v: number | null | undefined, digits = 3): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}

function Sidebar() {
  return (
    <aside className="flex w-12 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950 py-4">
      {["◇", "▤", "◎", "▦"].map((c, i) => (
        <button
          key={i}
          type="button"
          className="mb-3 px-3 text-xs text-zinc-500 hover:text-emerald-400"
          title="Nav"
        >
          {c}
        </button>
      ))}
    </aside>
  );
}

export default function App() {
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reloadDashboard = useCallback(async () => {
    setErr(null);
    setLoading(true);
    try {
      const r = await fetch(`/dashboard.json?_=${Date.now()}`, {
        cache: "no-store",
      });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const j = (await r.json()) as DashboardPayload;
      setData(j);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reloadDashboard();
  }, [reloadDashboard]);

  const lastPred = useMemo(() => {
    if (!data?.predictions?.length) return null;
    return data.predictions[data.predictions.length - 1];
  }, [data]);

  return (
    <div className="flex min-h-screen bg-[#121212] text-zinc-100">
      <Sidebar />
      <div className="grid min-w-0 flex-1 grid-cols-12 gap-0">
        {/* Asset rail */}
        <section className="col-span-12 border-b border-zinc-800 bg-zinc-950 py-2 pl-3 pr-4 md:col-span-2 md:border-b-0 md:border-r">
          <p className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-widest text-zinc-500">
            Watchlist
          </p>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-white">BTC-USD</span>
              <span className="text-xs text-emerald-400">RF backtest</span>
            </div>
            {lastPred && (
              <p className="mt-2 font-mono text-lg text-cyan-400">
                ${lastPred.close_t.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </p>
            )}
            <p className="mt-1 text-[10px] text-zinc-500">
              Last signal date: {lastPred?.signal_date ?? "—"}
            </p>
            <div className="mt-3 h-10 w-full min-w-0">
              {data?.predictions?.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={data.predictions.slice(-56).map((p) => ({
                      d: p.signal_date,
                      c: p.close_t,
                    }))}
                    margin={{ top: 2, right: 0, bottom: 0, left: 0 }}
                  >
                    <Line type="monotone" dataKey="c" stroke="#34d399" dot={false} strokeWidth={1.2} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full rounded bg-zinc-800/80" />
              )}
            </div>
          </div>
        </section>

        {/* Main */}
        <main className="col-span-12 space-y-4 p-4 md:col-span-10">
          <header className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-white">BTC research lab</h1>
              <p className="text-xs text-zinc-500">
                {data?.model_mode ?? "—"} · Updated {data?.generated_at ?? "—"}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={loading}
                title="Reload dashboard.json after running export_dashboard_data.py"
                onClick={() => void reloadDashboard()}
                className="rounded-md border border-cyan-500/35 bg-cyan-500/10 px-2.5 py-1 text-xs font-medium text-cyan-400 hover:bg-cyan-500/20 disabled:pointer-events-none disabled:opacity-50"
              >
                {loading ? "Refreshing…" : "Refresh dashboard"}
              </button>
              {loading && <span className="text-xs text-cyan-400">Loading…</span>}
              {err && <span className="text-xs text-rose-400">Load error: {err}</span>}
            </div>
          </header>

          <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
            <div className="mb-3">
              <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
                BTCUSDT — TradingView
              </h2>
              <p className="mt-0.5 text-[10px] text-zinc-500">
                Embedded advanced chart (Binance spot). Symbol and timeframe can be changed in the widget when
                allowed.
              </p>
            </div>
            <div className="h-[480px] w-full min-w-0 md:h-[520px]">
              <TradingViewWidget />
            </div>
          </div>

          <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
            <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Summary metrics
            </h2>
            <div className="overflow-x-auto text-xs">
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-zinc-800 text-zinc-500">
                    <th className="py-2 pr-2 font-medium">Metric</th>
                    <th className="py-2 pr-2 font-medium">Strategy</th>
                    <th className="py-2 font-medium">Buy &amp; hold</th>
                  </tr>
                </thead>
                <tbody className="font-mono text-zinc-300">
                  <tr className="border-b border-zinc-800/80">
                    <td className="py-1.5 text-zinc-500">Total return</td>
                    <td className={`py-1.5 ${(data?.metrics.total_return_strategy_pct ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {fmtPct(data?.metrics.total_return_strategy_pct)}
                    </td>
                    <td className={`py-1.5 ${(data?.metrics.total_return_bh_pct ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {fmtPct(data?.metrics.total_return_bh_pct)}
                    </td>
                  </tr>
                  <tr className="border-b border-zinc-800/80">
                    <td className="py-1.5 text-zinc-500">Sharpe</td>
                    <td className="py-1.5">{fmtNum(data?.metrics.sharpe_strategy)}</td>
                    <td className="py-1.5">{fmtNum(data?.metrics.sharpe_bh)}</td>
                  </tr>
                  <tr>
                    <td className="py-1.5 text-zinc-500">Max DD</td>
                    <td className="py-1.5 text-rose-300">{fmtPct(data?.metrics.max_dd_strategy_pct)}</td>
                    <td className="py-1.5 text-rose-300">{fmtPct(data?.metrics.max_dd_bh_pct)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
