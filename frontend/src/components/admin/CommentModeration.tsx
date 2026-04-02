import { useState, useEffect } from 'react';
import { adminRequest } from '../../lib/admin-api';

interface Comment {
  id: string;
  room_id: string;
  author_name: string;
  content: string;
  status: string;
  created_at: string;
}

const STATUS_COLORS: Record<string, string> = {
  approved: 'text-alive bg-alive/10',
  pending: 'text-info bg-info/10',
  rejected: 'text-cost bg-cost/10',
};

export default function CommentModeration() {
  const [comments, setComments] = useState<Comment[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);

  useEffect(() => { load(); }, [filter]);

  async function load() {
    setLoading(true);
    try {
      let url = `/admin/comments?limit=50`;
      if (filter) url += `&status=${filter}`;
      const data = await adminRequest<{ comments: Comment[]; total: number }>(url);
      if (data) { setComments(data.comments); setTotal(data.total); }
    } catch { /* backend offline */ }
    finally { setLoading(false); }
  }

  async function setStatus(id: string, status: string) {
    try {
      await adminRequest(`/admin/comments/${id}/status`, {
        method: 'PATCH', body: JSON.stringify({ status }),
      });
      await load();
    } catch { /* update failed */ }
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-2">
        {[undefined, 'pending', 'approved', 'rejected'].map((s) => (
          <button
            key={s ?? 'all'}
            onClick={() => setFilter(s)}
            className={`font-mono text-[10px] px-3 py-1.5 rounded-full border transition-all uppercase ${
              filter === s ? 'text-alive bg-alive/10 border-alive/20' : 'text-white/30 border-white/10 hover:text-white'
            }`}
          >
            {s ?? 'All'}
          </button>
        ))}
        <span className="ml-auto font-mono text-[10px] text-white/20">{total} comments</span>
      </div>

      {loading ? (
        <div className="font-mono text-sm text-white/30 py-8 text-center">Loading...</div>
      ) : comments.length === 0 ? (
        <div className="font-mono text-sm text-white/30 py-8 text-center">No comments</div>
      ) : (
        <div className="space-y-2">
          {comments.map((c) => (
            <div key={c.id} className="border border-white/5 rounded-lg p-4 bg-white/[0.02]">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-white/60 font-medium">{c.author_name}</span>
                  <span className={`font-mono text-[10px] px-2 py-0.5 rounded-full ${STATUS_COLORS[c.status] ?? ''}`}>
                    {c.status}
                  </span>
                  <span className="font-mono text-[10px] text-white/20">
                    room: {c.room_id.slice(0, 8)}...
                  </span>
                </div>
                <span className="font-mono text-[10px] text-white/20">
                  {new Date(c.created_at).toLocaleString()}
                </span>
              </div>
              <p className="text-sm text-white/50 mb-3">{c.content}</p>
              <div className="flex gap-1">
                {c.status !== 'approved' && (
                  <button onClick={() => setStatus(c.id, 'approved')}
                    className="font-mono text-[10px] px-2.5 py-1 text-alive/60 hover:text-alive hover:bg-alive/10 rounded transition-all">
                    Approve
                  </button>
                )}
                {c.status !== 'rejected' && (
                  <button onClick={() => setStatus(c.id, 'rejected')}
                    className="font-mono text-[10px] px-2.5 py-1 text-cost/60 hover:text-cost hover:bg-cost/10 rounded transition-all">
                    Reject
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
