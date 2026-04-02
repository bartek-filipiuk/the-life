import { useState, useEffect } from 'react';
import { BASE_URL } from '../lib/api';

interface Comment {
  id: string;
  author_name: string;
  content: string;
  created_at: string;
}

interface Props {
  roomId: string;
}

export default function CommentSection({ roomId }: Props) {
  const [comments, setComments] = useState<Comment[]>([]);
  const [name, setName] = useState('');
  const [content, setContent] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => { loadComments(); }, [roomId]);

  async function loadComments() {
    try {
      const resp = await fetch(`${BASE_URL}/rooms/${roomId}/comments`);
      if (resp.ok) setComments(await resp.json());
    } catch { /* backend offline */ }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !content.trim()) return;

    setSubmitting(true);
    setError('');
    setSuccess('');

    try {
      const resp = await fetch(`${BASE_URL}/rooms/${roomId}/comments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ author_name: name.trim(), content: content.trim() }),
      });

      if (resp.ok) {
        const data = await resp.json();
        setSuccess(data.status === 'approved' ? 'Comment posted!' : 'Comment submitted for review.');
        setContent('');
        await loadComments();
        setTimeout(() => setSuccess(''), 5000);
      } else {
        const data = await resp.json().catch(() => ({}));
        setError(data.detail || 'Failed to submit comment');
      }
    } catch {
      setError('Cannot reach server');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <div className="w-1 h-1 rounded-full bg-info"></div>
        <h3 className="font-mono text-xs uppercase tracking-[0.3em] text-white/30">
          Comments ({comments.length})
        </h3>
      </div>

      {/* Comment list */}
      {comments.length > 0 && (
        <div className="space-y-3">
          {comments.map((c) => (
            <div key={c.id} className="border border-white/5 rounded-lg p-4 bg-white/[0.02]">
              <div className="flex items-center gap-2 mb-2">
                <span className="font-mono text-xs text-white/60 font-medium">{c.author_name}</span>
                <span className="font-mono text-[10px] text-white/20">
                  {new Date(c.created_at).toLocaleString()}
                </span>
              </div>
              <p className="text-sm text-white/50 leading-relaxed">{c.content}</p>
            </div>
          ))}
        </div>
      )}

      {/* Submit form */}
      <form onSubmit={submit} className="border border-white/5 rounded-lg p-4 bg-white/[0.02] space-y-3">
        <div className="font-mono text-[10px] text-white/20 uppercase tracking-wider">Leave a comment</div>

        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Your name"
          maxLength={50}
          className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded font-mono text-sm text-white placeholder-white/20 focus:border-alive/30 focus:outline-none"
        />

        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Share your thoughts..."
          rows={3}
          maxLength={1000}
          className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded font-mono text-sm text-white placeholder-white/20 focus:border-alive/30 focus:outline-none resize-none"
        />

        {error && <div className="font-mono text-xs text-cost">{error}</div>}
        {success && <div className="font-mono text-xs text-alive">{success}</div>}

        <button
          type="submit"
          disabled={submitting || !name.trim() || !content.trim()}
          className="px-4 py-2 bg-alive/10 border border-alive/30 rounded font-mono text-xs text-alive hover:bg-alive/20 disabled:opacity-30 transition-all uppercase tracking-wider"
        >
          {submitting ? 'Sending...' : 'Submit'}
        </button>
      </form>
    </div>
  );
}
