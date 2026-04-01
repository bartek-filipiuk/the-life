import { useEffect, useState } from 'react';
import type { Room } from '../lib/api';
import { assetUrl, contentTypeColor, contentTypeHex, formatCost, formatDuration, formatNumber } from '../lib/api';

/**
 * Full room detail page, rendered as a React island.
 * Fetches room data client-side based on URL path.
 */
export default function RoomDetail() {
  const [room, setRoom] = useState<Room | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connectedRooms, setConnectedRooms] = useState<
    Array<{ id: string; title: string; content_type: string; cycle_number: number }>
  >([]);
  const [showPrompts, setShowPrompts] = useState(false);

  const apiUrl =
    (import.meta as unknown as { env?: Record<string, string> }).env?.PUBLIC_API_URL ??
    'http://localhost:8000';

  useEffect(() => {
    // Extract room ID from URL: /room/[id]
    const pathParts = window.location.pathname.split('/');
    const roomId = pathParts[pathParts.length - 1] || pathParts[pathParts.length - 2];

    if (!roomId) {
      setError('No room ID specified');
      setLoading(false);
      return;
    }

    fetch(`${apiUrl}/rooms/${encodeURIComponent(roomId)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Room not found (${res.status})`);
        return res.json() as Promise<Room>;
      })
      .then((data) => {
        setRoom(data);
        setLoading(false);

        // Fetch connected rooms
        const promises = data.connections.slice(0, 10).map((connId) =>
          fetch(`${apiUrl}/rooms/${encodeURIComponent(connId)}`)
            .then((r) => (r.ok ? (r.json() as Promise<Room>) : null))
            .catch(() => null),
        );

        Promise.all(promises).then((results) => {
          const connected = results
            .filter((r): r is Room => r !== null)
            .map((r) => ({
              id: r.id,
              title: r.title,
              content_type: r.content_type,
              cycle_number: r.cycle_number,
            }));
          setConnectedRooms(connected);
        });
      })
      .catch((err: unknown) => {
        console.error('[RoomDetail] Failed to fetch room:', err);
        setError(err instanceof Error ? err.message : 'Failed to load room');
        setLoading(false);
      });
  }, [apiUrl]);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-20 text-center">
        <div className="w-8 h-8 border-2 border-[#00ff88]/30 border-t-[#00ff88] rounded-full animate-spin mx-auto" />
        <p className="font-mono text-sm text-white/40 mt-4">Loading room...</p>
      </div>
    );
  }

  if (error || !room) {
    return (
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-20 text-center space-y-4">
        <div className="w-16 h-16 rounded-full border border-white/10 flex items-center justify-center mx-auto">
          <svg className="w-8 h-8 text-white/20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
        </div>
        <p className="font-mono text-sm text-white/40">{error ?? 'Room not found'}</p>
        <a
          href="/"
          className="inline-block font-mono text-xs text-[#00ff88]/60 hover:text-[#00ff88] transition-colors uppercase tracking-wider"
        >
          Back to Home
        </a>
      </div>
    );
  }

  const imageUrl = assetUrl(room.image_url);
  const musicUrl = assetUrl(room.music_url);
  const typeColor = contentTypeHex(room.content_type);

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm mb-8">
        <a href="/" className="font-mono text-white/30 hover:text-white transition-colors text-xs uppercase tracking-wider">
          Home
        </a>
        <span className="text-white/10">/</span>
        <span className="font-mono text-white/50 text-xs uppercase tracking-wider">
          Room #{room.cycle_number}
        </span>
      </nav>

      <article className="space-y-8">
        {/* Header */}
        <header className="space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <span
              className="font-mono text-[10px] uppercase tracking-[0.2em] px-3 py-1 rounded-full border"
              style={{ color: typeColor, borderColor: `${typeColor}33` }}
            >
              {room.content_type}
            </span>
            <span className="font-mono text-sm text-white/30">Cycle #{room.cycle_number}</span>
            {room.mood && (
              <span className="font-mono text-sm text-white/20 italic">{room.mood}</span>
            )}
            <span className="font-mono text-xs text-white/15">
              {new Date(room.created_at).toLocaleString()}
            </span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold text-white leading-tight">{room.title}</h1>
          {room.tags.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {room.tags.map((tag) => (
                <span key={tag} className="font-mono text-[10px] text-white/30 px-2.5 py-1 rounded-full bg-white/5 border border-white/5">
                  {tag}
                </span>
              ))}
            </div>
          )}
        </header>

        {/* Image */}
        {imageUrl && (
          <figure className="space-y-3">
            <div className="relative rounded-lg overflow-hidden border border-white/5">
              <img src={imageUrl} alt={room.image_prompt ?? room.title} className="w-full object-cover" loading="lazy" />
            </div>
            {room.image_prompt && (
              <figcaption className="font-mono text-[10px] text-white/20 text-center italic">
                Prompt: {room.image_prompt}
              </figcaption>
            )}
          </figure>
        )}

        {/* Content */}
        <div className={
          room.content_type === 'poem' || room.content_type === 'haiku'
            ? 'text-center text-lg leading-loose font-light italic'
            : 'text-base leading-relaxed'
        }>
          {room.content.split('\n').map((paragraph, i) =>
            paragraph.trim() ? (
              <p key={i} className="text-white/70 mb-4">{paragraph}</p>
            ) : (
              <br key={i} />
            ),
          )}
        </div>

        {/* Audio Player */}
        {musicUrl && (
          <div className="space-y-3">
            <h3 className="font-mono text-[10px] uppercase tracking-[0.3em] text-[#00ff88]/70">
              Generated Music
            </h3>
            <div className="rounded-lg border border-white/5 bg-white/[0.02] p-4">
              <audio controls className="w-full" preload="metadata" style={{ filter: 'invert(1) hue-rotate(180deg)', opacity: 0.7 }}>
                <source src={musicUrl} type="audio/mpeg" />
              </audio>
              {room.music_prompt && (
                <p className="font-mono text-[10px] text-white/20 mt-2 italic">Prompt: {room.music_prompt}</p>
              )}
            </div>
          </div>
        )}

        {/* Connected Rooms */}
        {connectedRooms.length > 0 && (
          <section className="space-y-4">
            <h3 className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">
              Connected Rooms ({connectedRooms.length})
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {connectedRooms.map((conn) => (
                <a
                  key={conn.id}
                  href={`/room/${conn.id}`}
                  className="group flex items-center gap-3 p-3 rounded-lg border border-white/5 bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/10 transition-all"
                >
                  <div
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: contentTypeHex(conn.content_type) }}
                  />
                  <div className="min-w-0">
                    <p className="text-sm text-white/60 group-hover:text-white transition-colors truncate">
                      {conn.title}
                    </p>
                    <p className="font-mono text-[10px] text-white/20">
                      #{conn.cycle_number} - {conn.content_type}
                    </p>
                  </div>
                </a>
              ))}
            </div>
          </section>
        )}

        {/* Behind the Scenes */}
        <section className="space-y-4">
          <h3 className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/40">
            Full Transparency
          </h3>
          <div className="rounded-lg border border-white/5 bg-white/[0.02] overflow-hidden">
            <div className="px-6 py-4 border-b border-white/5 bg-white/[0.02]">
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-[#00ff88]" />
                <span className="font-mono text-xs uppercase tracking-[0.3em] text-white/50">
                  Behind the Scenes
                </span>
              </div>
            </div>
            <div className="p-6 space-y-5">
              {/* Intention */}
              <div className="space-y-2">
                <h4 className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#00ff88]/70">Intention</h4>
                <p className="text-sm text-white/50 leading-relaxed">{room.intention}</p>
              </div>
              {/* Reasoning */}
              {room.reasoning && (
                <div className="space-y-2">
                  <h4 className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#6b9fff]/70">Reasoning</h4>
                  <p className="text-sm text-white/50 leading-relaxed">{room.reasoning}</p>
                </div>
              )}
              {/* Searches */}
              {room.search_queries.length > 0 && (
                <div className="space-y-2">
                  <h4 className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#c084fc]/70">
                    Searches ({room.search_queries.length})
                  </h4>
                  {room.search_queries.map((q, i) => (
                    <p key={i} className="text-xs text-white/40 font-mono">&gt; {q}</p>
                  ))}
                </div>
              )}
              {/* Cost breakdown */}
              <div className="space-y-2">
                <h4 className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#ff6b6b]/70">Cost</h4>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: 'LLM', value: room.llm_cost },
                    { label: 'Image', value: room.image_cost },
                    { label: 'Music', value: room.music_cost },
                    { label: 'Search', value: room.search_cost },
                  ].map((item) => (
                    <div key={item.label} className="p-2 rounded bg-white/[0.02] text-center">
                      <p className="font-mono text-[10px] text-white/30">{item.label}</p>
                      <p className="font-mono text-xs text-[#ff6b6b]">{formatCost(item.value)}</p>
                    </div>
                  ))}
                </div>
                <div className="flex items-center justify-between p-2 rounded bg-[#ff6b6b]/5 border border-[#ff6b6b]/10">
                  <span className="font-mono text-xs text-white/40">Total</span>
                  <span className="font-mono text-sm font-bold text-[#ff6b6b]">{formatCost(room.total_cost)}</span>
                </div>
              </div>
              {/* Metrics */}
              <div className="grid grid-cols-3 gap-2">
                <div className="p-2 rounded bg-white/[0.02] text-center">
                  <p className="font-mono text-[10px] text-white/30">Tokens</p>
                  <p className="font-mono text-xs text-[#6b9fff]">{formatNumber(room.llm_tokens)}</p>
                </div>
                <div className="p-2 rounded bg-white/[0.02] text-center">
                  <p className="font-mono text-[10px] text-white/30">Duration</p>
                  <p className="font-mono text-xs text-white/60">{formatDuration(room.duration_ms)}</p>
                </div>
                <div className="p-2 rounded bg-white/[0.02] text-center">
                  <p className="font-mono text-[10px] text-white/30">Model</p>
                  <p className="font-mono text-[9px] text-[#c084fc] truncate">{room.model.split('/').pop()}</p>
                </div>
              </div>
              {/* Image & Music Prompts */}
              {room.image_prompt && (
                <div className="space-y-2">
                  <h4 className="font-mono text-[10px] text-[#c084fc]/50">Image Prompt</h4>
                  <p className="text-xs text-white/30 font-mono bg-white/[0.02] p-3 rounded">{room.image_prompt}</p>
                </div>
              )}
              {room.music_prompt && (
                <div className="space-y-2">
                  <h4 className="font-mono text-[10px] text-[#00ff88]/50">Music Prompt</h4>
                  <p className="text-xs text-white/30 font-mono bg-white/[0.02] p-3 rounded">{room.music_prompt}</p>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Raw Prompts */}
        <section>
          <button
            onClick={() => setShowPrompts(!showPrompts)}
            className="font-mono text-[10px] uppercase tracking-[0.3em] text-white/30 hover:text-white/50 transition-colors flex items-center gap-2"
          >
            <svg
              className={`w-3 h-3 transition-transform ${showPrompts ? 'rotate-90' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            Raw Prompts
          </button>
          {showPrompts && (
            <div className="mt-4 space-y-4">
              {room.decision_prompt && (
                <div className="space-y-2">
                  <h4 className="font-mono text-[10px] text-[#c084fc]/50">Decision Prompt</h4>
                  <pre className="text-xs text-white/30 font-mono bg-white/[0.02] p-4 rounded-lg overflow-x-auto whitespace-pre-wrap border border-white/5">
                    {room.decision_prompt}
                  </pre>
                </div>
              )}
              {room.creation_prompt && (
                <div className="space-y-2">
                  <h4 className="font-mono text-[10px] text-[#00ff88]/50">Creation Prompt</h4>
                  <pre className="text-xs text-white/30 font-mono bg-white/[0.02] p-4 rounded-lg overflow-x-auto whitespace-pre-wrap border border-white/5">
                    {room.creation_prompt}
                  </pre>
                </div>
              )}
            </div>
          )}
        </section>

        {/* Next Direction Hint */}
        {room.next_hint && (
          <div className="p-4 rounded-lg border border-[#00ff88]/10 bg-[#00ff88]/5">
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#00ff88]/50 mb-2">
              Next Direction Hint
            </p>
            <p className="text-sm text-[#00ff88]/70 italic">{room.next_hint}</p>
          </div>
        )}

        {/* Navigation */}
        <div className="flex items-center justify-between pt-8 border-t border-white/5">
          <a
            href="/"
            className="font-mono text-xs text-white/30 hover:text-white transition-colors uppercase tracking-wider"
          >
            &larr; Back to Map
          </a>
          <a
            href="/timeline"
            className="font-mono text-xs text-white/30 hover:text-white transition-colors uppercase tracking-wider"
          >
            Timeline &rarr;
          </a>
        </div>
      </article>
    </div>
  );
}
