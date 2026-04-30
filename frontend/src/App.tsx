import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Search,
  Clock,
  Globe,
  X,
  Zap,
  TrendingUp,
  Activity,
  BarChart2,
  Shield,
  Layers,
  Filter,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';

type TickerAnalysis = {
  price: number;
  market_cap: number;
  ma20_support: boolean;
  ma60_support: boolean;
  pattern: string;
};

type TickerData = {
  display: string;
  ticker: string;
  name: string;
  analysis: TickerAnalysis;
};

type ThemeResult = {
  theme: string;
  krx: Record<string, TickerData[]> | null;
  nasdaq: Record<string, TickerData[]> | null;
};

type ScanResults = {
  timestamp: string;
  data: ThemeResult[];
};

type FlattenedTicker = {
  id: string;
  theme: string;
  market: 'KRX' | 'NASDAQ';
  indicatorKey: string;
  indicatorLabel: string;
  tvSymbol: string;
} & TickerData;

const INDICATOR_LABELS: Record<string, string> = {
  future_twist: "미래 구름대 양운 전환",
  breakout_red_cloud: "음운 상향 돌파",
  high_volume: "거래량 폭발",
  breakout_and_consolidation: "전고점 돌파 및 횡보",
  ma200_breakout: "200일선 돌파",
  monthly_bottom_reversal: "🔥 월봉 최저가 바닥 탈출"
};

const INDICATOR_COLORS: Record<string, string> = {
  future_twist: "text-yellow-400",
  breakout_red_cloud: "text-green-400",
  high_volume: "text-orange-400",
  breakout_and_consolidation: "text-purple-400",
  ma200_breakout: "text-pink-400",
  monthly_bottom_reversal: "text-indigo-400"
};

// TradingView Widget Component
const TVChart = ({ symbol, onClose }: { symbol: string; onClose: () => void }) => {
  const containerId = 'tv_chart_container_overlay';
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) containerRef.current.innerHTML = '';

    const loadWidget = () => {
      if (typeof (window as any).TradingView !== 'undefined' && containerRef.current) {
        new (window as any).TradingView.widget({
          autosize: true,
          symbol: symbol,
          interval: "1M",
          timezone: "Asia/Seoul",
          theme: "dark",
          style: "1",
          locale: "kr",
          hostname: "kr.tradingview.com", // Ensure Korean regional data resolution
          enable_publishing: false,
          backgroundColor: "#000000",
          gridColor: "#111111",
          container_id: containerId,
          saved_chart: "qHQNs4ra", // User's personal layout ID
          studies: ["IchimokuCloud@tv-basicstudies"] // Fallback indicator
        });
      }
    };

    if (!(window as any).TradingView) {
      const script = document.createElement('script');
      script.src = 'https://s3.tradingview.com/tv.js';
      script.async = true;
      script.onload = loadWidget;
      document.head.appendChild(script);
    } else loadWidget();
  }, [symbol]);

  return (
    <div className="fixed inset-y-0 right-0 w-full lg:w-3/4 bg-slate-900 shadow-2xl z-50 border-l border-slate-700 flex flex-col animate-in slide-in-from-right duration-300">
      <div className="h-14 flex items-center justify-between px-6 bg-slate-800 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <BarChart2 className="w-5 h-5 text-blue-400" />
          <span className="font-bold text-slate-100">{symbol} 실시간 월봉 차트</span>
        </div>
        <button onClick={onClose} className="p-2 hover:bg-slate-700 rounded-full transition-colors">
          <X className="w-6 h-6 text-slate-400" />
        </button>
      </div>
      <div id={containerId} ref={containerRef} className="flex-1" />
    </div>
  );
};

const INDICATOR_TAG_STYLES: Record<string, string> = {
  future_twist: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  breakout_red_cloud: "bg-rose-500/20 text-rose-300 border-rose-500/30",
  high_volume: "bg-orange-500/20 text-orange-300 border-orange-500/30",
  breakout_and_consolidation: "bg-indigo-500/20 text-indigo-300 border-indigo-500/30",
  ma200_breakout: "bg-pink-500/20 text-pink-300 border-pink-500/30",
  monthly_bottom_reversal: "bg-violet-500/20 text-violet-300 border-violet-500/30"
};

