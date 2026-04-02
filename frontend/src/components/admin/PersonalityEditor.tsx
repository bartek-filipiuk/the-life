import { useState, useEffect } from 'react';
import { adminRequest } from '../../lib/admin-api';

interface PersonalityData {
  seed: string;
  tone_guidelines: string;
  banned_topics: string[];
  evolution_notes: string;
}

interface GuardrailsData {
  temperature_min: number;
  temperature_max: number;
  novelty_threshold: number;
  meta_reflection_every: number;
  wildcard_every: number;
}

export default function PersonalityEditor() {
  const [personality, setPersonality] = useState<PersonalityData>({
    seed: '', tone_guidelines: '', banned_topics: [], evolution_notes: '',
  });
  const [guardrails, setGuardrails] = useState<GuardrailsData>({
    temperature_min: 0.7, temperature_max: 1.0, novelty_threshold: 0.92,
    meta_reflection_every: 10, wildcard_every: 5,
  });
  const [msg, setMsg] = useState('');
  const [newBannedTopic, setNewBannedTopic] = useState('');

  useEffect(() => { load(); }, []);

  async function load() {
    try {
      const [p, g] = await Promise.all([
        adminRequest<PersonalityData>('/admin/personality'),
        adminRequest<GuardrailsData>('/admin/guardrails'),
      ]);
      if (p) setPersonality(p);
      if (g) setGuardrails(g);
    } catch { /* backend offline */ }
  }

  async function savePersonality() {
    try {
      await adminRequest('/admin/personality', { method: 'PUT', body: JSON.stringify(personality) });
      flash('Personality saved');
    } catch { flash('Save failed'); }
  }

  async function saveGuardrails() {
    try {
      await adminRequest('/admin/guardrails', { method: 'PUT', body: JSON.stringify(guardrails) });
      flash('Guardrails saved');
    } catch { flash('Save failed'); }
  }

  function addBannedTopic() {
    if (!newBannedTopic.trim()) return;
    setPersonality({
      ...personality,
      banned_topics: [...personality.banned_topics, newBannedTopic.trim()],
    });
    setNewBannedTopic('');
  }

  function removeBannedTopic(topic: string) {
    setPersonality({
      ...personality,
      banned_topics: personality.banned_topics.filter(t => t !== topic),
    });
  }

  function flash(m: string) { setMsg(m); setTimeout(() => setMsg(''), 3000); }

  return (
    <div className="space-y-8">
      {msg && <div className="font-mono text-xs text-alive bg-alive/5 border border-alive/20 p-2 rounded">{msg}</div>}

      {/* Personality Seed */}
      <div className="bg-white/[0.02] border border-white/5 rounded-lg p-6 space-y-4">
        <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-white/30">Identity Seed</h2>
        <textarea
          value={personality.seed}
          onChange={(e) => setPersonality({ ...personality, seed: e.target.value })}
          rows={4}
          className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg font-mono text-sm text-white placeholder-white/20 focus:border-creative/30 focus:outline-none resize-none"
          placeholder="Describe the AI's core identity..."
        />

        <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-white/30 pt-2">Writing Style</h2>
        <textarea
          value={personality.tone_guidelines}
          onChange={(e) => setPersonality({ ...personality, tone_guidelines: e.target.value })}
          rows={3}
          className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg font-mono text-sm text-white placeholder-white/20 focus:border-creative/30 focus:outline-none resize-none"
          placeholder="Style and tone guidelines..."
        />

        <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-white/30 pt-2">Banned Topics</h2>
        <div className="flex flex-wrap gap-2">
          {personality.banned_topics.map((topic) => (
            <span key={topic} className="font-mono text-xs px-3 py-1 rounded-full bg-cost/10 border border-cost/20 text-cost flex items-center gap-2">
              {topic}
              <button onClick={() => removeBannedTopic(topic)} className="text-cost/40 hover:text-cost">&times;</button>
            </span>
          ))}
          <div className="flex gap-1">
            <input
              value={newBannedTopic}
              onChange={(e) => setNewBannedTopic(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addBannedTopic()}
              placeholder="Add topic..."
              className="px-3 py-1 bg-white/5 border border-white/10 rounded-full font-mono text-xs text-white placeholder-white/20 focus:border-cost/30 focus:outline-none w-32"
            />
          </div>
        </div>

        {personality.evolution_notes && (
          <>
            <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-white/30 pt-2">Evolution Notes (AI-generated)</h2>
            <p className="font-mono text-xs text-white/40 bg-white/[0.02] border border-white/5 rounded-lg p-4">{personality.evolution_notes}</p>
          </>
        )}

        <button
          onClick={savePersonality}
          className="px-4 py-2 bg-creative/10 border border-creative/30 rounded-lg font-mono text-xs text-creative hover:bg-creative/20 transition-all uppercase tracking-wider"
        >
          Save Personality
        </button>
      </div>

      {/* Guardrails */}
      <div className="bg-white/[0.02] border border-white/5 rounded-lg p-6 space-y-4">
        <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-white/30">Creativity Guardrails</h2>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <SliderField label="Temp Min" value={guardrails.temperature_min} min={0} max={2} step={0.1}
            onChange={(v) => setGuardrails({ ...guardrails, temperature_min: v })} />
          <SliderField label="Temp Max" value={guardrails.temperature_max} min={0} max={2} step={0.1}
            onChange={(v) => setGuardrails({ ...guardrails, temperature_max: v })} />
          <SliderField label="Novelty Threshold" value={guardrails.novelty_threshold} min={0.5} max={1} step={0.01}
            onChange={(v) => setGuardrails({ ...guardrails, novelty_threshold: v })} />
          <NumberField label="Meta Reflect Every" value={guardrails.meta_reflection_every}
            onChange={(v) => setGuardrails({ ...guardrails, meta_reflection_every: v })} />
          <NumberField label="Wildcard Every" value={guardrails.wildcard_every}
            onChange={(v) => setGuardrails({ ...guardrails, wildcard_every: v })} />
        </div>

        <button
          onClick={saveGuardrails}
          className="px-4 py-2 bg-info/10 border border-info/30 rounded-lg font-mono text-xs text-info hover:bg-info/20 transition-all uppercase tracking-wider"
        >
          Save Guardrails
        </button>
      </div>
    </div>
  );
}

function SliderField({ label, value, min, max, step, onChange }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex justify-between mb-1">
        <label className="font-mono text-[10px] text-white/20">{label}</label>
        <span className="font-mono text-[10px] text-white/40">{value}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full accent-creative" />
    </div>
  );
}

function NumberField({ label, value, onChange }: {
  label: string; value: number; onChange: (v: number) => void;
}) {
  return (
    <div>
      <label className="font-mono text-[10px] text-white/20 block mb-1">{label}</label>
      <input type="number" value={value}
        onChange={(e) => onChange(parseInt(e.target.value) || 0)}
        className="w-full px-3 py-1.5 bg-white/5 border border-white/10 rounded font-mono text-xs text-white focus:border-info/30 focus:outline-none" />
    </div>
  );
}
