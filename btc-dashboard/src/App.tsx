import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  DashboardPayload,
  DeltaCandle,
  DeltaPerpPayload,
} from "./types";

const grid = { stroke: "#27272a", strokeDasharray: "3 3" as const };
const axis = { stroke: "#71717a", fontSize: 10, fill: "#a1a1aa" };

function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function fmtNum(v: number | null | undefined, digits = 3): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(digits);
}

function sliceCandles(rows: DeltaCandle[], lastHours: number): DeltaCandle[] {
  if (!rows.length) return [];
  if (lastHours <= 0) return rows;
  const lastT = rows[rows.length - 1].time;
  const cutoff = lastT - lastHours * 3600;
  return rows.filter((r) => r.time >= cutoff);
}

function axisSpanHours(full: DeltaCandle[], viewHours: number): number {
  if (viewHours > 0) return viewHours;
  if (full.length < 2) return 24;
  return Math.max(1, (full[full.length - 1].time - full[0].time) / 3600);
}

function formatAxisTime(tSec: number, spanH: number): string {
  const d = new Date(tSec * 1000);
  if (spanH <= 72) return d.toISOString().slice(11, 16);
  return d.toISOString().slice(5, 16);
}

const DELTA_VIEW_PRESETS: { label: string; hours: number }[] = [
  { label: "6 h", hours: 6 },
  { label: "24 h", hours: 24 },
  { label: "3 d", hours: 72 },
  { label: "7 d", hours: 168 },
  { label: "14 d", hours: 336 },
  { label: "Full file", hours: 0 },
];

/** Recharts Scatter point + yAxis from getComposedData */
type ScatterPointProps = {
  cx: number;
  cy: number;
  payload: DeltaCandle & { label?: string };
  yAxis?: { scale: (v: number) => number };
};

function DeltaCandlestickShape(
  props: ScatterPointProps & { bodyHalfWidth: number },
) {
  const { cx, payload, bodyHalfWidth } = props;
  const scale = props.yAxis?.scale;
  if (!scale || payload == null) return null;

  const yHigh = scale(payload.high);
  const yLow = scale(payload.low);
  const yOpen = scale(payload.open);
  const yClose = scale(payload.close);
  const bullish = payload.close >= payload.open;
  const fill = bullish ? "#22c55e" : "#ef4444";
  const stroke = bullish ? "#16a34a" : "#dc2626";

  const bodyTop = Math.min(yOpen, yClose);
  const bodyBot = Math.max(yOpen, yClose);
  const bodyH = Math.max(bodyBot - bodyTop, 1);
  const w = bodyHalfWidth * 2;

  return (
    <g className="delta-candle">
      <line
        x1={cx}
        x2={cx}
        y1={yHigh}
        y2={yLow}
        stroke={stroke}
        strokeWidth={1}
        strokeLinecap="square"
      />
      <rect
        x={cx - bodyHalfWidth}
        y={bodyTop}
        width={w}
        height={bodyH}
        fill={fill}
        fillOpacity={0.82}
        stroke={stroke}
        strokeWidth={1}
      />
    </g>
  );
}

/** Exponential moving average; indexes before seed use `null`. */
function emaSeries(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = values.map(() => null);
  if (values.length < period) return out;
  const k = 2 / (period + 1);
  let ema =
    values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = ema;
  for (let i = period; i < values.length; i++) {
    ema = values[i] * k + ema * (1 - k);
    out[i] = ema;
  }
  return out;
}

type CandleWithEma = DeltaCandle & {
  label: string;
  ema9: number | null;
  ema20: number | null;
};

