import { useState, useEffect, useCallback } from 'react';
import type { Room } from '../lib/api';
import { assetUrl, contentTypeColor, formatCost, formatDuration, formatNumber } from '../lib/api';
import Graph from './Graph';

/**
 * Client-side panel that wraps Graph + selected room details.
 * When a user clicks a node in the graph, it fetches that room's data
 * and renders the card + behind-the-scenes panels.
 */
export default function RoomPanel() {
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const [loading, setLoading] = useState(false);

  const apiUrl =
    (import.meta as unknown as { env?: Record<string, string> }).env?.PUBLIC_API_URL ??
    'http://localhost:8765';

  const handleSelectRoom = useCallback(
    (roomId: string) => {
      setLoading(true);
      fetch(`${apiUrl}/rooms/${encodeURIComponent(roomId)}`)
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json() as Promise<Room>;
        })
        .then((data) => {
          setSelectedRoom(data);
          setLoading(false);
        })
        .catch((err: unknown) => {
          console.error('[RoomPanel] Failed to fetch room:', err);
          setLoading(false);
        });
    },
    [apiUrl],
  );

  const imageUrl = selectedRoom ? assetUrl(selectedRoom.image_url) : null;
  const excerpt = selectedRoom
    ? selectedRoom.content.length > 300
      ? selectedRoom.content.slice(0, 300) + '...'
      : selectedRoom.content
    : '';

  return (
    <div className="space-y-8">
      {/* Graph */}
      <Graph onSelectRoom={handleSelectRoom} />

      {/* Selected room + behind the scenes */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Room Card */}
        <div>
          <p className="font-mono text-[10px] text-white/30 uppercase tracking-[0.3em] mb-3">
            Selected Room
          </p>
          {loading ? (
            <div className="rounded-lg border border-white/5 bg-white/[0.02] p-8 flex items-center justify-center">
              <div className="w-6 h-6 border-2 border-alive/30 border-t-alive rounded-full animate-spin" />
            </div>
          ) : selectedRoom ? (
            <RoomCardReact room={selectedRoom} imageUrl={imageUrl} excerpt={excerpt} />
          ) : (
            <div className="rounded-lg border border-dashed border-white/10 bg-white/[0.01] p-8 text-center">
              <div className="space-y-3">
                <div className="w-12 h-12 rounded-full border border-white/10 flex items-center justify-center mx-auto">
                  <svg className="w-5 h-5 text-white/20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
                  </svg>
                </div>
                <p className="font-mono text-sm text-white/30">Click a node to explore</p>
                <p className="font-mono text-xs text-white/15">Select a room from the graph above</p>
              </div>
            </div>
          )}
        </div>

        {/* Behind the Scenes */}
        <div>
          <p className="font-mono text-[10px] text-white/30 uppercase tracking-[0.3em] mb-3">
            Behind the Scenes
          </p>
          {loading ? (
            <div className="rounded-lg border border-white/5 bg-white/[0.02] p-8 flex items-center justify-center">
              <div className="w-6 h-6 border-2 border-alive/30 border-t-alive rounded-full animate-spin" />
            </div>
          ) : selectedRoom ? (
            <BehindScenesReact room={selectedRoom} />
          ) : (
            <div className="rounded-lg border border-dashed border-white/10 bg-white/[0.01] p-8 text-center">
              <p className="font-mono text-sm text-white/20">
                Select a room to see behind the scenes
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Inline React versions of RoomCard and BehindScenes ─────────── */

function RoomCardReact({
  room,
  imageUrl,
  excerpt,
}: {
  room: Room;
  imageUrl: string | null;
  excerpt: string;
}) {
  return (
    <a
      href={`/room/${room.id}`}
      className="block group rounded-lg border border-white/5 bg-white/[0.02] hover:bg-white/[0.04] transition-all duration-300 hover:border-white/10 p-6 space-y-4"
    >
      {imageUrl && (
        <div className="relative aspect-video rounded-md overflow-hidden bg-white/5">
          <img
            src={imageUrl}
            alt={room.title}
            className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity duration-300"
            loading="lazy"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#0a0a0f]/60 to-transparent" />
        </div>
      )}
      <div className="space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={`font-mono text-[10px] uppercase tracking-[0.2em] px-2 py-0.5 rounded-full border border-current/20 ${contentTypeColor(room.content_type)}`}
          >
            {room.content_type}
          </span>
          <span className="font-mono text-[10px] text-white/30">#{room.cycle_number}</span>
          {room.mood && (
            <span className="font-mono text-[10px] text-white/20">{room.mood}</span>
          )}
        </div>
        <h3 className="text-lg font-semibold text-white group-hover:text-[#00ff88] transition-colors">
          {room.title}
        </h3>
        <p className="text-sm text-white/40 leading-relaxed whitespace-pre-line">{excerpt}</p>
      </div>
      {room.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {room.tags.slice(0, 6).map((tag) => (
            <span key={tag} className="font-mono text-[10px] text-white/25 px-2 py-0.5 rounded bg-white/5">
              {tag}
            </span>
          ))}
          {room.tags.length > 6 && (
            <span className="font-mono text-[10px] text-white/20">+{room.tags.length - 6}</span>
          )}
        </div>
      )}
      <div className="flex items-center gap-4 pt-2 border-t border-white/5 text-white/20">
        <span className="font-mono text-[10px]">
          Cost: <span className="text-[#ff6b6b]">{formatCost(room.total_cost)}</span>
        </span>
        <span className="font-mono text-[10px]">{room.connections.length} connections</span>
        {room.image_url && <span className="font-mono text-[10px] text-[#c084fc]">IMG</span>}
        {room.music_url && <span className="font-mono text-[10px] text-[#00ff88]">AUD</span>}
      </div>
    </a>
  );
}

function BehindScenesReact({ room }: { room: Room }) {
  return (
    <div className="rounded-lg border border-white/5 bg-white/[0.02] overflow-hidden">
      <div className="px-6 py-4 border-b border-white/5 bg-white/[0.02]">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-[#00ff88]" />
          <h3 className="font-mono text-xs uppercase tracking-[0.3em] text-white/50">
            Behind the Scenes
          </h3>
        </div>
      </div>
      <div className="p-6 space-y-5 max-h-[600px] overflow-y-auto">
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
            <div className="space-y-1">
              {room.search_queries.map((q, i) => (
                <p key={i} className="text-xs text-white/40 font-mono">
                  &gt; {q}
                </p>
              ))}
            </div>
          </div>
        )}
        {/* Cost grid */}
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
        {/* Metrics row */}
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
        {/* Connections */}
        {room.connections.length > 0 && (
          <div className="space-y-2">
            <h4 className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/30">
              Connections ({room.connections.length})
            </h4>
            <div className="flex flex-wrap gap-1.5">
              {room.connections.map((cid) => (
                <a
                  key={cid}
                  href={`/room/${cid}`}
                  className="font-mono text-[10px] text-[#6b9fff]/50 hover:text-[#6b9fff] px-2 py-1 rounded bg-[#6b9fff]/5 hover:bg-[#6b9fff]/10 transition-colors"
                >
                  {cid.slice(0, 8)}...
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
