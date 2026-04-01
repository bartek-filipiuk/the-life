import { useMemo } from 'react';
import type { DayStat, TagCount } from '../lib/api';

interface StatsChartsProps {
  costPerDay: DayStat[];
  topTags: TagCount[];
}

/**
 * Simple SVG-based charts for the stats dashboard.
 * No external charting library needed — just clean SVG.
 */
export default function StatsCharts({ costPerDay, topTags }: StatsChartsProps) {
  return (
    <div className="space-y-8">
      <CostChart data={costPerDay} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TokensChart data={costPerDay} />
        <RoomsPerDayChart data={costPerDay} />
      </div>
      <TopTagsChart tags={topTags} />
    </div>
  );
}

// ── Cost Over Time Chart ───────────────────────────────────────────────

function CostChart({ data }: { data: DayStat[] }) {
  const { points, maxCost, width, height, padding } = useMemo(() => {
    const w = 800;
    const h = 250;
    const p = { top: 20, right: 20, bottom: 40, left: 60 };

    if (data.length === 0) return { points: '', maxCost: 0, width: w, height: h, padding: p };

    // Cumulative cost
    let cumulative = 0;
    const cumulativeData = data.map((d) => {
      cumulative += d.cost;
      return { ...d, cumCost: cumulative };
    });

    const max = Math.max(...cumulativeData.map((d) => d.cumCost), 0.01);
    const chartW = w - p.left - p.right;
    const chartH = h - p.top - p.bottom;

    const pts = cumulativeData
      .map((d, i) => {
        const x = p.left + (i / Math.max(cumulativeData.length - 1, 1)) * chartW;
        const y = p.top + chartH - (d.cumCost / max) * chartH;
        return `${x},${y}`;
      })
      .join(' ');

    return { points: pts, maxCost: max, width: w, height: h, padding: p };
  }, [data]);

  if (data.length === 0) {
    return <EmptyChart label="Cost Over Time" />;
  }

  return (
    <div className="rounded-lg border border-white/5 bg-white/[0.02] p-6">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.3em] text-cost/70 mb-4">
        Cumulative Cost Over Time
      </h3>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
          const y = padding.top + (height - padding.top - padding.bottom) * (1 - pct);
          return (
            <g key={pct}>
              <line
                x1={padding.left}
                y1={y}
                x2={width - padding.right}
                y2={y}
                stroke="white"
                strokeOpacity={0.05}
              />
              <text
                x={padding.left - 8}
                y={y + 4}
                textAnchor="end"
                className="fill-white/20"
                fontSize={10}
                fontFamily="monospace"
              >
                ${(maxCost * pct).toFixed(2)}
              </text>
            </g>
          );
        })}

        {/* Area fill */}
        <polygon
          points={`${padding.left},${height - padding.bottom} ${points} ${width - padding.right},${height - padding.bottom}`}
          fill="url(#costGradient)"
        />

        {/* Line */}
        <polyline
          points={points}
          fill="none"
          stroke="#ff6b6b"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Gradient definition */}
        <defs>
          <linearGradient id="costGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ff6b6b" stopOpacity={0.3} />
            <stop offset="100%" stopColor="#ff6b6b" stopOpacity={0} />
          </linearGradient>
        </defs>

        {/* X-axis labels (first, middle, last) */}
        {data.length > 0 && (
          <>
            <text
              x={padding.left}
              y={height - 10}
              className="fill-white/20"
              fontSize={9}
              fontFamily="monospace"
            >
              {data[0]?.day}
            </text>
            <text
              x={width - padding.right}
              y={height - 10}
              textAnchor="end"
              className="fill-white/20"
              fontSize={9}
              fontFamily="monospace"
            >
              {data[data.length - 1]?.day}
            </text>
          </>
        )}
      </svg>
    </div>
  );
}

// ── Tokens Chart ───────────────────────────────────────────────────────