const TickerPill = ({
  item,
  onClick,
  isIntersection,
  allIndicators,
  usdRate
}: {
  item: FlattenedTicker;
  onClick: () => void;
  isIntersection: boolean;
  allIndicators: { key: string; label: string }[];
  usdRate: number;
}) => {
  const { analysis } = item;
  
  const formatCap = (cap: number) => {
    if (!cap) return "N/A";
    if (cap >= 1e12) return `${(cap / 1e12).toFixed(1)}T`;
    if (cap >= 1e8) return `${(cap / 1e8).toFixed(0)}억`;
    if (cap >= 1e4) return `${(cap / 1e4).toFixed(0)}만`;
    return cap.toLocaleString();
  };

  const renderPrice = () => {
    if (analysis.price <= 0) return null;
    
    const isUS = item.market === 'NASDAQ';
    const krwPrice = isUS ? Math.round(analysis.price * usdRate) : analysis.price;
    
    const formatCap = (cap: number) => {
      if (!cap || cap <= 0) return "해당사항 없음";
      
      const toKRWStr = (val: number) => {
        if (val >= 1e12) return `${(val / 1e12).toFixed(1)}조`;
        if (val >= 1e8) return `${(val / 1e8).toFixed(0)}억`;
        return `${val.toLocaleString()}원`;
      };

      if (isUS) {
        const usdStr = cap >= 1e9 ? `${(cap / 1e9).toFixed(1)}B달러` : `${(cap / 1e6).toFixed(0)}M달러`;
        const krwStr = toKRWStr(cap * usdRate);
        return `${usdStr} (원화 ${krwStr})`;
      }
      
      return toKRWStr(cap);
    };

    return (
      <div className="flex flex-col gap-0.5">
        <div className="flex items-center gap-2">
          <span className={`font-black text-base transition-colors ${isIntersection ? 'text-rose-400' : 'text-blue-400'}`}>
            {isUS ? `${analysis.price.toLocaleString()}달러` : `${analysis.price.toLocaleString()}원`}
          </span>
          {isUS && (
            <span className="text-[10px] text-slate-500 font-bold">
              ({krwPrice.toLocaleString()}원)
            </span>
          )}
        </div>
        <div className="text-[10px] font-bold text-slate-500 flex items-center gap-1">
          <span className="opacity-60">시총:</span>
          <span className={analysis.market_cap > 0 ? "text-slate-400" : ""}>{formatCap(analysis.market_cap)}</span>
        </div>
      </div>
    );
  };
  
  return (
    <button
      onClick={onClick}
      className={`
        group relative flex flex-col items-start gap-2 p-4 rounded-2xl text-sm font-medium transition-all duration-200 text-left
        ${isIntersection 
          ? 'bg-red-950/20 text-red-100 border-2 border-red-500/60 shadow-[0_0_20px_rgba(239,68,68,0.15)] hover:bg-red-950/30 hover:border-red-500' 
          : 'bg-slate-800/40 text-slate-200 border border-slate-700/50 hover:bg-slate-800/60 hover:border-slate-600'
        }
      `}
    >
      <div className="flex items-center justify-between w-full gap-4">
        <span className={`font-extrabold text-lg tracking-tight transition-colors ${isIntersection ? 'text-white group-hover:text-red-400' : 'text-white group-hover:text-blue-400'}`}>
          {item.name}
        </span>
        <span className="text-xs font-mono opacity-40 group-hover:opacity-100">{item.ticker}</span>
      </div>
      
      <div className="flex flex-col gap-2 mt-0.5 w-full">
        {renderPrice()}
        
        {/* 교집합일 경우 중복된 모든 조건들을 전용 색상 박스로 표시 */}
        {isIntersection && (
          <div className="flex flex-wrap gap-1.5 mt-1">
            {allIndicators.map((ind, i) => (
              <span key={i} className={`text-[10px] px-2 py-0.5 rounded-lg border font-black uppercase tracking-tighter ${INDICATOR_TAG_STYLES[ind.key] || 'bg-slate-700 text-slate-300'}`}>
                {ind.label}
              </span>
            ))}
          </div>
        )}
      </div>
    </button>
  );
};

