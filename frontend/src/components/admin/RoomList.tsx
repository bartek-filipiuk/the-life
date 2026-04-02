import { useState, useEffect } from 'react';
import type { AdminRoom } from '../../lib/admin-api';
import {
  listRooms,
  updateRoomStatus,
  deleteRoom,
  getToken,
} from '../../lib/admin-api';

const STATUS_COLORS: Record<string, string> = {
  published: 'text-alive bg-alive/10 border-alive/20',
  featured: 'text-creative bg-creative/10 border-creative/20',
  draft: 'text-white/40 bg-white/5 border-white/10',
};

const TYPE_COLORS: Record<string, string> = {
  poem: 'text-creative',
  essay: 'text-info',
  haiku: 'text-alive',
  reflection: 'text-cost',
  story: 'text-white',
};

export default function RoomList() {
  const [rooms, setRooms] = useState<AdminRoom[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionMsg, setActionMsg] = useState('');

  const perPage = 20;

  useEffect(() => {
    if (!getToken()) {
      window.location.href = '/admin/login';
      return;
    }
    load();
  }, [page, statusFilter]);

  async function load() {
    setLoading(true);
    setError('');
    try {
      const data = await listRooms(page, perPage, statusFilter);
      setRooms(data.rooms);
      setTotal(data.total);
    } catch (e: any) {
      setError(e.message || 'Failed to load rooms');
    } finally {
      setLoading(false);
    }
  }

  async function handleStatusChange(id: string, newStatus: string) {
    try {
      await updateRoomStatus(id, newStatus);
      setActionMsg(`Room ${id.slice(0, 8)}... set to ${newStatus}`);
      await load();
      setTimeout(() => setActionMsg(''), 3000);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Permanently delete this room?')) return;
    try {
      await deleteRoom(id);
      setActionMsg(`Room ${id.slice(0, 8)}... deleted`);
      await load();
      setTimeout(() => setActionMsg(''), 3000);
    } catch (e: any) {
      setError(e.message);
    }
  }

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-2">
        {[undefined, 'published', 'featured', 'draft'].map((s) => (
          <button
            key={s ?? 'all'}
            onClick={() => { setStatusFilter(s); setPage(1); }}
            className={`font-mono text-[10px] px-3 py-1.5 rounded-full border transition-all uppercase tracking-wider ${
              statusFilter === s
                ? 'text-alive bg-alive/10 border-alive/20'
                : 'text-white/30 bg-transparent border-white/10 hover:text-white hover:bg-white/5'
            }`}
          >
            {s ?? 'All'}
          </button>
        ))}
        <span className="ml-auto font-mono text-[10px] text-white/20">
          {total} room{total !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Status messages */}
      {actionMsg && (
        <div className="font-mono text-xs text-alive bg-alive/5 border border-alive/20 p-2 rounded">
          {actionMsg}
        </div>
      )}
      {error && (
        <div className="font-mono text-xs text-cost bg-cost/5 border border-cost/20 p-2 rounded">
          {error}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="font-mono text-sm text-white/30 py-8 text-center">Loading...</div>
      ) : rooms.length === 0 ? (
        <div className="font-mono text-sm text-white/30 py-8 text-center">No rooms found</div>
      ) : (
        <div className="border border-white/5 rounded-lg overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/5 bg-white/[0.02]">
                <th className="px-4 py-3 text-left font-mono text-[10px] text-white/30 uppercase tracking-wider">#</th>
                <th className="px-4 py-3 text-left font-mono text-[10px] text-white/30 uppercase tracking-wider">Title</th>
                <th className="px-4 py-3 text-left font-mono text-[10px] text-white/30 uppercase tracking-wider">Type</th>
                <th className="px-4 py-3 text-left font-mono text-[10px] text-white/30 uppercase tracking-wider">Status</th>
                <th className="px-4 py-3 text-left font-mono text-[10px] text-white/30 uppercase tracking-wider">Cost</th>
                <th className="px-4 py-3 text-right font-mono text-[10px] text-white/30 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rooms.map((room) => (
                <tr key={room.id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-white/30">{room.cycle_number}</td>
                  <td className="px-4 py-3">
                    <a
                      href={`/room/${room.id}`}
                      target="_blank"
                      className="font-mono text-sm text-white hover:text-alive transition-colors"
                    >
                      {room.title}
                    </a>
                    <div className="font-mono text-[10px] text-white/20 mt-0.5">
                      {room.id.slice(0, 8)}... &middot; {room.mood}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`font-mono text-xs ${TYPE_COLORS[room.content_type] ?? 'text-white/50'}`}>
                      {room.content_type}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`font-mono text-[10px] px-2 py-1 rounded-full border ${STATUS_COLORS[room.status] ?? STATUS_COLORS.draft}`}>
                      {room.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-cost">
                    ${room.total_cost.toFixed(4)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      {room.status !== 'featured' && (
                        <button
                          onClick={() => handleStatusChange(room.id, 'featured')}
                          className="font-mono text-[10px] px-2 py-1 text-creative/60 hover:text-creative hover:bg-creative/10 rounded transition-all"
                          title="Feature"
                        >
                          star
                        </button>
                      )}
                      {room.status !== 'published' && (
                        <button
                          onClick={() => handleStatusChange(room.id, 'published')}
                          className="font-mono text-[10px] px-2 py-1 text-alive/60 hover:text-alive hover:bg-alive/10 rounded transition-all"
                          title="Publish"
                        >
                          pub
                        </button>
                      )}
                      {room.status !== 'draft' && (
                        <button
                          onClick={() => handleStatusChange(room.id, 'draft')}
                          className="font-mono text-[10px] px-2 py-1 text-white/30 hover:text-white hover:bg-white/10 rounded transition-all"
                          title="Unpublish"
                        >
                          draft
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(room.id)}
                        className="font-mono text-[10px] px-2 py-1 text-cost/40 hover:text-cost hover:bg-cost/10 rounded transition-all"
                        title="Delete"
                      >
                        del
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page === 1}
            className="font-mono text-xs px-3 py-1.5 rounded border border-white/10 text-white/40 hover:text-white hover:bg-white/5 disabled:opacity-20 transition-all"
          >
            Prev
          </button>
          <span className="font-mono text-xs text-white/30">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages, page + 1))}
            disabled={page === totalPages}
            className="font-mono text-xs px-3 py-1.5 rounded border border-white/10 text-white/40 hover:text-white hover:bg-white/5 disabled:opacity-20 transition-all"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
