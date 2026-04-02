import type { Room } from '../../lib/api';
import { assetUrl } from '../../lib/api';

interface Props {
  room: Room;
}

export default function VideoRenderer({ room }: Props) {
  const videoUrl = assetUrl((room as any).video_url);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Video Player */}
      {videoUrl && (
        <div className="relative w-full aspect-video rounded-xl overflow-hidden bg-black">
          <video controls className="w-full h-full" preload="metadata">
            <source src={videoUrl} type="video/mp4" />
            Your browser does not support video playback.
          </video>
        </div>
      )}

      {/* Title & Content */}
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] px-2 py-1 rounded-full border border-cost/20 text-cost">video</span>
          <span className="font-mono text-[10px] text-white/30">Cycle #{room.cycle_number}</span>
        </div>
        <h1 className="text-2xl font-bold text-white">{room.title}</h1>
        <p className="text-white/60 leading-relaxed">{room.content}</p>
      </div>

      {/* Tags */}
      <div className="flex flex-wrap gap-2">
        {room.tags.map((tag) => (
          <span key={tag} className="font-mono text-[10px] px-2 py-1 rounded-full border border-white/10 text-white/30">
            {tag}
          </span>
        ))}
      </div>
    </div>
  );
}
