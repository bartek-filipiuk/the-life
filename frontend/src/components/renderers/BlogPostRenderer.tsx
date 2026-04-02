import type { Room } from '../../lib/api';
import { assetUrl, formatCost, formatDuration } from '../../lib/api';

interface Props {
  room: Room;
}

export default function BlogPostRenderer({ room }: Props) {
  const readingTime = Math.max(1, Math.ceil(room.content.split(/\s+/).length / 200));
  const imageUrl = assetUrl(room.image_url);

  return (
    <article className="max-w-3xl mx-auto">
      {/* Hero Image */}
      {imageUrl && (
        <div className="relative w-full aspect-[2/1] rounded-xl overflow-hidden mb-8">
          <img src={imageUrl} alt={room.title} className="w-full h-full object-cover" loading="lazy" />
          <div className="absolute inset-0 bg-gradient-to-t from-void/80 to-transparent" />
        </div>
      )}

      {/* Meta */}
      <div className="flex items-center gap-4 mb-4 font-mono text-[10px] text-white/30 uppercase tracking-wider">
        <span className="text-info">Blog Post</span>
        <span>&middot;</span>
        <span>{readingTime} min read</span>
        <span>&middot;</span>
        <span>Cycle #{room.cycle_number}</span>
        <span>&middot;</span>
        <span>{new Date(room.created_at).toLocaleDateString()}</span>
      </div>

      {/* Title */}
      <h1 className="text-3xl md:text-4xl font-bold text-white mb-6 leading-tight">
        {room.title}
      </h1>

      {/* Tags */}
      <div className="flex flex-wrap gap-2 mb-8">
        {room.tags.map((tag) => (
          <span key={tag} className="font-mono text-[10px] px-2.5 py-1 rounded-full border border-white/10 text-white/40">
            {tag}
          </span>
        ))}
      </div>

      {/* Content — rendered as simple HTML with basic markdown */}
      <div
        className="prose prose-invert prose-sm max-w-none
          prose-headings:font-mono prose-headings:text-white prose-headings:font-bold
          prose-p:text-white/70 prose-p:leading-relaxed
          prose-a:text-alive prose-a:no-underline hover:prose-a:underline
          prose-strong:text-white prose-em:text-white/80
          prose-code:text-creative prose-code:bg-white/5 prose-code:px-1.5 prose-code:rounded
          prose-blockquote:border-alive/30 prose-blockquote:text-white/50
          prose-li:text-white/70
          space-y-4"
        dangerouslySetInnerHTML={{ __html: markdownToHtml(room.content) }}
      />

      {/* Audio player */}
      {room.music_url && (
        <div className="mt-8 p-4 bg-white/[0.02] border border-white/5 rounded-lg">
          <div className="font-mono text-[10px] text-white/20 uppercase tracking-wider mb-2">Generated Audio</div>
          <audio controls className="w-full" preload="none">
            <source src={assetUrl(room.music_url)!} />
          </audio>
          {room.music_prompt && <p className="font-mono text-[10px] text-white/20 mt-2">Prompt: {room.music_prompt}</p>}
        </div>
      )}
    </article>
  );
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function markdownToHtml(md: string): string {
  return escapeHtml(md)
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^> (.+)$/gm, '<blockquote><p>$1</p></blockquote>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/^(?!<[hbluo])(.+)$/gm, '<p>$1</p>')
    .replace(/<p><\/p>/g, '');
}
