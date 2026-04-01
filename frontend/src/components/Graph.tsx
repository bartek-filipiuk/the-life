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

// Cluster color palette — distinct, vibrant
const CLUSTER_COLORS = [
  '#c084fc', '#6b9fff', '#ff6b6b', '#00ff88', '#f59e0b',
  '#ec4899', '#14b8a6', '#f97316', '#8b5cf6', '#22d3ee',
];

// Content type labels for clusters
const CLUSTER_LABELS_FALLBACK = [
  'CLUSTER A', 'CLUSTER B', 'CLUSTER C', 'CLUSTER D', 'CLUSTER E',
  'CLUSTER F', 'CLUSTER G', 'CLUSTER H', 'CLUSTER I', 'CLUSTER J',
];

/**
 * Constellation Graph — nodes auto-clustered by Louvain community detection.
 * Each cluster is a "star system" placed on a circle, nodes orbit within.
 * Inter-cluster edges are dashed/subtle, intra-cluster edges are solid.
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
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() as Promise<GraphData>; })
      .then((data) => { setGraphData(data); setLoading(false); })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setError('Could not load graph data');
        setLoading(false);
      });
    return () => controller.abort();
  }, []);

  // Build constellation graph
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

      // Try Louvain community detection
      let louvain: ((g: unknown) => Record<string, number>) | null = null;
      try {
        const mod = await import('graphology-communities-louvain');
        louvain = mod.default ?? mod;
      } catch { /* fallback to content_type grouping */ }

      // Try curved edges
      let edgeProgram: unknown = undefined;
      try {
        const mod = await import('@sigma/edge-curve');
        edgeProgram = mod.EdgeCurvedArrowProgram ?? mod.EdgeCurveProgram ?? mod.default;
      } catch { /* straight lines fallback */ }

      if (!containerRef.current || !graphData) return;

      const graph = new GraphClass();

      // Build node map for lookup
      const nodeMap = new Map<string, GraphNode>();
      graphData.nodes.forEach((n) => nodeMap.set(n.id, n));

      // Add all nodes temporarily (for Louvain)
      graphData.nodes.forEach((node) => {
        graph.addNode(node.id, { label: node.label });
      });
      graphData.edges.forEach((edge, i) => {
        if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
          try { graph.addEdge(edge.source, edge.target, { key: `e-${i}` }); } catch { /* dup */ }
        }
      });

      // Detect communities
      let communities: Record<string, number> = {};
      if (louvain && graph.order > 2 && graph.size > 0) {
        try {
          communities = louvain(graph) as Record<string, number>;
        } catch {
          // Fallback: group by content_type
          graphData.nodes.forEach((n) => {
            const types = ['reflection', 'poem', 'essay', 'haiku', 'story'];
            communities[n.id] = types.indexOf(n.content_type) >= 0 ? types.indexOf(n.content_type) : 0;
          });
        }
      } else {
        // Fallback: group by content_type
        const types = ['reflection', 'poem', 'essay', 'haiku', 'story'];
        graphData.nodes.forEach((n) => {
          communities[n.id] = types.indexOf(n.content_type) >= 0 ? types.indexOf(n.content_type) : 0;
        });
      }

      // Clear and rebuild with positions
      graph.clear();

      // Group nodes by community
      const clusterGroups = new Map<number, string[]>();
      for (const [nodeId, cluster] of Object.entries(communities)) {
        if (!clusterGroups.has(cluster)) clusterGroups.set(cluster, []);
        clusterGroups.get(cluster)!.push(nodeId);
      }

      const numClusters = clusterGroups.size;
      const clusterKeys = Array.from(clusterGroups.keys()).sort((a, b) => a - b);

      // Place cluster centers on a large circle
      const mainRadius = Math.max(150, numClusters * 60);
      const clusterCenters = new Map<number, { x: number; y: number }>();

      clusterKeys.forEach((clusterId, i) => {
        const angle = (i / numClusters) * Math.PI * 2 - Math.PI / 2;
        clusterCenters.set(clusterId, {
          x: mainRadius * Math.cos(angle),
          y: mainRadius * Math.sin(angle),
        });
      });

      // Build cluster labels from most common tags/types
      const clusterLabels = new Map<number, string>();
      clusterKeys.forEach((clusterId) => {
        const members = clusterGroups.get(clusterId) || [];
        const typeCounts = new Map<string, number>();
        members.forEach((nid) => {
          const node = nodeMap.get(nid);
          if (node) {
            const t = node.content_type || 'unknown';
            typeCounts.set(t, (typeCounts.get(t) || 0) + 1);
          }
        });
        const topType = [...typeCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || 'mixed';
        const tags = members.flatMap((nid) => nodeMap.get(nid)?.tags || []);
        const tagCounts = new Map<string, number>();
        tags.forEach((t) => tagCounts.set(t, (tagCounts.get(t) || 0) + 1));
        const topTag = [...tagCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || '';
        clusterLabels.set(clusterId, `${topType.toUpperCase()}${topTag ? ' · ' + topTag : ''}`);
      });

      // Place nodes around their cluster center
      clusterKeys.forEach((clusterId) => {
        const members = clusterGroups.get(clusterId) || [];
        const center = clusterCenters.get(clusterId)!;
        const orbitRadius = Math.max(40, members.length * 12);

        members.forEach((nodeId, j) => {
          const node = nodeMap.get(nodeId);
          if (!node) return;

          const angle = (j / members.length) * Math.PI * 2 + Math.random() * 0.3;
          const r = orbitRadius * (0.3 + Math.random() * 0.7);
          const x = center.x + r * Math.cos(angle);
          const y = center.y + r * Math.sin(angle);

          const clusterColor = CLUSTER_COLORS[clusterId % CLUSTER_COLORS.length];
          const nodeColor = contentTypeHex(node.content_type);
          const connectionBonus = (node.size ?? 1) * 2;
          const nodeSize = Math.max(10, Math.min(28, 10 + connectionBonus));

          graph.addNode(nodeId, {
            label: node.label,
            x, y,
            size: nodeSize,
            color: nodeColor,
            type: 'circle',
            originalColor: nodeColor,
            originalSize: nodeSize,
            community: clusterId,
            clusterColor,
          });
        });
      });

      // Add edges
      graphData.edges.forEach((edge, index) => {
        if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
          try {
            const srcCommunity = graph.getNodeAttribute(edge.source, 'community');
            const tgtCommunity = graph.getNodeAttribute(edge.target, 'community');
            const isInterCluster = srcCommunity !== tgtCommunity;

            graph.addEdge(edge.source, edge.target, {
              key: `e-${index}`,
              color: isInterCluster ? '#ffffff08' : '#ffffff18',
              size: isInterCluster ? 0.5 : 1,
              curvature: 0.2 + Math.random() * 0.15,
              type: 'curved',
              interCluster: isInterCluster,
            });
          } catch { /* dup */ }
        }
      });

      // Kill previous
      if (sigmaRef.current) {
        (sigmaRef.current as { kill: () => void }).kill();
      }

      const sigmaSettings: Record<string, unknown> = {
        renderEdgeLabels: false,
        allowInvalidContainer: true,
        defaultEdgeColor: '#ffffff12',
        defaultNodeColor: '#ffffff',
        labelColor: { color: '#ffffffcc' },
        labelFont: '"JetBrains Mono", monospace',
        labelSize: 12,
        labelWeight: '500',
        labelRenderedSizeThreshold: 9,
        stagePadding: 80,
        nodeReducer: (node: string, data: Record<string, unknown>) => {
          const res = { ...data };
          if (currentHovered) {
            const hoveredCommunity = graph.getNodeAttribute(currentHovered, 'community');
            const nodeCommunity = data['community'];

            if (node === currentHovered) {
              res['highlighted'] = true;
              res['size'] = ((data['originalSize'] as number) ?? 14) * 1.5;
              res['zIndex'] = 100;
            } else if (
              graph.hasEdge(node, currentHovered) ||
              graph.hasEdge(currentHovered, node)
            ) {
              // Direct neighbor
              res['size'] = ((data['originalSize'] as number) ?? 14) * 1.15;
            } else if (nodeCommunity === hoveredCommunity) {
              // Same cluster — slightly dimmed
              res['color'] = ((data['originalColor'] as string) ?? '#fff') + 'aa';
            } else {
              // Other cluster — heavily dimmed
              res['color'] = '#ffffff08';
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
              res['color'] = '#ffffff03';
            }
          }
          return res;
        },
      };

      if (edgeProgram) {
        sigmaSettings['defaultEdgeType'] = 'curved';
        sigmaSettings['edgeProgramClasses'] = { curved: edgeProgram };
      }

      sigma = new Sigma(graph, containerRef.current, sigmaSettings);

      // Click
      sigma.on('clickNode', (event: { node?: string }) => {
        if (event.node && onSelectRoom) onSelectRoom(event.node);
      });

      // Hover
      sigma.on('enterNode', (event: { node?: string }) => {
        if (event.node) { currentHovered = event.node; sigma?.refresh(); }
      });
      sigma.on('leaveNode', () => {
        currentHovered = null; sigma?.refresh();
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
      <div className="absolute top-4 left-4 z-10">
        <p className="font-mono text-xs text-white/40 uppercase tracking-[0.3em]">World Map</p>
        <p className="font-mono text-[10px] text-white/20 mt-1">Clusters = thematic islands &middot; Click to explore</p>
      </div>

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

      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-void/50 z-20">
          <div className="text-center space-y-3">
            <div className="w-8 h-8 border-2 border-alive/30 border-t-alive rounded-full animate-spin mx-auto" />
            <p className="font-mono text-sm text-white/40">Detecting constellations...</p>
          </div>
        </div>
      )}

      {error && !loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-void/50 z-20">
          <p className="font-mono text-sm text-white/40">{error}</p>
        </div>
      )}

      {!loading && !error && graphData && graphData.nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center z-20">
          <div className="text-center space-y-3">
            <div className="w-3 h-3 rounded-full bg-alive animate-pulse mx-auto" />
            <p className="font-mono text-sm text-white/40">No rooms yet</p>
          </div>
        </div>
      )}

      <div ref={containerRef}
        className="w-full h-full rounded-lg border border-white/5 bg-[#06060a]"
        style={{ cursor: 'grab' }} />
    </div>
  );
}
