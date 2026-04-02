import type { Room } from '../../lib/api';

interface Props {
  room: Room;
}

export default function MicroRenderer({ room }: Props) {
  return (
    <div className="max-w-2xl mx-auto flex items-center justify-center min-h-[50vh]">
      <div className="text-center space-y-6">
        <div className="font-mono text-[10px] text-alive/60 uppercase tracking-[0.3em]">
          Micro &middot; Cycle #{room.cycle_number}
        </div>

        <blockquote className="text-2xl md:text-4xl font-light text-white leading-relaxed px-8">
          &ldquo;{room.content}&rdquo;
        </blockquote>

        <div className="flex items-center justify-center gap-3 font-mono text-[10px] text-white/20">
          <span>{room.mood}</span>
          {room.tags.length > 0 && (
            <>
              <span>&middot;</span>
              <span>{room.tags.join(', ')}</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
