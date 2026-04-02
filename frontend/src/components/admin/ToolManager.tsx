import { useState, useEffect, useCallback, useRef } from 'react';
import { adminRequest, getToken } from '../../lib/admin-api';

interface ToolConfig {
  id: string;
  name: string;
  category: string;
  api_type: string;
  provider: string;
  model: string;
  enabled: boolean;
  daily_limit: number;
  cost_estimate: number;
  config: Record<string, string>;
  daily_usage?: number;
}

const CATEGORY_COLORS: Record<string, string> = {
  search: 'text-info border-info/20',
  image: 'text-creative border-creative/20',
  video: 'text-cost border-cost/20',
  music: 'text-alive border-alive/20',
  custom: 'text-white/60 border-white/20',
};

export default function ToolManager() {
  const [tools, setTools] = useState<ToolConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [newTool, setNewTool] = useState({
    id: '', name: '', category: 'custom', api_type: 'custom_http',
    provider: '', model: '', daily_limit: 10, cost_estimate: 0, endpoint_url: '',
  });

  const debounceTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const data = await adminRequest<ToolConfig[]>('/admin/tools');
      if (data) setTools(data);
    } catch { setError('Failed to load tools'); }
    finally { setLoading(false); }
  }

  async function toggle(id: string, enabled: boolean) {
    try {
      await adminRequest(`/admin/tools/${id}`, { method: 'PUT', body: JSON.stringify({ enabled }) });
      await load();
      flash(`${id} ${enabled ? 'enabled' : 'disabled'}`);
    } catch { setError('Failed to update tool'); }
  }

  function updateFieldDebounced(id: string, field: string, value: unknown) {
    // Update local state immediately for responsiveness
    setTools(prev => prev.map(t => t.id === id ? { ...t, [field]: value } : t));
    // Debounce API call
    const key = `${id}_${field}`;
    clearTimeout(debounceTimers.current[key]);
    debounceTimers.current[key] = setTimeout(async () => {
      try {
        await adminRequest(`/admin/tools/${id}`, { method: 'PUT', body: JSON.stringify({ [field]: value }) });
      } catch { setError('Update failed'); }
    }, 600);
  }

  async function addTool() {
    try {
      const body: Record<string, unknown> = { ...newTool };
      if (newTool.endpoint_url) {
        body.config = { endpoint_url: newTool.endpoint_url };
      }
      delete body.endpoint_url;
      await adminRequest('/admin/tools', { method: 'POST', body: JSON.stringify(body) });
      setShowAdd(false);
      setNewTool({ id: '', name: '', category: 'custom', api_type: 'custom_http', provider: '', model: '', daily_limit: 10, cost_estimate: 0, endpoint_url: '' });
      await load();
      flash('Tool added');
    } catch { setError('Failed to add tool'); }
  }

  async function removeTool(id: string) {
    if (!confirm(`Delete tool "${id}"?`)) return;
    try {
      await adminRequest(`/admin/tools/${id}`, { method: 'DELETE' });
      await load();
      flash(`${id} removed`);
    } catch { setError('Failed to remove tool'); }
  }

  function flash(m: string) {
    setMsg(m);
    setTimeout(() => setMsg(''), 3000);
  }

  if (loading) return <div className="font-mono text-sm text-white/30 py-8 text-center">Loading tools...</div>;

  return (
    <div className="space-y-4">
      {msg && <div className="font-mono text-xs text-alive bg-alive/5 border border-alive/20 p-2 rounded">{msg}</div>}
      {error && <div className="font-mono text-xs text-cost bg-cost/5 border border-cost/20 p-2 rounded">{error}</div>}

      {/* Tool cards */}
      <div className="space-y-3">
        {tools.map((tool) => (
          <div key={tool.id} className={`border rounded-lg p-4 bg-white/[0.02] ${tool.enabled ? 'border-white/10' : 'border-white/5 opacity-50'}`}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => toggle(tool.id, !tool.enabled)}
                  className={`w-10 h-5 rounded-full transition-all relative ${tool.enabled ? 'bg-alive/30' : 'bg-white/10'}`}
                >
                  <div className={`w-4 h-4 rounded-full absolute top-0.5 transition-all ${tool.enabled ? 'left-5 bg-alive' : 'left-0.5 bg-white/30'}`} />
                </button>
                <div>
                  <span className="font-mono text-sm font-medium text-white">{tool.name}</span>
                  <span className={`ml-2 font-mono text-[10px] px-2 py-0.5 rounded-full border ${CATEGORY_COLORS[tool.category] ?? CATEGORY_COLORS.custom}`}>
                    {tool.category}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-4 font-mono text-[10px] text-white/30">
                <span>Usage: {tool.daily_usage ?? 0}/{tool.daily_limit || '∞'}</span>
                <span>~${tool.cost_estimate}/call</span>
                {tool.category === 'custom' && (
                  <button onClick={() => removeTool(tool.id)} className="text-cost/40 hover:text-cost">del</button>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <label className="font-mono text-[10px] text-white/20 block mb-1">Provider</label>
                <input
                  value={tool.provider}
                  onChange={(e) => updateFieldDebounced(tool.id, 'provider', e.target.value)}
                  className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded font-mono text-xs text-white focus:border-alive/30 focus:outline-none"
                />
              </div>
              <div>
                <label className="font-mono text-[10px] text-white/20 block mb-1">Model</label>
                <input
                  value={tool.model}
                  onChange={(e) => updateFieldDebounced(tool.id, 'model', e.target.value)}
                  className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded font-mono text-xs text-white focus:border-alive/30 focus:outline-none"
                />
              </div>
              <div>
                <label className="font-mono text-[10px] text-white/20 block mb-1">Daily Limit</label>
                <input
                  type="number"
                  value={tool.daily_limit}
                  onChange={(e) => updateFieldDebounced(tool.id, 'daily_limit', parseInt(e.target.value) || 0)}
                  className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded font-mono text-xs text-white focus:border-alive/30 focus:outline-none"
                />
              </div>
              <div>
                <label className="font-mono text-[10px] text-white/20 block mb-1">API Type</label>
                <select
                  value={tool.api_type}
                  onChange={(e) => updateFieldDebounced(tool.id, 'api_type', e.target.value)}
                  className="w-full px-2 py-1.5 bg-white/5 border border-white/10 rounded font-mono text-xs text-white focus:border-alive/30 focus:outline-none"
                >
                  <option value="builtin">Built-in</option>
                  <option value="replicate">Replicate</option>
                  <option value="openrouter">OpenRouter</option>
                  <option value="custom_http">Custom HTTP</option>
                </select>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Add Tool */}
      {!showAdd ? (
        <button
          onClick={() => setShowAdd(true)}
          className="w-full py-3 border border-dashed border-white/10 rounded-lg font-mono text-xs text-white/30 hover:text-white hover:border-white/20 transition-all"
        >
          + Add Custom Tool
        </button>
      ) : (
        <div className="border border-alive/20 rounded-lg p-4 bg-alive/5 space-y-3">
          <div className="font-mono text-xs text-alive uppercase tracking-wider">New Custom Tool</div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <input placeholder="ID (slug)" value={newTool.id} onChange={(e) => setNewTool({ ...newTool, id: e.target.value })}
              className="px-2 py-1.5 bg-white/5 border border-white/10 rounded font-mono text-xs text-white focus:border-alive/30 focus:outline-none" />
            <input placeholder="Name" value={newTool.name} onChange={(e) => setNewTool({ ...newTool, name: e.target.value })}
              className="px-2 py-1.5 bg-white/5 border border-white/10 rounded font-mono text-xs text-white focus:border-alive/30 focus:outline-none" />
            <select value={newTool.category} onChange={(e) => setNewTool({ ...newTool, category: e.target.value })}
              className="px-2 py-1.5 bg-white/5 border border-white/10 rounded font-mono text-xs text-white focus:border-alive/30 focus:outline-none">
              <option value="custom">Custom</option><option value="search">Search</option>
              <option value="image">Image</option><option value="video">Video</option><option value="music">Music</option>
            </select>
            <input placeholder="Endpoint URL" value={newTool.endpoint_url} onChange={(e) => setNewTool({ ...newTool, endpoint_url: e.target.value })}
              className="px-2 py-1.5 bg-white/5 border border-white/10 rounded font-mono text-xs text-white focus:border-alive/30 focus:outline-none col-span-2" />
            <input type="number" placeholder="Daily limit" value={newTool.daily_limit} onChange={(e) => setNewTool({ ...newTool, daily_limit: parseInt(e.target.value) || 0 })}
              className="px-2 py-1.5 bg-white/5 border border-white/10 rounded font-mono text-xs text-white focus:border-alive/30 focus:outline-none" />
          </div>
          <div className="flex gap-2">
            <button onClick={addTool} className="px-4 py-1.5 bg-alive/10 border border-alive/30 rounded font-mono text-xs text-alive hover:bg-alive/20 transition-all">Add</button>
            <button onClick={() => setShowAdd(false)} className="px-4 py-1.5 border border-white/10 rounded font-mono text-xs text-white/40 hover:text-white transition-all">Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}
