import { useEffect, useRef, useState, useCallback } from 'react';
import type { GraphData, GraphNode } from '../lib/api';
import { contentTypeHex } from '../lib/api';

interface GraphProps {
  onSelectRoom?: (roomId: string) => void;
}

/**
 * Interactive force-directed graph visualization using Sigma.js + Graphology.
 * Rendered as a React island for client-side interactivity.
 */
export default function Graph({ onSelectRoom }: GraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<unknown>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Fetch graph data
  useEffect(() => {
    const apiUrl =
      (import.meta as unknown as { env?: Record<string, string> }).env?.PUBLIC_API_URL ??
      'http://localhost:8000';

    const controller = new AbortController();

    fetch(`${apiUrl}/graph`, { signal: controller.signal })
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
        console.error('[Graph] Failed to fetch graph data:', err);
        setError('Could not load graph data');
        setLoading(false);
      });

    return () => controller.abort();
  }, []);

  // Initialize Sigma graph
  useEffect(() => {
    if (!graphData || !containerRef.current) return;
    if (graphData.nodes.length === 0) return;

    let sigma: { kill: () => void; on: (event: string, cb: (e: { node?: string }) => void) => void } | null = null;

    async function initGraph() {
      // Dynamic imports to avoid SSR issues
      const { default: GraphClass } = await import('graphology');
      const { default: Sigma } = await import('sigma');
      const forceAtlas2 = await import('graphology-layout-forceatlas2');

      if (!containerRef.current || !graphData) return;

      const graph = new GraphClass();

      // Add nodes
      graphData.nodes.forEach((node: GraphNode) => {
        const size = Math.max(6, Math.min(25, 6 + node.connections_count * 3));
        const color = contentTypeHex(node.content_type);

        graph.addNode(node.id, {
          label: node.label,
          x: Math.random() * 100,
          y: Math.random() * 100,
          size,
          color,
          type: 'circle',
          // Store metadata for interactions
          borderColor: node.is_latest ? '#00ff88' : color,
          borderSize: node.is_latest ? 3 : 0,
        });
      });

      // Add edges
      graphData.edges.forEach((edge, index) => {
        const sourceExists = graph.hasNode(edge.source);
        const targetExists = graph.hasNode(edge.target);
        if (sourceExists && targetExists) {
          try {
            graph.addEdge(edge.source, edge.target, {
              key: `e-${index}`,
              color: '#ffffff10',
              size: 1,
            });
          } catch {
            // Duplicate edge, skip
          }
        }
      });

      // Apply force-directed layout
      if (graph.order > 1) {
        forceAtlas2.assign(graph, {
          iterations: 100,
          settings: {
            gravity: 1,
            scalingRatio: 10,
            barnesHutOptimize: graph.order > 50,
            strongGravityMode: true,
            slowDown: 5,
          },
        });
      }

      // Clear existing sigma instance
      if (sigmaRef.current) {
        (sigmaRef.current as { kill: () => void }).kill();
      }

      // Create Sigma renderer
      sigma = new Sigma(graph, containerRef.current, {
        renderEdgeLabels: false,
        allowInvalidContainer: true,
        defaultEdgeColor: '#ffffff10',
        defaultNodeColor: '#ffffff',
        labelColor: { color: '#ffffff' },
        labelFont: '"JetBrains Mono", monospace',
        labelSize: 11,
        labelWeight: '500',
        stagePadding: 40,
        nodeReducer: (node: string, data: Record<string, unknown>) => {
          const res = { ...data };
          if (hoveredNode) {
            if (node === hoveredNode) {
              res['highlighted'] = true;
              res['size'] = (data['size'] as number ?? 10) * 1.3;
            } else if (!graph.hasEdge(node, hoveredNode) && !graph.hasEdge(hoveredNode, node)) {
              res['color'] = '#ffffff15';
              res['label'] = '';
            }
          }
          return res;
        },
        edgeReducer: (_edge: string, data: Record<string, unknown>) => {
          const res = { ...data };
          if (hoveredNode) {
            const [source, target] = [
              graph.source(_edge),
              graph.target(_edge),
            ];
            if (source === hoveredNode || target === hoveredNode) {
              res['color'] = '#ffffff40';
              res['size'] = 2;
            } else {
              res['color'] = '#ffffff05';
            }
          }
          return res;
        },
      });

      // Click handler
      sigma.on('clickNode', (event: { node?: string }) => {
        if (event.node && onSelectRoom) {
          onSelectRoom(event.node);
        }
      });

      // Hover handler
      sigma.on('enterNode', (event: { node?: string }) => {
        if (event.node) setHoveredNode(event.node);
      });
      sigma.on('leaveNode', () => {
        setHoveredNode(null);
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
  }, [graphData, onSelectRoom, hoveredNode]);

  // Zoom controls
  const handleZoom = useCallback((direction: 'in' | 'out') => {
    const sigma = sigmaRef.current as {
      getCamera: () => { animatedZoom: (opts: { duration: number; factor: number }) => void; animatedUnzoom: (opts: { duration: number; factor: number }) => void };
    } | null;
    if (!sigma) return;
    const camera = sigma.getCamera();
    if (direction === 'in') {
      camera.animatedZoom({ duration: 300, factor: 1.5 });
    } else {
      camera.animatedUnzoom({ duration: 300, factor: 1.5 });
    }
  }, []);

  const handleResetZoom = useCallback(() => {
    const sigma = sigmaRef.current as {
      getCamera: () => { animatedReset: (opts: { duration: number }) => void };
    } | null;
    if (!sigma) return;
    sigma.getCamera().animatedReset({ duration: 300 });
  }, []);

  return (
    <div className="relative w-full" style={{ height: '500px' }}>
      {/* Section label */}
      <div className="absolute top-4 left-4 z-10">
        <p className="font-mono text-[10px] text-white/30 uppercase tracking-[0.3em]">
          World Map
        </p>
      </div>

      {/* Zoom controls */}
      <div className="absolute top-4 right-4 z-10 flex flex-col gap-1">
        <button
          onClick={() => handleZoom('in')}
          className="w-8 h-8 rounded bg-white/5 border border-white/10 text-white/50 hover:text-white hover:bg-white/10 transition-all flex items-center justify-center font-mono text-sm"
          title="Zoom in"
        >
          +
        </button>
        <button
          onClick={() => handleZoom('out')}
          className="w-8 h-8 rounded bg-white/5 border border-white/10 text-white/50 hover:text-white hover:bg-white/10 transition-all flex items-center justify-center font-mono text-sm"
          title="Zoom out"
        >
          -
        </button>
        <button
          onClick={handleResetZoom}
          className="w-8 h-8 rounded bg-white/5 border border-white/10 text-white/50 hover:text-white hover:bg-white/10 transition-all flex items-center justify-center font-mono text-xs"
          title="Reset zoom"
        >
          R
        </button>
      </div>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 z-10 flex flex-wrap gap-3">
        {[
          { label: 'Poem', color: '#c084fc' },
          { label: 'Essay', color: '#6b9fff' },
          { label: 'Haiku', color: '#00ff88' },
          { label: 'Reflection', color: '#ff6b6b' },
          { label: 'Story', color: '#ffffff' },
        ].map((item) => (
          <div key={item.label} className="flex items-center gap-1.5">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <span className="font-mono text-[10px] text-white/40 uppercase">
              {item.label}
            </span>
          </div>
        ))}
      </div>

      {/* Loading state */}
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-void/50 z-20">
          <div className="text-center space-y-3">
            <div className="w-8 h-8 border-2 border-alive/30 border-t-alive rounded-full animate-spin mx-auto" />
            <p className="font-mono text-sm text-white/40">Loading graph...</p>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && !loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-void/50 z-20">
          <div className="text-center space-y-3 p-8">
            <div className="w-12 h-12 rounded-full border border-white/10 flex items-center justify-center mx-auto">
              <svg className="w-6 h-6 text-white/30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
              </svg>
            </div>
            <p className="font-mono text-sm text-white/40">{error}</p>
            <p className="font-mono text-xs text-white/20">
              Backend may be offline. Start with: uvicorn app.main:app
            </p>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && graphData && graphData.nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center z-20">
          <div className="text-center space-y-3 p-8">
            <div className="w-16 h-16 rounded-full border border-white/10 flex items-center justify-center mx-auto">
              <div className="w-3 h-3 rounded-full bg-alive animate-pulse" />
            </div>
            <p className="font-mono text-sm text-white/40">No rooms yet</p>
            <p className="font-mono text-xs text-white/20">
              The AI will create its first room soon...
            </p>
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