function yPriceDomain(rows: CandleWithEma[]): [number, number] {
  if (!rows.length) return [0, 1];
  let lo = Infinity;
  let hi = -Infinity;
  for (const c of rows) {
    lo = Math.min(lo, c.low);
    hi = Math.max(hi, c.high);
    if (c.ema9 != null) {
      lo = Math.min(lo, c.ema9);
      hi = Math.max(hi, c.ema9);
    }
    if (c.ema20 != null) {
      lo = Math.min(lo, c.ema20);
      hi = Math.max(hi, c.ema20);
    }
  }
  const pad = (hi - lo) * 0.02 || hi * 0.001 || 1;
  return [lo - pad, hi + pad];
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

function DeltaPerpPanel() {
  const [bundle, setBundle] = useState<DeltaPerpPayload | null>(null);
  const [deltaErr, setDeltaErr] = useState<string | null>(null);
  const [deltaLoading, setDeltaLoading] = useState(true);
  const [symbol, setSymbol] = useState<"BTCUSD" | "ETHUSD">("BTCUSD");
  const [viewHours, setViewHours] = useState(24);

  /** Reload candles from `/delta_perp_candles.json` (bypasses browser cache after you re-export). */
  const reloadDeltaBundle = useCallback(async () => {
    setDeltaErr(null);
    setDeltaLoading(true);
    try {
      const r = await fetch(`/delta_perp_candles.json?_=${Date.now()}`, {
        cache: "no-store",
      });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const j = (await r.json()) as DeltaPerpPayload;
      setBundle(j);
    } catch (e) {
      setDeltaErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDeltaLoading(false);
    }
  }, []);

  useEffect(() => {
    void reloadDeltaBundle();
  }, [reloadDeltaBundle]);

  const full = bundle?.candles?.[symbol] ?? [];
  const spanH = axisSpanHours(full, viewHours);
  const chartData = useMemo((): CandleWithEma[] => {
    const sliced = sliceCandles(full, viewHours);
    const closes = sliced.map((c) => c.close);
    const ema9 = emaSeries(closes, 9);
    const ema20 = emaSeries(closes, 20);
    return sliced.map((c, i) => ({
      ...c,
      label: formatAxisTime(c.time, spanH),
      ema9: ema9[i],
      ema20: ema20[i],
    }));
  }, [full, viewHours, spanH]);

  const yDomain = useMemo(() => yPriceDomain(chartData), [chartData]);
  const bodyHalfWidth = useMemo(() => {
    const n = chartData.length;
    if (n <= 1) return 4;
    return Math.max(1.5, Math.min(6, 320 / n));
  }, [chartData.length]);

  const candleShape = useMemo(
    () => (p: ScatterPointProps) => (
      <DeltaCandlestickShape {...p} bodyHalfWidth={bodyHalfWidth} />
    ),
    [bodyHalfWidth],
  );

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
            Delta perpetual futures (India)
          </h2>
          <p className="mt-0.5 text-[10px] text-zinc-500">
            File: <code className="text-zinc-400">delta_perp_candles.json</code> · OHLC{" "}
            {bundle?.resolution ?? "—"} · Loaded window{" "}
            <span className="text-zinc-300">{bundle?.fetch_hours ?? "—"} h</span> ·{" "}
            {bundle?.generated_at ?? "—"} · EMA crossovers (9 / 20) on close{" "}
            <span className="text-orange-400">●</span> 9 · <span className="text-zinc-100">●</span>{" "}
            20
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-[10px] text-zinc-500">
            Instrument
            <select
              className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value as "BTCUSD" | "ETHUSD")}
            >
              <option value="BTCUSD">BTCUSD</option>
              <option value="ETHUSD">ETHUSD</option>
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-[10px] text-zinc-500">
            Chart window
            <select
              className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200"
              value={viewHours}
              onChange={(e) => setViewHours(Number(e.target.value))}
            >
              {DELTA_VIEW_PRESETS.map((o) => (
                <option key={o.label} value={o.hours}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={deltaLoading}
            title="Reload delta_perp_candles.json from the server. Run export_delta_dashboard.py first if you need new candles from the API."
            onClick={() => void reloadDeltaBundle()}
            className="rounded-md border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-400 hover:bg-emerald-500/25 disabled:pointer-events-none disabled:opacity-50"
          >
            {deltaLoading ? "Refreshing…" : "Refresh candles"}
          </button>
        </div>
      </div>

      {deltaLoading && <p className="text-xs text-cyan-400">Loading Delta bundle…</p>}
      {deltaErr && <p className="text-xs text-rose-400">Delta bundle: {deltaErr}</p>}

      <div className="h-72 w-full min-w-0">
        {chartData.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid {...grid} />
              <XAxis
                type="number"
                dataKey="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(t) => formatAxisTime(Number(t), spanH)}
                tick={axis}
                tickMargin={8}
                minTickGap={24}
              />
              <YAxis tick={axis} width={52} domain={yDomain} />
              <Tooltip
                cursor={{ stroke: "#71717a", strokeWidth: 1, strokeDasharray: "4 4" }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const row = payload[0].payload as CandleWithEma;
                  const d = new Date(row.time * 1000);
                  const hdr = `${d.toISOString().replace("T", " ").slice(0, 19)} UTC`;
                  const rowFmt = (k: keyof DeltaCandle) =>
                    typeof row[k] === "number"
                      ? (row[k] as number).toLocaleString(undefined, { maximumFractionDigits: 2 })
                      : "—";
                  const emaFmt = (v: number | null) =>
                    v != null
                      ? v.toLocaleString(undefined, { maximumFractionDigits: 2 })
                      : "—";
                  const up = row.close >= row.open;
                  return (
                    <div className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-[11px] text-zinc-200 shadow-xl">
                      <div className="mb-1 text-zinc-500">{hdr}</div>
                      <div>O {rowFmt("open")}</div>
                      <div>H {rowFmt("high")}</div>
                      <div>L {rowFmt("low")}</div>
                      <div>C {rowFmt("close")}</div>
                      <div className="text-orange-400">EMA 9 {emaFmt(row.ema9)}</div>
                      <div className="text-zinc-100">EMA 20 {emaFmt(row.ema20)}</div>
                      <div className="text-zinc-500">Vol {rowFmt("volume")}</div>
                      <div className={`mt-1 ${up ? "text-emerald-400" : "text-rose-400"}`}>
                        {up ? "Bullish candle" : "Bearish candle"}
                      </div>
                    </div>
                  );
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Scatter
                name="OHLC"
                dataKey="close"
                fill="transparent"
                shape={candleShape}
                isAnimationActive={false}
                legendType="none"
              />
              <Line
                type="monotone"
                dataKey="ema20"
                name="EMA 20"
                stroke="#fafafa"
                strokeWidth={1.5}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="ema9"
                name="EMA 9"
                stroke="#fb923c"
                strokeWidth={1.6}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-zinc-500">
            <p>No candles in bundle for {symbol}.</p>
            <p className="max-w-md text-xs leading-relaxed text-zinc-600">
              Export from the repo root:{" "}
              <code className="rounded bg-zinc-800 px-1 text-zinc-400">
                .venv/bin/python export_delta_dashboard.py --hours 168 --resolution 5m
              </code>{" "}
              then click <strong className="text-zinc-400">Refresh candles</strong> above (or run{" "}
              <code className="text-zinc-400">scripts/refresh_dashboard.sh</code> for a full rebuild).
            </p>
          </div>
        )}
      </div>

      <p className="mt-2 text-[10px] leading-relaxed text-zinc-600">
        <strong className="text-zinc-500">Fetch depth</strong> is set when you export ({" "}
        <code className="rounded bg-zinc-800 px-1">--hours</code>,         <code className="rounded bg-zinc-800 px-1">--resolution</code>
        ), then use <strong className="text-zinc-500">Refresh candles</strong>. The app cannot call Delta directly from
        the browser (CORS); it only reloads the JSON file.
      </p>
    </div>
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

          <DeltaPerpPanel />

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