function TokensChart({ data }: { data: DayStat[] }) {
  const { bars, maxTokens } = useMemo(() => {
    if (data.length === 0) return { bars: [], maxTokens: 0 };
    const max = Math.max(...data.map((d) => d.tokens), 1);
    return {
      bars: data.map((d) => ({
        ...d,
        height: (d.tokens / max) * 100,
      })),
      maxTokens: max,
    };
  }, [data]);

  if (data.length === 0) {
    return <EmptyChart label="Tokens Used" />;
  }

  return (
    <div className="rounded-lg border border-white/5 bg-white/[0.02] p-6">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.3em] text-info/70 mb-4">
        Tokens per Day
      </h3>
      <div className="flex items-end gap-1 h-32">
        {bars.map((bar, i) => (
          <div
            key={i}
            className="flex-1 min-w-[4px] group relative"
            title={`${bar.day}: ${bar.tokens.toLocaleString()} tokens`}
          >
            <div
              className="w-full bg-info/40 rounded-t-sm hover:bg-info/70 transition-colors"
              style={{ height: `${bar.height}%` }}
            />
          </div>
        ))}
      </div>
      <div className="flex justify-between mt-2">
        <span className="font-mono text-[9px] text-white/15">{data[0]?.day}</span>
        <span className="font-mono text-[9px] text-white/15">{data[data.length - 1]?.day}</span>
      </div>
    </div>
  );
}

// ── Rooms Per Day Chart ────────────────────────────────────────────────

function RoomsPerDayChart({ data }: { data: DayStat[] }) {
  const { bars } = useMemo(() => {
    if (data.length === 0) return { bars: [] };
    const max = Math.max(...data.map((d) => d.rooms), 1);
    return {
      bars: data.map((d) => ({
        ...d,
        height: (d.rooms / max) * 100,
      })),
    };
  }, [data]);

  if (data.length === 0) {
    return <EmptyChart label="Rooms per Day" />;
  }

  return (
    <div className="rounded-lg border border-white/5 bg-white/[0.02] p-6">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.3em] text-alive/70 mb-4">
        Rooms per Day
      </h3>
      <div className="flex items-end gap-1 h-32">
        {bars.map((bar, i) => (
          <div
            key={i}
            className="flex-1 min-w-[4px] group relative"
            title={`${bar.day}: ${bar.rooms} rooms`}
          >
            <div
              className="w-full bg-alive/40 rounded-t-sm hover:bg-alive/70 transition-colors"
              style={{ height: `${bar.height}%` }}
            />
          </div>
        ))}
      </div>
      <div className="flex justify-between mt-2">
        <span className="font-mono text-[9px] text-white/15">{data[0]?.day}</span>
        <span className="font-mono text-[9px] text-white/15">{data[data.length - 1]?.day}</span>
      </div>
    </div>
  );
}

// ── Top Tags Chart ─────────────────────────────────────────────────────

function TopTagsChart({ tags }: { tags: TagCount[] }) {
  if (tags.length === 0) {
    return <EmptyChart label="Top Tags" />;
  }

  const maxCount = Math.max(...tags.map((t) => t.count), 1);

  return (
    <div className="rounded-lg border border-white/5 bg-white/[0.02] p-6">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.3em] text-creative/70 mb-4">
        Top Tags
      </h3>
      <div className="space-y-2">
        {tags.slice(0, 15).map((tag) => (
          <div key={tag.tag} className="flex items-center gap-3">
            <span className="font-mono text-[10px] text-white/40 w-24 text-right truncate flex-shrink-0">
              {tag.tag}
            </span>
            <div className="flex-1 h-4 bg-white/[0.03] rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-creative/60 to-creative/30 rounded-full transition-all"
                style={{ width: `${(tag.count / maxCount) * 100}%` }}
              />
            </div>
            <span className="font-mono text-[10px] text-white/20 w-8 flex-shrink-0">
              {tag.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Empty State ────────────────────────────────────────────────────────

function EmptyChart({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-dashed border-white/10 bg-white/[0.01] p-8 text-center">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/20 mb-2">{label}</p>
      <p className="font-mono text-xs text-white/10">No data available yet</p>
    </div>
  );
}
