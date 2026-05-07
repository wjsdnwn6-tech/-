import { useState, useEffect, useMemo, useRef } from 'react';
import {
  Search, Clock, Globe, X, TrendingUp, Activity,
  BarChart2, Layers, Filter, ChevronDown, ChevronRight, ArrowUpRight
} from 'lucide-react';

// ─── Types ───
type TickerAnalysis = { price: number; market_cap: number; ma20_support: boolean; ma60_support: boolean; pattern: string };
type TickerData = { display: string; ticker: string; name: string; analysis: TickerAnalysis };
type ThemeResult = { theme: string; krx: Record<string, TickerData[]> | null; nasdaq: Record<string, TickerData[]> | null };
type ScanResults = { timestamp: string; data: ThemeResult[] };
type FlatStock = {
  uid: string; theme: string; market: 'KRX' | 'NASDAQ'; ticker: string; name: string;
  display: string; price: number; marketCap: number; signals: string[]; tvSymbol: string;
  analysis: TickerAnalysis;
};

// ─── Constants ───
const SIGNAL_META: Record<string, { label: string; icon: string; color: string; bg: string; border: string }> = {
  monthly_pattern:             { label: '월봉 패턴 방어', icon: '🛡️', color: 'text-cyan-300',    bg: 'bg-cyan-500/15',    border: 'border-cyan-500/30' },
  cloud_twist:                 { label: '양운 전환',       icon: '🟢', color: 'text-emerald-300', bg: 'bg-emerald-500/15', border: 'border-emerald-500/30' },
  ma200_support_breakout:      { label: '200일선 지지/돌파', icon: '📈', color: 'text-pink-300',    bg: 'bg-pink-500/15',    border: 'border-pink-500/30' },
  '5yr_high_breakout':         { label: '5년 전고점 돌파',  icon: '🚀', color: 'text-rose-300',    bg: 'bg-rose-500/15',    border: 'border-rose-500/30' }
};
const ALL_SIGNALS = Object.keys(SIGNAL_META);

function getTVSymbol(ticker: string, market: 'KRX' | 'NASDAQ') {
  const clean = ticker.split(' ')[0].replace(/[()]/g, '').trim();
  if (market === 'KRX') return `KRX:${clean.replace('.KS', '').replace('.KQ', '')}`;
  return `NASDAQ:${clean}`;
}

function formatCap(cap: number, isUS: boolean, usdRate: number) {
  if (!cap || cap <= 0) return 'N/A';
  if (isUS) {
    const krw = cap * usdRate;
    const usd = cap >= 1e9 ? `${(cap / 1e9).toFixed(1)}B` : `${(cap / 1e6).toFixed(0)}M`;
    const k = krw >= 1e12 ? `${(krw / 1e12).toFixed(1)}조` : `${(krw / 1e8).toFixed(0)}억`;
    return `$${usd} (${k})`;
  }
  if (cap >= 1e12) return `${(cap / 1e12).toFixed(1)}조`;
  if (cap >= 1e8) return `${(cap / 1e8).toFixed(0)}억`;
  return `${cap.toLocaleString()}원`;
}

// ─── TradingView Chart ───
const TVChart = ({ symbol }: { symbol: string }) => {
  const ref = useRef<HTMLDivElement>(null);
  const id = 'tv_main_chart';

  useEffect(() => {
    if (ref.current) ref.current.innerHTML = '';
    const load = () => {
      if (typeof (window as any).TradingView !== 'undefined' && ref.current) {
        new (window as any).TradingView.widget({
          autosize: true, symbol, interval: 'M', timezone: 'Asia/Seoul',
          theme: 'dark', style: '1', locale: 'kr', hostname: 'kr.tradingview.com',
          enable_publishing: false, backgroundColor: '#020617', gridColor: '#1e293b',
          container_id: id,
          studies: [
            'IchimokuCloud@tv-basicstudies',
            { id: 'MASimple@tv-basicstudies', inputs: { length: 20 } },
            { id: 'MASimple@tv-basicstudies', inputs: { length: 60 } },
          ],
        });
      }
    };
    if (!(window as any).TradingView) {
      const s = document.createElement('script');
      s.src = 'https://s3.tradingview.com/tv.js';
      s.async = true; s.onload = load;
      document.head.appendChild(s);
    } else load();
  }, [symbol]);

  return <div id={id} ref={ref} className="w-full h-full" />;
};

