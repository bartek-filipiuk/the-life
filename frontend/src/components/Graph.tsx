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
        console.error('[Graph] Failed to fetch:', err);
        setError('Could not load graph data');
        setLoading(false);
      });

    return () => controller.abort();
  }, []);

  // Initialize Sigma graph — NO hoveredNode in deps (was causing full reinit)
  useEffect(() => {
    if (!graphData || !containerRef.current) return;
    if (graphData.nodes.length === 0) return;

    let sigma: {
      kill: () => void;
      on: (event: string, cb: (e: { node?: string }) => void) => void;
      refresh: () => void;
      setSetting: (key: string, value: unknown) => void;
      getCamera: () => {
        animatedZoom: (opts: { duration: number; factor: number }) => void;
        animatedUnzoom: (opts: { duration: number; factor: number }) => void;
        animatedReset: (opts: { duration: number }) => void;
      };
    } | null = null;

    let currentHovered: string | null = null;

    async function initGraph() {
      const { default: GraphClass } = await import('graphology');
      const { default: Sigma } = await import('sigma');
      const forceAtlas2 = await import('graphology-layout-forceatlas2');

      if (!containerRef.current || !graphData) return;

      const graph = new GraphClass();

      // Add nodes — bigger sizes for visibility
      graphData.nodes.forEach((node: GraphNode) => {
        const connectionSize = node.size ?? 1;
        const nodeSize = Math.max(12, Math.min(35, 10 + connectionSize * 4));
        const color = contentTypeHex(node.content_type);

        graph.addNode(node.id, {
          label: node.label,
          x: Math.random() * 100,
          y: Math.random() * 100,
          size: nodeSize,
          color,
          type: 'circle',
          originalColor: color,
          originalSize: nodeSize,
        });
      });

      // Add edges
      graphData.edges.forEach((edge, index) => {
        if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
          try {
            graph.addEdge(edge.source, edge.target, {
              key: `e-${index}`,
              color: '#ffffff15',
              size: 1.5,
            });
          } catch {
            // Duplicate edge
          }
        }
      });

      // Force-directed layout
      if (graph.order > 1) {
        forceAtlas2.assign(graph, {
          iterations: 150,
          settings: {
            gravity: 2,
            scalingRatio: 15,
            barnesHutOptimize: graph.order > 50,
            strongGravityMode: true,
            slowDown: 8,
          },
        });
      }

      // Kill previous instance
      if (sigmaRef.current) {
        (sigmaRef.current as { kill: () => void }).kill();
      }

      // Create Sigma renderer
      sigma = new Sigma(graph, containerRef.current, {
        renderEdgeLabels: false,
        allowInvalidContainer: true,
        defaultEdgeColor: '#ffffff15',
        defaultNodeColor: '#ffffff',
        labelColor: { color: '#ffffffcc' },
        labelFont: '"JetBrains Mono", monospace',
        labelSize: 13,
        labelWeight: '500',
        labelRenderedSizeThreshold: 8,
        stagePadding: 50,
        zoomToSizeRatioFunction: (x: number) => x,
        nodeReducer: (node: string, data: Record<string, unknown>) => {
          const res = { ...data };
          if (currentHovered) {
            if (node === currentHovered) {
              res['highlighted'] = true;
              res['size'] = ((data['originalSize'] as number) ?? 14) * 1.4;
              res['zIndex'] = 10;
            } else if (
              graph.hasEdge(node, currentHovered) ||
              graph.hasEdge(currentHovered, node)
            ) {
              // Neighbor — keep visible
              res['size'] = ((data['originalSize'] as number) ?? 14) * 1.1;
            } else {
              res['color'] = '#ffffff12';
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
              res['color'] = '#ffffff50';
              res['size'] = 2.5;
            } else {
              res['color'] = '#ffffff05';
            }
          }
          return res;
        },
      });

      // Click → select room
      sigma.on('clickNode', (event: { node?: string }) => {
        if (event.node && onSelectRoom) {
          onSelectRoom(event.node);
        }
      });

      // Hover — use refresh() instead of state (avoids reinit)
      sigma.on('enterNode', (event: { node?: string }) => {
        if (event.node) {
          currentHovered = event.node;
          sigma?.refresh();
        }
      });
      sigma.on('leaveNode', () => {
        currentHovered = null;
        sigma?.refresh();
      });

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
  const handleZoom = useCallback((direction: 'in' | 'out') => {
    const s = sigmaRef.current as { getCamera: () => { animatedZoom: (o: { duration: number; factor: number }) => void; animatedUnzoom: (o: { duration: number; factor: number }) => void } } | null;
    if (!s) return;
    const cam = s.getCamera();
    if (direction === 'in') cam.animatedZoom({ duration: 300, factor: 1.5 });
    else cam.animatedUnzoom({ duration: 300, factor: 1.5 });
  }, []);

  const handleResetZoom = useCallback(() => {
    const s = sigmaRef.current as { getCamera: () => { animatedReset: (o: { duration: number }) => void } } | null;
    if (!s) return;
    s.getCamera().animatedReset({ duration: 300 });
  }, []);

  return (
    <div className="relative w-full" style={{ height: '550px' }}>
      {/* Label */}
      <div className="absolute top-4 left-4 z-10">
        <p className="font-mono text-xs text-white/40 uppercase tracking-[0.3em]">World Map</p>
      </div>

      {/* Zoom controls */}
      <div className="absolute top-4 right-4 z-10 flex flex-col gap-1">
        {[
          { label: '+', action: () => handleZoom('in'), title: 'Zoom in' },
          { label: '−', action: () => handleZoom('out'), title: 'Zoom out' },
          { label: '⟲', action: handleResetZoom, title: 'Reset' },
        ].map((btn) => (
          <button
            key={btn.label}
            onClick={btn.action}
            title={btn.title}
            className="w-9 h-9 rounded bg-white/5 border border-white/10 text-white/50 hover:text-white hover:bg-white/10 transition-all flex items-center justify-center font-mono text-base"
          >
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
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color, boxShadow: `0 0 6px ${item.color}44` }} />
            <span className="font-mono text-xs text-white/50">{item.label}</span>
          </div>
        ))}
      </div>

      {/* Loading */}
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-void/50 z-20">
          <div className="text-center space-y-3">
            <div className="w-8 h-8 border-2 border-alive/30 border-t-alive rounded-full animate-spin mx-auto" />
            <p className="font-mono text-sm text-white/40">Loading graph...</p>
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
      <div
        ref={containerRef}
        className="w-full h-full rounded-lg border border-white/5 bg-[#06060a]"
        style={{ cursor: 'grab' }}
      />
    </div>
  );
}
