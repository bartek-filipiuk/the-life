import { useEffect, useRef, useState, useCallback } from 'react';
import type { GraphData, GraphNode } from '../lib/api';
import { contentTypeHex } from '../lib/api';

interface GraphProps {
  onSelectRoom?: (roomId: string) => void;
}

const API_URL =
  typeof window !== 'undefined'
    ? (import.meta as unknown as { env?: Record<string, string> }).env?.PUBLIC_API_URL ?? 'http://localhost:8765'
    : 'http://localhost:8765';

/**
 * Time Spiral Graph — rooms laid out on an Archimedean spiral.
 * Center = first room (Day 0), outer edge = latest.
 * Curved edges connect thematically related rooms.
 */
export default function Graph({ onSelectRoom }: GraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<unknown>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch graph data
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/graph`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<GraphData>;
      })
      .then((data) => {
        setGraphData(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setError('Could not load graph data');
        setLoading(false);
      });
    return () => controller.abort();
  }, []);

  // Build graph with spiral layout
  useEffect(() => {
    if (!graphData || !containerRef.current || graphData.nodes.length === 0) return;

    let sigma: {
      kill: () => void;
      on: (event: string, cb: (e: { node?: string }) => void) => void;
      refresh: () => void;
      getCamera: () => {
        animatedZoom: (o: { duration: number; factor: number }) => void;
        animatedUnzoom: (o: { duration: number; factor: number }) => void;
        animatedReset: (o: { duration: number }) => void;
      };
    } | null = null;

    let currentHovered: string | null = null;

    async function initGraph() {
      const { default: GraphClass } = await import('graphology');
      const { default: Sigma } = await import('sigma');

      // Try to import edge-curve, fall back to default
      let edgeProgram: unknown = undefined;
      try {
        const mod = await import('@sigma/edge-curve');
        edgeProgram = mod.EdgeCurvedArrowProgram ?? mod.EdgeCurveProgram ?? mod.default;
      } catch {
        // edge-curve not available, use default straight lines
      }

      if (!containerRef.current || !graphData) return;

      const graph = new GraphClass();

      // Sort nodes by cycle_number for spiral placement
      const sortedNodes = [...graphData.nodes].sort(
        (a, b) => (a.cycle_number ?? 0) - (b.cycle_number ?? 0)
      );

      const n = sortedNodes.length;

      // Archimedean spiral: r = a + b*θ
      // θ increases per node, r grows outward
      const spiralSpacing = 55;   // distance between spiral arms — generous
      const angleStep = 2.399;    // golden angle ≈ 137.5° for even distribution
      const centerX = 0;
      const centerY = 0;

      sortedNodes.forEach((node: GraphNode, index: number) => {
        // Spiral coordinates
        const theta = index * angleStep;
        const r = spiralSpacing * Math.sqrt(index + 1); // sqrt for even density
        const x = centerX + r * Math.cos(theta);
        const y = centerY + r * Math.sin(theta);

        // Size grows slightly with time (AI evolves)
        const baseSize = 10;
        const growthFactor = 1 + (index / n) * 0.8; // 1.0 → 1.8x
        const connectionBonus = (node.size ?? 1) * 2;
        const nodeSize = Math.max(12, Math.min(32, baseSize * growthFactor + connectionBonus));

        const color = contentTypeHex(node.content_type);
        const isLatest = index === n - 1;

        graph.addNode(node.id, {
          label: node.label,
          x,
          y,
          size: nodeSize,
          color,
          type: 'circle',
          originalColor: color,
          originalSize: nodeSize,
          borderColor: isLatest ? '#00ff88' : undefined,
          borderSize: isLatest ? 3 : 0,
          zIndex: isLatest ? 10 : index,
        });
      });

      // Add edges with curvature
      graphData.edges.forEach((edge, index) => {
        if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
          try {
            graph.addEdge(edge.source, edge.target, {
              key: `e-${index}`,
              color: '#ffffff0c',
              size: 0.8,
              curvature: 0.3 + Math.random() * 0.2, // slight variation
              type: 'curved',
            });
          } catch {
            // duplicate
          }
        }
      });

      // Kill previous
      if (sigmaRef.current) {
        (sigmaRef.current as { kill: () => void }).kill();
      }

      // Sigma settings
      const sigmaSettings: Record<string, unknown> = {
        renderEdgeLabels: false,
        allowInvalidContainer: true,
        defaultEdgeColor: '#ffffff18',
        defaultNodeColor: '#ffffff',
        labelColor: { color: '#ffffffcc' },
        labelFont: '"JetBrains Mono", monospace',
        labelSize: 12,
        labelWeight: '500',
        labelRenderedSizeThreshold: 10,
        stagePadding: 60,
        nodeReducer: (node: string, data: Record<string, unknown>) => {
          const res = { ...data };
          if (currentHovered) {
            if (node === currentHovered) {
              res['highlighted'] = true;
              res['size'] = ((data['originalSize'] as number) ?? 14) * 1.5;
              res['zIndex'] = 100;
            } else if (
              graph.hasEdge(node, currentHovered) ||
              graph.hasEdge(currentHovered, node)
            ) {
              res['size'] = ((data['originalSize'] as number) ?? 14) * 1.15;
            } else {
              res['color'] = '#ffffff10';
              res['label'] = '';
            }
          }
          return res;
        },
        edgeReducer: (_edge: string, data: Record<string, unknown>) => {
          const res = { ...data };
          if (currentHovered) {
            const source = graph.source(_edge);
            const target = graph.target(_edge);
            if (source === currentHovered || target === currentHovered) {
              res['color'] = '#ffffff60';
              res['size'] = 2.5;
            } else {
              res['color'] = '#ffffff04';
            }
          }
          return res;
        },
      };

      // Use curved edges if available
      if (edgeProgram) {
        sigmaSettings['defaultEdgeType'] = 'curved';
        sigmaSettings['edgeProgramClasses'] = { curved: edgeProgram };
      }

      sigma = new Sigma(graph, containerRef.current, sigmaSettings);

      // Click → select room
      sigma.on('clickNode', (event: { node?: string }) => {
        if (event.node && onSelectRoom) onSelectRoom(event.node);
      });

      // Hover via refresh (no state dependency)
      sigma.on('enterNode', (event: { node?: string }) => {
        if (event.node) { currentHovered = event.node; sigma?.refresh(); }
      });
      sigma.on('leaveNode', () => {
        currentHovered = null; sigma?.refresh();
      });

      // Zoom out slightly to show full spiral with breathing room
      const camera = sigma.getCamera();
      camera.animatedReset({ duration: 0 });

      sigmaRef.current = sigma;
    }

    initGraph().catch(console.error);

    return () => {
      if (sigmaRef.current) {
        (sigmaRef.current as { kill: () => void }).kill();
        sigmaRef.current = null;
      }
    };
  }, [graphData, onSelectRoom]);

  // Zoom controls
  const handleZoom = useCallback((dir: 'in' | 'out') => {
    const s = sigmaRef.current as { getCamera: () => { animatedZoom: (o: { duration: number; factor: number }) => void; animatedUnzoom: (o: { duration: number; factor: number }) => void } } | null;
    if (!s) return;
    const cam = s.getCamera();
    dir === 'in' ? cam.animatedZoom({ duration: 300, factor: 1.5 }) : cam.animatedUnzoom({ duration: 300, factor: 1.5 });
  }, []);

  const handleReset = useCallback(() => {
    const s = sigmaRef.current as { getCamera: () => { animatedReset: (o: { duration: number }) => void } } | null;
    s?.getCamera().animatedReset({ duration: 300 });
  }, []);

  return (
    <div className="relative w-full" style={{ height: '600px' }}>
      {/* Title */}
      <div className="absolute top-4 left-4 z-10">
        <p className="font-mono text-xs text-white/40 uppercase tracking-[0.3em]">World Map</p>
        <p className="font-mono text-[10px] text-white/20 mt-1">Center = Day 0 &middot; Outer = Latest</p>
      </div>

      {/* Zoom */}
      <div className="absolute top-4 right-4 z-10 flex flex-col gap-1">
        {[
          { label: '+', action: () => handleZoom('in'), title: 'Zoom in' },
          { label: '−', action: () => handleZoom('out'), title: 'Zoom out' },
          { label: '⟲', action: handleReset, title: 'Reset' },
        ].map((btn) => (
          <button key={btn.label} onClick={btn.action} title={btn.title}
            className="w-9 h-9 rounded bg-white/5 border border-white/10 text-white/50 hover:text-white hover:bg-white/10 transition-all flex items-center justify-center font-mono text-base">
            {btn.label}
          </button>
        ))}
      </div>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 z-10 flex flex-wrap gap-4">
        {[
          { label: 'Poem', color: '#c084fc' },
          { label: 'Essay', color: '#6b9fff' },
          { label: 'Haiku', color: '#00ff88' },
          { label: 'Reflection', color: '#ff6b6b' },
          { label: 'Story', color: '#ffffff' },
        ].map((item) => (
          <div key={item.label} className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color, boxShadow: `0 0 8px ${item.color}44` }} />
            <span className="font-mono text-xs text-white/50">{item.label}</span>
          </div>
        ))}
      </div>

      {/* Loading */}
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-void/50 z-20">
          <div className="text-center space-y-3">
            <div className="w-8 h-8 border-2 border-alive/30 border-t-alive rounded-full animate-spin mx-auto" />
            <p className="font-mono text-sm text-white/40">Loading spiral...</p>
          </div>
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-void/50 z-20">
          <p className="font-mono text-sm text-white/40">{error}</p>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && graphData && graphData.nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center z-20">
          <div className="text-center space-y-3">
            <div className="w-3 h-3 rounded-full bg-alive animate-pulse mx-auto" />
            <p className="font-mono text-sm text-white/40">No rooms yet</p>
          </div>
        </div>
      )}

      {/* Sigma container */}
      <div ref={containerRef}
        className="w-full h-full rounded-lg border border-white/5 bg-[#06060a]"
        style={{ cursor: 'grab' }} />
    </div>
  );
}