// ─── Signal Badge ───
const SignalBadge = ({ sig }: { sig: string }) => {
  const m = SIGNAL_META[sig];
  if (!m) return null;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-md border ${m.bg} ${m.color} ${m.border}`}>
      <span>{m.icon}</span>{m.label}
    </span>
  );
};

// ─── Stock Card ───
const StockCard = ({ stock, isActive, usdRate, onClick }: {
  stock: FlatStock; isActive: boolean; usdRate: number; onClick: () => void;
}) => {
  const isUS = stock.market === 'NASDAQ';
  const multi = stock.signals.length > 1;
  return (
    <button onClick={onClick} className={`
      w-full text-left p-3.5 rounded-xl border transition-all duration-150 group
      ${isActive
        ? 'bg-blue-600/20 border-blue-500/60 shadow-lg shadow-blue-500/10'
        : multi
          ? 'bg-red-950/15 border-red-500/30 hover:bg-red-950/25 hover:border-red-500/50'
          : 'bg-slate-800/40 border-slate-700/40 hover:bg-slate-800/70 hover:border-slate-600'
      }
    `}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-extrabold text-sm text-white truncate">{stock.name}</span>
        <span className="text-[10px] font-mono text-slate-500 group-hover:text-slate-300 shrink-0 ml-2">{stock.ticker}</span>
      </div>
      <div className="flex items-center gap-3 mb-2 text-xs">
        <span className="font-bold text-blue-400">
          {isUS ? `$${stock.price.toLocaleString()}` : `₩${stock.price.toLocaleString()}`}
        </span>
        <span className="text-slate-500 text-[10px]">시총 {formatCap(stock.marketCap, isUS, usdRate)}</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {stock.signals.map(s => <SignalBadge key={s} sig={s} />)}
      </div>
    </button>
  );
};

// ─── Accordion Section ───
const SignalSection = ({ signal, stocks, activeId, usdRate, onSelect }: {
  signal: string; stocks: FlatStock[]; activeId: string | null; usdRate: number;
  onSelect: (s: FlatStock) => void;
}) => {
  const [open, setOpen] = useState(true);
  const m = SIGNAL_META[signal];
  if (!m || stocks.length === 0) return null;
  return (
    <div className="mb-4">
      <button onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full text-left py-1.5 px-1 hover:bg-slate-800/50 rounded-lg transition-colors">
        {open ? <ChevronDown className="w-3.5 h-3.5 text-slate-500" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-500" />}
        <span className={`text-xs font-black uppercase tracking-tight ${m.color}`}>{m.icon} {m.label}</span>
        <span className="text-[10px] text-slate-600 font-bold">{stocks.length}</span>
      </button>
      {open && (
        <div className="grid grid-cols-1 gap-2 mt-2 pl-1">
          {stocks.map(s => (
            <StockCard key={s.uid} stock={s} isActive={activeId === s.uid} usdRate={usdRate}
              onClick={() => onSelect(s)} />
          ))}
        </div>
      )}
    </div>
  );
};

// ─── Main App ───
export default function App() {
  const [data, setData] = useState<ScanResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selTheme, setSelTheme] = useState<string | null>(null);
  const [selMarket, setSelMarket] = useState<'ALL' | 'KRX' | 'NASDAQ'>('ALL');
  const [selSignals, setSelSignals] = useState<Set<string>>(new Set());
  const [selStock, setSelStock] = useState<FlatStock | null>(null);
  const [usdRate, setUsdRate] = useState(1400);

  useEffect(() => {
    fetch('https://open.er-api.com/v6/latest/USD').then(r => r.json())
      .then(j => setUsdRate(j.rates?.KRW ?? 1400)).catch(() => {});
    fetch('/scan_results.json').then(r => r.json())
      .then(j => { setData(j); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  // Flatten & deduplicate stocks
  const flatStocks = useMemo(() => {
    if (!data) return [];
    const map = new Map<string, FlatStock>();
    data.data.forEach(theme => {
      (['krx', 'nasdaq'] as const).forEach(mk => {
        const mData = mk === 'krx' ? theme.krx : theme.nasdaq;
        if (!mData) return;
        const market: 'KRX' | 'NASDAQ' = mk === 'krx' ? 'KRX' : 'NASDAQ';
        Object.entries(mData).forEach(([sig, tickers]) => {
          if (!tickers) return;
          tickers.forEach((t: any) => {
            const td: TickerData = typeof t === 'string'
              ? { display: t, ticker: t, name: t, analysis: { price: 0, market_cap: 0, ma20_support: false, ma60_support: false, pattern: '' } }
              : t;
            const uid = `${theme.theme}_${market}_${td.ticker}`;
            const existing = map.get(uid);
            if (existing) {
              if (!existing.signals.includes(sig)) existing.signals.push(sig);
            } else {
              map.set(uid, {
                uid, theme: theme.theme, market, ticker: td.ticker, name: td.name,
                display: td.display, price: td.analysis.price, marketCap: td.analysis.market_cap,
                signals: [sig], tvSymbol: getTVSymbol(td.ticker, market), analysis: td.analysis,
              });
            }
          });
        });
      });
    });
    return Array.from(map.values());
  }, [data]);

  // Filtered stocks
  const filtered = useMemo(() => {
    let list = flatStocks;
    if (selTheme) list = list.filter(s => s.theme === selTheme);
    if (selMarket !== 'ALL') list = list.filter(s => s.market === selMarket);
    if (selSignals.size > 0) list = list.filter(s => s.signals.some(sig => selSignals.has(sig)));
    if (search) {
      const t = search.toLowerCase();
      list = list.filter(s => s.name.toLowerCase().includes(t) || s.ticker.toLowerCase().includes(t) || s.theme.toLowerCase().includes(t));
    }
    // Sort: multi-signal first, then by name
    return list.sort((a, b) => b.signals.length - a.signals.length || a.name.localeCompare(b.name));
  }, [flatStocks, selTheme, selMarket, selSignals, search]);

  // Theme list with counts
  const themes = useMemo(() => {
    const HARDCODED_THEMES = [
      "IT (소프트웨어, 하드웨어, 반도체, IT 기기 및 서비스)",
      "커뮤니케이션 (통신, 미디어, 엔터테인먼트, 인터랙티브 미디어 및 서비스)",
      "임의소비재 (자동차 및 부품, 내구소비재, 의류, 레저, 호텔/레스토랑)",
      "필수소비재 (식음료, 유통, 가정용품, 개인용품, 담배)",
      "헬스케어 (제약, 생명공학(바이오), 의료기기, 헬스케어 서비스 및 장비)",
      "금융 (은행, 보험, 다각화된 금융 서비스, 소비자 금융)",
      "산업재 (자본재, 기계, 상업/전문 서비스, 운송 및 물류)",
      "소재 (화학, 건설자재, 금속 및 채광, 종이/포장재)",
      "에너지 (석유/가스 탐사 및 생산, 정제, 에너지 장비 및 서비스)",
      "유틸리티 (전력, 가스, 수도, 다각화된 재생에너지)",
      "부동산 (부동산 관리 및 개발, 리츠(REITs))"
    ];
    const counts = new Map<string, number>();
    HARDCODED_THEMES.forEach(t => counts.set(t, 0));
    flatStocks.forEach(s => {
      if (counts.has(s.theme)) {
        counts.set(s.theme, counts.get(s.theme)! + 1);
      }
    });
    return Array.from(counts.entries()); // Keeps the original 11 categories order
  }, [flatStocks]);

  // Group filtered by signal for accordion
  const groupedBySignal = useMemo(() => {
    const groups: Record<string, FlatStock[]> = {};
    ALL_SIGNALS.forEach(sig => { groups[sig] = []; });
    filtered.forEach(s => {
      s.signals.forEach(sig => {
        if (!groups[sig]) groups[sig] = [];
        // avoid duplicate cards: only add if not already there
        if (!groups[sig].find(x => x.uid === s.uid)) groups[sig].push(s);
      });
    });
    return groups;
  }, [filtered]);

  const toggleSignal = (sig: string) => {
    setSelSignals(prev => {
      const next = new Set(prev);
      if (next.has(sig)) next.delete(sig); else next.add(sig);
      return next;
    });
  };

  if (loading) return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <div className="w-12 h-12 border-4 border-blue-500/20 border-t-blue-500 rounded-full animate-spin" />
    </div>
  );

  const multiSignalCount = filtered.filter(s => s.signals.length > 1).length;

  return (
    <div className="h-screen flex flex-col bg-slate-950 text-slate-200 overflow-hidden">
      {/* ─── Header ─── */}
      <header className="shrink-0 bg-slate-900/95 backdrop-blur-md border-b border-slate-800 px-4 py-3 z-40">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg">
              <Layers className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-black text-white tracking-tight">
                Market <span className="text-blue-400">Scanner</span>
              </h1>
              <div className="flex items-center gap-1.5 text-[9px] text-slate-500 font-bold uppercase tracking-wider">
                <Clock className="w-2.5 h-2.5" />{data?.timestamp}
                <span className="mx-1">·</span>
                <span className="text-blue-400">{filtered.length}</span> 종목
                {multiSignalCount > 0 && <><span className="mx-1">·</span><span className="text-rose-400">{multiSignalCount} 교집합</span></>}
              </div>
            </div>
          </div>
          <div className="relative w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
            <input type="text" value={search} onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 bg-slate-800/60 border border-slate-700 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-blue-500/40"
              placeholder="종목/테마 검색..." />
          </div>
        </div>
      </header>

      {/* ─── Main: 2-Panel ─── */}
      <main className="flex-1 flex overflow-hidden">
        {/* ─── Left Panel ─── */}
        <aside className="w-[420px] shrink-0 border-r border-slate-800 flex flex-col bg-slate-950">
          {/* Theme Pills */}
          <div className="shrink-0 p-3 border-b border-slate-800/60">
            <div className="flex items-center gap-1.5 mb-2">
              <Filter className="w-3 h-3 text-slate-500" />
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">테마</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <button onClick={() => setSelTheme(null)}
                className={`text-[11px] font-bold px-2.5 py-1 rounded-lg border transition-all
                  ${!selTheme ? 'bg-blue-600 text-white border-blue-500' : 'bg-slate-800/50 text-slate-400 border-slate-700 hover:border-slate-500'}`}>
                전체
              </button>
              {themes.map(([t, c]) => (
                <button key={t} onClick={() => setSelTheme(selTheme === t ? null : t)}
                  className={`text-[11px] font-bold px-2.5 py-1 rounded-lg border transition-all truncate max-w-[140px]
                    ${selTheme === t ? 'bg-blue-600 text-white border-blue-500' : 'bg-slate-800/50 text-slate-400 border-slate-700 hover:border-slate-500'}`}>
                  {t.split(' (')[0]} <span className="text-[9px] opacity-60">{c}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Market & Signal Filters */}
          <div className="shrink-0 p-3 border-b border-slate-800/60 space-y-2.5">
            {/* Market Toggle */}
            <div className="flex items-center gap-1.5">
              <Globe className="w-3 h-3 text-slate-500" />
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mr-1">시장</span>
              {(['ALL', 'KRX', 'NASDAQ'] as const).map(m => (
                <button key={m} onClick={() => setSelMarket(m)}
                  className={`text-[11px] font-bold px-3 py-1 rounded-lg border transition-all
                    ${selMarket === m ? 'bg-blue-600 text-white border-blue-500' : 'bg-slate-800/50 text-slate-400 border-slate-700 hover:border-slate-500'}`}>
                  {m === 'ALL' ? '전체' : m}
                </button>
              ))}
            </div>
            {/* Signal Filters */}
            <div className="flex flex-wrap gap-1">
              {ALL_SIGNALS.map(sig => {
                const m = SIGNAL_META[sig];
                const active = selSignals.has(sig);
                return (
                  <button key={sig} onClick={() => toggleSignal(sig)}
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-md border transition-all
                      ${active ? `${m.bg} ${m.color} ${m.border}` : 'bg-slate-800/30 text-slate-500 border-slate-700/50 hover:border-slate-600'}`}>
                    {m.icon} {m.label}
                  </button>
                );
              })}
              {selSignals.size > 0 && (
                <button onClick={() => setSelSignals(new Set())}
                  className="text-[10px] text-slate-500 hover:text-slate-300 px-1">
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>

          {/* Stock List (Accordion by Signal) */}
          <div className="flex-1 overflow-y-auto p-3 space-y-1 custom-scrollbar">
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-slate-600 text-sm">
                <Activity className="w-8 h-8 mb-2 opacity-30" />
                <p>조건에 맞는 종목이 없습니다</p>
              </div>
            ) : (
              ALL_SIGNALS.map(sig => (
                <SignalSection key={sig} signal={sig} stocks={groupedBySignal[sig] || []}
                  activeId={selStock?.uid ?? null} usdRate={usdRate}
                  onSelect={s => setSelStock(s)} />
              ))
            )}
          </div>
        </aside>

        {/* ─── Right Panel: Chart ─── */}
        <section className="flex-1 flex flex-col bg-slate-950 min-w-0">
          {selStock ? (
            <>
              {/* Chart Header */}
              <div className="shrink-0 flex items-center justify-between px-5 py-3 bg-slate-900/60 border-b border-slate-800">
                <div className="flex items-center gap-3">
                  <BarChart2 className="w-5 h-5 text-blue-400" />
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-black text-white text-lg">{selStock.name}</span>
                      <span className="text-xs font-mono text-slate-500">{selStock.tvSymbol}</span>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${selStock.market === 'KRX' ? 'bg-blue-500/15 text-blue-300' : 'bg-rose-500/15 text-rose-300'}`}>
                        {selStock.market}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-sm font-bold text-blue-400">
                        {selStock.market === 'NASDAQ' ? `$${selStock.price.toLocaleString()}` : `₩${selStock.price.toLocaleString()}`}
                      </span>
                      <span className="text-[10px] text-slate-500">
                        시총 {formatCap(selStock.marketCap, selStock.market === 'NASDAQ', usdRate)}
                      </span>
                      <div className="flex gap-1 ml-1">
                        {selStock.signals.map(s => <SignalBadge key={s} sig={s} />)}
                      </div>
                    </div>
                  </div>
                </div>
                <button onClick={() => setSelStock(null)} className="p-1.5 hover:bg-slate-800 rounded-lg transition-colors">
                  <X className="w-4 h-4 text-slate-500" />
                </button>
              </div>
              {/* Chart */}
              <div className="flex-1">
                <TVChart symbol={selStock.tvSymbol} />
              </div>
            </>
          ) : (
            /* Empty State */
            <div className="flex-1 flex flex-col items-center justify-center text-center p-8">
              <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-blue-600/20 to-indigo-600/20 border border-blue-500/20 flex items-center justify-center mb-6">
                <TrendingUp className="w-10 h-10 text-blue-500/50" />
              </div>
              <h2 className="text-xl font-black text-slate-400 mb-2">종목을 선택하세요</h2>
              <p className="text-sm text-slate-600 max-w-xs">
                왼쪽 패널에서 종목을 클릭하면 월봉 차트가 표시됩니다.<br />
                일목균형표 + 20/60 이평선이 기본 적용됩니다.
              </p>
              <div className="flex items-center gap-2 mt-6 text-[10px] text-slate-600">
                <ArrowUpRight className="w-3 h-3" /> 테마·시장·시그널 필터로 종목을 좁혀보세요
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
