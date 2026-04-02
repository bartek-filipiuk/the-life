import { useState, useEffect } from 'react';
import { adminRequest } from '../../lib/admin-api';

interface DashboardData {
  rooms: { total: number; published: number; featured: number; drafts: number };
  costs: { total: number; today: number; budget_daily: number; budget_monthly: number; budget_used_pct: number };
  tokens: { total: number };
  comments: { total: number; pending: number };
  cost_per_day: Array<{ day: string; cost: number; tokens: number; rooms: number }>;
  tool_usage: Array<{ id: string; name: string; enabled: boolean; daily_usage: number; daily_limit: number }>;
  scheduler_running: boolean;
  model: string;
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, []);

  async function load() {
    try {
      const result = await adminRequest<DashboardData>('/admin/dashboard');
      if (result) setData(result);
    } catch { /* backend offline */ }
    finally { setLoading(false); }
  }

  if (loading || !data) return <div className="font-mono text-sm text-white/30 py-8 text-center">Loading dashboard...</div>;

  const maxCost = Math.max(...data.cost_per_day.map(d => d.cost), 0.01);
  const maxRooms = Math.max(...data.cost_per_day.map(d => d.rooms), 1);

  return (
    <div className="space-y-6">
      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Rooms" value={data.rooms.total.toString()} sub={`${data.rooms.published} pub / ${data.rooms.featured} feat / ${data.rooms.drafts} draft`} color="text-info" />
        <StatCard label="Total Cost" value={`$${data.costs.total.toFixed(2)}`} sub={`$${data.costs.today.toFixed(2)} today`} color="text-cost" />
        <StatCard label="Budget Used" value={`${data.costs.budget_used_pct}%`} sub={`$${data.costs.budget_daily}/day limit`} color={data.costs.budget_used_pct > 80 ? 'text-cost' : 'text-alive'} />
        <StatCard label="Comments" value={data.comments.total.toString()} sub={`${data.comments.pending} pending`} color="text-creative" />
      </div>

      {/* Budget progress */}
      <div className="bg-white/[0.02] border border-white/5 rounded-lg p-4">
        <div className="font-mono text-[10px] text-white/20 uppercase tracking-wider mb-2">Daily Budget</div>
        <div className="w-full h-3 bg-white/5 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${data.costs.budget_used_pct > 80 ? 'bg-cost' : 'bg-alive'}`}
            style={{ width: `${Math.min(100, data.costs.budget_used_pct)}%` }}
          />
        </div>
        <div className="flex justify-between mt-1 font-mono text-[10px] text-white/20">
          <span>${data.costs.today.toFixed(4)} used</span>
          <span>${data.costs.budget_daily.toFixed(2)} limit</span>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Cost per day */}
        <div className="bg-white/[0.02] border border-white/5 rounded-lg p-4">
          <div className="font-mono text-[10px] text-white/20 uppercase tracking-wider mb-3">Cost / Day</div>
          <div className="flex items-end gap-1 h-32">
            {data.cost_per_day.slice(-14).map((d, i) => (
              <div key={i} className="flex-1 flex flex-col items-center">
                <div
                  className="w-full bg-cost/40 rounded-t hover:bg-cost/60 transition-all"
                  style={{ height: `${(d.cost / maxCost) * 100}%`, minHeight: '2px' }}
                  title={`${d.day}: $${d.cost.toFixed(4)}`}
                />
                <span className="font-mono text-[8px] text-white/10 mt-1">{d.day.slice(-2)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Rooms per day */}
        <div className="bg-white/[0.02] border border-white/5 rounded-lg p-4">
          <div className="font-mono text-[10px] text-white/20 uppercase tracking-wider mb-3">Rooms / Day</div>
          <div className="flex items-end gap-1 h-32">
            {data.cost_per_day.slice(-14).map((d, i) => (
              <div key={i} className="flex-1 flex flex-col items-center">
                <div
                  className="w-full bg-info/40 rounded-t hover:bg-info/60 transition-all"
                  style={{ height: `${(d.rooms / maxRooms) * 100}%`, minHeight: '2px' }}
                  title={`${d.day}: ${d.rooms} rooms`}
                />
                <span className="font-mono text-[8px] text-white/10 mt-1">{d.day.slice(-2)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Tool usage */}
      <div className="bg-white/[0.02] border border-white/5 rounded-lg p-4">
        <div className="font-mono text-[10px] text-white/20 uppercase tracking-wider mb-3">Tool Usage (Today)</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {data.tool_usage.map((t) => (
            <div key={t.id} className={`p-3 border rounded-lg ${t.enabled ? 'border-white/10' : 'border-white/5 opacity-50'}`}>
              <div className="font-mono text-xs text-white/60">{t.name}</div>
              <div className="font-mono text-lg text-white mt-1">
                {t.daily_usage}<span className="text-white/20 text-xs">/{t.daily_limit || '∞'}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* System info */}
      <div className="flex items-center gap-4 font-mono text-[10px] text-white/20">
        <span>Model: <span className="text-white/40">{data.model}</span></span>
        <span>Scheduler: <span className={data.scheduler_running ? 'text-alive' : 'text-cost'}>{data.scheduler_running ? 'RUNNING' : 'PAUSED'}</span></span>
        <span>Tokens: <span className="text-white/40">{data.tokens.total.toLocaleString()}</span></span>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  return (
    <div className="bg-white/[0.02] border border-white/5 rounded-lg p-4">
      <div className="font-mono text-[10px] text-white/20 uppercase tracking-wider">{label}</div>
      <div className={`font-mono text-2xl font-bold mt-1 ${color}`}>{value}</div>
      <div className="font-mono text-[10px] text-white/20 mt-1">{sub}</div>
    </div>
  );
}