const MarketSection = ({
  title,
  data,
  market,
  theme,
  onTickerClick,
  intersections,
  usdRate
}: {
  title: string;
  data: Record<string, TickerData[]>;
  market: 'KRX' | 'NASDAQ';
  theme: string;
  onTickerClick: (symbol: string) => void;
  intersections: Record<string, { key: string; label: string }[]>;
  usdRate: number;
}) => {
  const hasData = Object.values(data).some(arr => arr && arr.length > 0);
  if (!hasData) return (
    <div className="flex-1 flex items-center justify-center py-10 opacity-30 italic text-sm">
      데이터 없음
    </div>
  );

  const getTVSymbol = (ticker: string, market: 'KRX' | 'NASDAQ') => {
    const cleanTicker = ticker.split(' ')[0].replace(/[()]/g, '').trim();
    if (market === 'KRX') {
      const rawCode = cleanTicker.replace('.KS', '').replace('.KQ', '');
      return `KRX:${rawCode}`;
    }
    return `NASDAQ:${cleanTicker}`;
  };

  return (
    <div className="flex-1 min-w-[300px]">
      <div className="flex items-center gap-4 mb-10 border-b-2 border-slate-700 pb-5">
        <Globe className={`w-8 h-8 ${market === 'KRX' ? 'text-blue-400' : 'text-rose-400'}`} />
        <h4 className="text-3xl font-black text-slate-100 uppercase tracking-tighter">{title}</h4>
      </div>
      <div className="space-y-8">
        {Object.entries(data).map(([indicator, tickers]) => {
          if (!tickers || tickers.length === 0) return null;
          return (
            <div key={indicator} className="space-y-3">
              <div className="flex items-center gap-3 px-1">
                <Activity className={`w-5 h-5 ${INDICATOR_COLORS[indicator] || 'text-slate-500'}`} />
                <span className="text-lg font-black text-slate-300 uppercase tracking-tighter">
                  {INDICATOR_LABELS[indicator] || indicator}
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {tickers.map((t: any, idx) => {
                  const tickerObj: TickerData = typeof t === 'string' ? {
                    display: t,
                    ticker: t.match(/\(([^)]+)\)/)?.[1] || t,
                    name: t.split('(')[0],
                    analysis: { price: 0, market_cap: 0, ma20_support: false, ma60_support: false, pattern: "" }
                  } : t;

                  const tickerId = `${theme}_${tickerObj.ticker}`;
                  const labels = intersections[tickerId] || [];
                  const isIntersection = labels.length > 1;

                  return (
                    <TickerPill
                      key={`${indicator}-${idx}`}
                      isIntersection={isIntersection}
                      allIndicators={labels}
                      usdRate={usdRate}
                      item={{
                        ...tickerObj,
                        id: `${theme}-${market}-${indicator}-${idx}`,
                        theme,
                        market,
                        indicatorKey: indicator,
                        indicatorLabel: INDICATOR_LABELS[indicator] || indicator,
                        tvSymbol: getTVSymbol(tickerObj.ticker, market)
                      }}
                      onClick={() => {
                        const targetSymbol = getTVSymbol(tickerObj.ticker, market);
                        console.log('선택된 심볼:', targetSymbol);
                        onTickerClick(targetSymbol);
                      }}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default function App() {
  const [data, setData] = useState<ScanResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [usdRate, setUsdRate] = useState(1350); // Default fallback

  useEffect(() => {
    // Fetch USD rate
    fetch('https://open.er-api.com/v6/latest/USD')
      .then(res => res.json())
      .then(json => setUsdRate(json.rates.KRW))
      .catch(err => console.error("Failed to fetch exchange rate", err));

    fetch('/scan_results.json')
      .then(res => res.json())
      .then(json => {
        setData(json);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to fetch data", err);
        setLoading(false);
      });
  }, []);

  const filteredThemes = useMemo(() => {
    if (!data) return [];
    if (!searchTerm) return data.data;
    const term = searchTerm.toLowerCase();
    return data.data.filter(theme => {
      if (theme.theme.toLowerCase().includes(term)) return true;
      const checkMarket = (m: Record<string, any[]> | null) =>
        m && Object.values(m).some(tickers => tickers.some((t: any) => {
          if (typeof t === 'string') return t.toLowerCase().includes(term);
          return t.name.toLowerCase().includes(term) || t.ticker.toLowerCase().includes(term);
        }));
      return checkMarket(theme.krx) || checkMarket(theme.nasdaq);
    });
  }, [data, searchTerm]);

  const tickerIntersections = useMemo(() => {
    const counts: Record<string, { key: string; label: string }[]> = {};
    if (!data) return counts;

    data.data.forEach(theme => {
      const processMarket = (market: Record<string, any[]> | null) => {
        if (!market) return;
        Object.entries(market).forEach(([indicator, tickers]) => {
          tickers.forEach((t: any) => {
            const ticker = typeof t === 'string' ? t.match(/\(([^)]+)\)/)?.[1] || t : t.ticker;
            const key = `${theme.theme}_${ticker}`;
            const label = INDICATOR_LABELS[indicator] || indicator;

            if (!counts[key]) counts[key] = [];
            if (!counts[key].some(item => item.key === indicator)) {
              counts[key].push({ key: indicator, label });
            }
          });
        });
      };
      processMarket(theme.krx);
      processMarket(theme.nasdaq);
    });
    return counts;
  }, [data]);

  if (loading) return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <div className="w-12 h-12 border-4 border-blue-500/20 border-t-blue-500 rounded-full animate-spin"></div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 flex flex-col">
      <header className="sticky top-0 z-40 bg-slate-900/90 backdrop-blur-md border-b border-slate-800 px-6 py-5">
        <div className="max-w-[1600px] mx-auto flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="p-2.5 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl shadow-lg">
              <Layers className="w-7 h-7 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-black text-white tracking-tighter uppercase">Market <span className="text-blue-500">Intelligence</span></h1>
              <div className="flex items-center gap-2 text-[10px] text-slate-500 font-bold mt-0.5 tracking-widest uppercase">
                <Clock className="w-3 h-3" /> {data?.timestamp} 업데이트됨
              </div>
            </div>
          </div>
          <div className="relative w-full md:w-[400px]">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              type="text"
              className="w-full pl-12 pr-4 py-3 bg-slate-800/50 border border-slate-700 rounded-2xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all"
              placeholder="테마 또는 종목 검색..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
        </div>
      </header>

      <main className="flex-1 p-6 lg:p-12 max-w-[1600px] mx-auto w-full space-y-16">
        {filteredThemes.map((theme, idx) => (
          <section key={idx} className="animate-in fade-in slide-in-from-bottom-6 duration-700 fill-mode-both" style={{ animationDelay: `${idx * 100}ms` }}>
            <div className="flex items-center gap-6 mb-8">
              <h2 className="text-3xl font-black text-white tracking-tight">{theme.theme}</h2>
              <div className="h-px flex-1 bg-slate-800" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-px bg-slate-800 border border-slate-800 rounded-3xl overflow-hidden shadow-2xl">
              <div className="p-8 lg:p-10 bg-slate-900/40 backdrop-blur-sm">
                <MarketSection title="KRX Market" data={theme.krx || {}} market="KRX" theme={theme.theme} onTickerClick={setSelectedSymbol} intersections={tickerIntersections} usdRate={usdRate} />
              </div>
              <div className="p-8 lg:p-10 bg-slate-900/60 backdrop-blur-sm">
                <MarketSection title="US Market" data={theme.nasdaq || {}} market="NASDAQ" theme={theme.theme} onTickerClick={setSelectedSymbol} intersections={tickerIntersections} usdRate={usdRate} />
              </div>
            </div>
          </section>
        ))}
      </main>

      {selectedSymbol && <TVChart symbol={selectedSymbol} onClose={() => setSelectedSymbol(null)} />}
    </div>
  );
}
