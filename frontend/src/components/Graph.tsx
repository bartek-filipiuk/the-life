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

const CLUSTER_COLORS = [
  '#c084fc', '#6b9fff', '#ff6b6b', '#00ff88', '#f59e0b',
  '#ec4899', '#14b8a6', '#f97316', '#8b5cf6', '#22d3ee',
];

export default function Graph({ onSelectRoom }: GraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<unknown>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/graph`, { signal: controller.signal })
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() as Promise<GraphData>; })
      .then((data) => { setGraphData(data); setLoading(false); })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setError('Could not load graph data'); setLoading(false);
      });
    return () => controller.abort();
  }, []);

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
    let selectedNode: string | null = null;

    async function initGraph() {
      const { default: GraphClass } = await import('graphology');
      const { default: Sigma } = await import('sigma');

      let louvain: ((g: unknown) => Record<string, number>) | null = null;
      try {
        const mod = await import('graphology-communities-louvain');
        louvain = mod.default ?? mod;
      } catch { /* fallback */ }

      let edgeProgram: unknown = undefined;
      try {
        const mod = await import('@sigma/edge-curve');
        edgeProgram = mod.EdgeCurvedArrowProgram ?? mod.EdgeCurveProgram ?? mod.default;
      } catch { /* straight fallback */ }

      if (!containerRef.current || !graphData) return;

      const graph = new GraphClass();
      const nodeMap = new Map<string, GraphNode>();
      graphData.nodes.forEach((n) => nodeMap.set(n.id, n));

      // Temp graph for Louvain
      graphData.nodes.forEach((node) => graph.addNode(node.id, { label: node.label }));
      graphData.edges.forEach((edge, i) => {
        if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
          try { graph.addEdge(edge.source, edge.target, { key: `e-${i}` }); } catch {}
        }
      });

      // Group by content_type — gives clean, predictable 5 clusters
      const communities: Record<string, number> = {};
      const typeOrder = ['reflection', 'poem', 'essay', 'haiku', 'story'];
      graphData.nodes.forEach((n) => {
        const idx = typeOrder.indexOf(n.content_type);
        communities[n.id] = idx >= 0 ? idx : 0;
      });

      graph.clear();

      // Group by community
      const clusterGroups = new Map<number, string[]>();
      for (const [nodeId, cluster] of Object.entries(communities)) {
        if (!clusterGroups.has(cluster)) clusterGroups.set(cluster, []);
        clusterGroups.get(cluster)!.push(nodeId);
      }

      const clusterKeys = Array.from(clusterGroups.keys()).sort((a, b) => a - b);
      const numClusters = clusterKeys.length;

      // ── Place clusters at fixed positions — spread like star map ──
      // Positions designed for 5 clusters in a pentagon-like spread
      const fixedPositions = [
        { x: 0, y: -280 },     // top center
        { x: 320, y: -80 },    // right
        { x: 200, y: 250 },    // bottom right
        { x: -200, y: 250 },   // bottom left
        { x: -320, y: -80 },   // left
        // extras if more clusters
        { x: 0, y: 0 },
        { x: 400, y: 250 },
        { x: -400, y: 250 },
      ];

      const clusterCenters = new Map<number, { x: number; y: number }>();
      clusterKeys.forEach((clusterId, i) => {
        const pos = fixedPositions[i % fixedPositions.length];
        clusterCenters.set(clusterId, { x: pos.x, y: pos.y });
      });

      // Cluster labels — derive from top tag in each group
      const clusterLabels = new Map<number, string>();
      const typeNames = ['REFLECTIONS', 'POETRY', 'ESSAYS', 'HAIKU', 'STORIES'];
      clusterKeys.forEach((clusterId) => {
        const members = clusterGroups.get(clusterId) || [];
        const tagCounts = new Map<string, number>();
        members.forEach((nid) => {
          (nodeMap.get(nid)?.tags || []).forEach((t) => tagCounts.set(t, (tagCounts.get(t) || 0) + 1));
        });
        const topTag = [...tagCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || '';
        const baseName = typeNames[clusterId] || 'MIXED';
        clusterLabels.set(clusterId, topTag ? `${baseName} & ${topTag.toUpperCase()}` : baseName);
      });

      // ── Place nodes with generous spacing within clusters ──
      clusterKeys.forEach((clusterId) => {
        const members = clusterGroups.get(clusterId) || [];
        const center = clusterCenters.get(clusterId)!;
        // Orbit radius scales with member count but minimum 60
        const orbitRadius = Math.max(80, members.length * 18);

        members.forEach((nodeId, j) => {
          const node = nodeMap.get(nodeId);
          if (!node) return;

          // Even angular distribution with slight jitter
          const angle = (j / members.length) * Math.PI * 2;
          const jitter = (Math.random() - 0.5) * 0.4;
          const r = orbitRadius * (0.4 + (j % 2) * 0.3 + Math.random() * 0.3);
          const x = center.x + r * Math.cos(angle + jitter);
          const y = center.y + r * Math.sin(angle + jitter);

          const nodeColor = contentTypeHex(node.content_type);
          const connectionBonus = (node.size ?? 1) * 1.5;
          const nodeSize = Math.max(8, Math.min(22, 8 + connectionBonus));

          graph.addNode(nodeId, {
            label: node.label,
            x, y,
            size: nodeSize,
            color: nodeColor,
            type: 'circle',
            originalColor: nodeColor,
            originalSize: nodeSize,
            community: clusterId,
          });
        });

        // ── Add invisible "label node" for cluster name ──
        const labelId = `__cluster_label_${clusterId}`;
        const clusterColor = CLUSTER_COLORS[clusterId % CLUSTER_COLORS.length];
        graph.addNode(labelId, {
          label: clusterLabels.get(clusterId) || '',
          x: center.x,
          y: center.y - orbitRadius - 25,
          size: 0.5,  // tiny dot, basically invisible
          color: clusterColor + '00', // transparent
          type: 'circle',
          originalColor: clusterColor + '00',
          originalSize: 0.5,
          community: clusterId,
          isLabel: true,
          forceLabel: true,
        });
      });

      // ── Add edges — thin! ──
      graphData.edges.forEach((edge, index) => {
        if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
          try {
            const srcComm = graph.getNodeAttribute(edge.source, 'community');
            const tgtComm = graph.getNodeAttribute(edge.target, 'community');
            const isInter = srcComm !== tgtComm;

            graph.addEdge(edge.source, edge.target, {
              key: `e-${index}`,
              color: isInter ? '#ffffff02' : '#ffffff04',
              size: isInter ? 0.1 : 0.2,
              curvature: 0.15 + Math.random() * 0.1,
              type: 'curved',
            });
          } catch {}
        }
      });

      if (sigmaRef.current) {
        (sigmaRef.current as { kill: () => void }).kill();
      }

      const sigmaSettings: Record<string, unknown> = {
        renderEdgeLabels: false,
        allowInvalidContainer: true,
        defaultEdgeColor: '#ffffff03',
        defaultNodeColor: '#ffffff',
        labelColor: { color: '#ffffffbb' },
        labelFont: '"JetBrains Mono", monospace',
        labelSize: 11,
        labelWeight: '400',
        labelRenderedSizeThreshold: 6,
        stagePadding: 100,
        // Show cluster labels always (forceLabel)
        nodeReducer: (node: string, data: Record<string, unknown>) => {
          const res = { ...data };

          // Force cluster labels to always show with cluster color
          if (data['isLabel']) {
            const cId = data['community'] as number;
            const clColor = CLUSTER_COLORS[cId % CLUSTER_COLORS.length];
            res['forceLabel'] = true;
            res['labelSize'] = 14;
            res['labelWeight'] = '600';
            res['labelColor'] = clColor + 'cc';
            res['color'] = clColor + '00';
            res['size'] = 0.01;

            if (currentHovered) {
              const hovComm = graph.hasNode(currentHovered) ? graph.getNodeAttribute(currentHovered, 'community') : -1;
              res['labelColor'] = cId === hovComm ? clColor : clColor + '20';
            }
            return res;
          }

          // Selected node — persistent highlight with ring
          if (selectedNode && node === selectedNode) {
            res['highlighted'] = true;
            res['size'] = ((data['originalSize'] as number) ?? 12) * 1.6;
            res['color'] = '#00ff88';
            res['zIndex'] = 100;
            res['forceLabel'] = true;
          }

          // Hovered state
          const activeNode = currentHovered || selectedNode;
          if (activeNode && activeNode !== node) {
            const activeComm = graph.hasNode(activeNode) ? graph.getNodeAttribute(activeNode, 'community') : -1;
            const nodeComm = data['community'];

            if (currentHovered && node === currentHovered) {
              res['highlighted'] = true;
              res['size'] = ((data['originalSize'] as number) ?? 12) * 1.5;
              res['zIndex'] = 100;
            } else if (
              graph.hasEdge(node, activeNode) ||
              graph.hasEdge(activeNode, node)
            ) {
              res['size'] = ((data['originalSize'] as number) ?? 12) * 1.1;
            } else if (nodeComm === activeComm) {
              // Same cluster — keep visible
            } else if (currentHovered) {
              // Only dim when hovering, not for persistent selection
              res['color'] = '#ffffff08';
              res['label'] = '';
            }
          }
          return res;
        },
        edgeReducer: (_edge: string, data: Record<string, unknown>) => {
          const res = { ...data };
          const activeNode = currentHovered || selectedNode;
          if (activeNode) {
            const source = graph.source(_edge);
            const target = graph.target(_edge);
            if (source === activeNode || target === activeNode) {
              res['color'] = currentHovered ? '#ffffff40' : '#00ff8840';
              res['size'] = 1.5;
            } else if (currentHovered) {
              res['color'] = '#ffffff02';
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

      sigma.on('clickNode', (event: { node?: string }) => {
        if (event.node && !event.node.startsWith('__cluster_label_')) {
          selectedNode = event.node;
          sigma?.refresh();
          if (onSelectRoom) onSelectRoom(event.node);
        }
      });

      // Click on background deselects
      sigma.on('clickStage', () => {
        selectedNode = null;
        sigma?.refresh();
      });

      sigma.on('enterNode', (event: { node?: string }) => {
        if (event.node && !event.node.startsWith('__cluster_label_')) {
          currentHovered = event.node; sigma?.refresh();
        }
      });
      sigma.on('leaveNode', () => { currentHovered = null; sigma?.refresh(); });

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
    dir === 'in' ? s.getCamera().animatedZoom({ duration: 300, factor: 1.5 }) : s.getCamera().animatedUnzoom({ duration: 300, factor: 1.5 });
  }, []);

  const handleReset = useCallback(() => {
    (sigmaRef.current as { getCamera: () => { animatedReset: (o: { duration: number }) => void } } | null)?.getCamera().animatedReset({ duration: 300 });
  }, []);

  return (
    <div className="relative w-full" style={{ height: '600px' }}>
      <div className="absolute top-4 left-4 z-10">
        <p className="font-mono text-xs text-white/40 uppercase tracking-[0.3em]">World Map</p>
        <p className="font-mono text-[10px] text-white/20 mt-1">Thematic constellations &middot; Click to explore</p>
      </div>

      <div className="absolute top-4 right-4 z-10 flex flex-col gap-1">
        {[
          { label: '+', action: () => handleZoom('in') },
          { label: '−', action: () => handleZoom('out') },
          { label: '⟲', action: handleReset },
        ].map((btn) => (
          <button key={btn.label} onClick={btn.action}
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
          <p className="font-mono text-sm text-white/40">No rooms yet</p>
        </div>
      )}

      <div ref={containerRef}
        className="w-full h-full rounded-lg border border-white/5 bg-[#06060a]"
        style={{ cursor: 'grab' }} />
    </div>
  );
}
