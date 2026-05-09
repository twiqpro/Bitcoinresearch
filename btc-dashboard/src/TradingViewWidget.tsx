import { memo, useEffect, useRef } from "react";

/** Matches TradingView advanced-chart embed config (see embed-widget-advanced-chart.js). */
const WIDGET_CONFIG: Record<string, unknown> = {
  allow_symbol_change: true,
  calendar: false,
  details: false,
  hide_side_toolbar: true,
  hide_top_toolbar: false,
  hide_legend: false,
  hide_volume: false,
  hotlist: false,
  interval: "240",
  locale: "en",
  save_image: true,
  style: "1",
  symbol: "BINANCE:BTCUSDT",
  theme: "light",
  timezone: "Etc/UTC",
  backgroundColor: "#ffffff",
  gridColor: "rgba(46, 46, 46, 0.06)",
  watchlist: [],
  withdateranges: false,
  compareSymbols: [],
  studies: [],
  autosize: true,
};

export const TradingViewWidget = memo(function TradingViewWidget() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;

    const script = document.createElement("script");
    script.src =
      "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.type = "text/javascript";
    script.async = true;
    script.dataset.tvInjected = "1";
    script.innerHTML = JSON.stringify(WIDGET_CONFIG);
    root.appendChild(script);

    return () => {
      script.remove();
      root
        .querySelector<HTMLDivElement>(".tradingview-widget-container__widget")
        ?.replaceChildren();
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="tradingview-widget-container min-h-0 w-full overflow-hidden rounded border border-zinc-800 bg-white"
      style={{ height: "100%", width: "100%" }}
    >
      <div
        className="tradingview-widget-container__widget min-h-0"
        style={{ height: "100%", width: "100%" }}
      />
    </div>
  );
});
