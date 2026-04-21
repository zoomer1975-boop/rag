"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef } from "react";
import type { ForceGraphMethods } from "react-force-graph-2d";
import type { GraphEdge, GraphNode } from "@/lib/api";

// react-force-graph-2d touches window/canvas — must not SSR
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--fg-muted, #888)" }}>
      그래프 초기화 중…
    </div>
  ),
});

// Entity type → hue (HSL)
const TYPE_HUES: Record<string, number> = {
  person: 210,
  organization: 150,
  org: 150,
  place: 40,
  location: 40,
  event: 280,
  concept: 320,
  product: 15,
  law: 180,
  unknown: 0,
};

function typeColor(entityType: string): string {
  const type = entityType.toLowerCase();
  const hue = TYPE_HUES[type] ?? ((entityType.charCodeAt(0) * 47) % 360);
  return `hsl(${hue}, 65%, 55%)`;
}

interface GraphData {
  nodes: { id: number; name: string; entity_type: string; description: string; degree: number; chunk_count: number; [k: string]: unknown }[];
  links: { id: number; source: number; target: number; description: string; keywords: string[]; weight: number }[];
}

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeId: number | null;
  onNodeClick: (node: GraphNode) => void;
  width: number;
  height: number;
}

export default function GraphCanvas({ nodes, edges, selectedNodeId, onNodeClick, width, height }: Props) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<ForceGraphMethods<any, any>>(undefined);

  const data: GraphData = useMemo(() => ({
    nodes: nodes.map((n) => ({ ...n })),
    links: edges.map((e) => ({ ...e })),
  }), [nodes, edges]);

  // Center on selected node when it changes
  useEffect(() => {
    if (selectedNodeId == null || !graphRef.current) return;
    const node = data.nodes.find((n) => n.id === selectedNodeId);
    if (node && "x" in node && "y" in node) {
      graphRef.current.centerAt(node.x as number, node.y as number, 400);
      graphRef.current.zoom(2.5, 400);
    }
  }, [selectedNodeId, data.nodes]); // eslint-disable-line react-hooks/exhaustive-deps

  const nodeCanvasObject = useCallback(
    (
      node: { id: number; name: string; entity_type: string; degree: number; x?: number; y?: number },
      ctx: CanvasRenderingContext2D,
      globalScale: number
    ) => {
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const baseR = Math.max(4, Math.min(12, 4 + Math.sqrt(node.degree) * 1.5));
      const r = node.id === selectedNodeId ? baseR * 1.4 : baseR;
      const color = typeColor(node.entity_type);

      // Node circle
      ctx.beginPath();
      ctx.arc(x, y, r, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();

      if (node.id === selectedNodeId) {
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2 / globalScale;
        ctx.stroke();
      }

      // Label (only when zoomed in enough)
      const fontSize = Math.max(8, 11 / globalScale);
      if (globalScale > 0.6) {
        ctx.font = `${fontSize}px system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = "#fff";
        ctx.fillText(node.name.length > 20 ? node.name.slice(0, 18) + "…" : node.name, x, y + r + 2 / globalScale);
      }
    },
    [selectedNodeId]
  );

  const linkWidth = useCallback(
    (link: { weight?: number }) => Math.max(0.5, (link.weight ?? 1) * 1.5),
    []
  );

  const handleNodeClick = useCallback(
    (node: Record<string, unknown>) => {
      onNodeClick(node as unknown as GraphNode);
    },
    [onNodeClick]
  );

  return (
    <ForceGraph2D
      ref={graphRef}
      graphData={data}
      width={width}
      height={height}
      nodeId="id"
      linkSource="source"
      linkTarget="target"
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      nodeCanvasObject={nodeCanvasObject as any}
      nodeCanvasObjectMode={() => "replace"}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      linkWidth={linkWidth as any}
      linkColor={() => "rgba(150,150,180,0.4)"}
      linkDirectionalArrowLength={4}
      linkDirectionalArrowRelPos={1}
      onNodeClick={handleNodeClick}
      cooldownTicks={120}
      d3AlphaDecay={0.02}
      d3VelocityDecay={0.3}
    />
  );
}
