"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchGraph,
  fetchGraphSummary,
  fetchNeighborhood,
  type GraphEdge,
  type GraphNode,
  type GraphPayload,
  type GraphSummary,
} from "@/lib/api";
import GraphCanvas from "./GraphCanvas";
import styles from "./GraphPanel.module.css";

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

type Mode = "full" | "neighborhood";

const CANVAS_HEIGHT = 520;

export default function GraphPanel({ apiKey }: { apiKey: string }) {
  const [summary, setSummary] = useState<GraphSummary | null>(null);
  const [payload, setPayload] = useState<GraphPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [mode, setMode] = useState<Mode>("full");
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [nameQuery, setNameQuery] = useState("");
  const [depth, setDepth] = useState(1);
  const [focusedNode, setFocusedNode] = useState<GraphNode | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  const canvasRef = useRef<HTMLDivElement>(null);
  const [canvasWidth, setCanvasWidth] = useState(600);

  // Measure canvas container width
  useEffect(() => {
    if (!canvasRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setCanvasWidth(w);
    });
    ro.observe(canvasRef.current);
    return () => ro.disconnect();
  }, []);

  // Load summary on mount
  useEffect(() => {
    fetchGraphSummary(apiKey)
      .then(setSummary)
      .catch(() => setSummary(null));
  }, [apiKey]);

  const loadFull = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchGraph(apiKey, {
        types: selectedTypes.length ? selectedTypes : undefined,
        q: nameQuery.trim() || undefined,
      });
      setPayload(data);
      setMode("full");
      setFocusedNode(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "알 수 없는 오류");
    } finally {
      setLoading(false);
    }
  }, [apiKey, selectedTypes, nameQuery]);

  const loadNeighborhood = useCallback(
    async (node: GraphNode) => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchNeighborhood(apiKey, node.id, { depth });
        setPayload(data);
        setMode("neighborhood");
        setFocusedNode(node);
      } catch (e) {
        setError(e instanceof Error ? e.message : "알 수 없는 오류");
      } finally {
        setLoading(false);
      }
    },
    [apiKey, depth]
  );

  // Initial load
  useEffect(() => {
    loadFull();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function toggleType(type: string) {
    setSelectedTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  }

  function handleReset() {
    setSelectedTypes([]);
    setNameQuery("");
    setMode("full");
    setFocusedNode(null);
    setSelectedNode(null);
  }

  const entityTypes = useMemo(
    () => summary?.entity_types.map((t) => t.type) ?? [],
    [summary]
  );

  const hasGraph = payload && (payload.nodes.length > 0 || payload.edges.length > 0);

  return (
    <div className={styles.root}>
      <h2 className={styles.heading}>엔티티 관계 그래프</h2>

      {/* Summary */}
      {summary && (
        <div className={styles.summaryBar}>
          <div className={styles.summaryCard}>
            <span className={styles.summaryValue}>{summary.entity_count.toLocaleString()}</span>
            <span className={styles.summaryLabel}>엔티티</span>
          </div>
          <div className={styles.summaryCard}>
            <span className={styles.summaryValue}>{summary.relationship_count.toLocaleString()}</span>
            <span className={styles.summaryLabel}>관계</span>
          </div>
          {mode === "neighborhood" && focusedNode && (
            <span className={styles.summaryLabel} style={{ alignSelf: "center" }}>
              📍 {focusedNode.name} 중심 {depth}-hop 그래프
            </span>
          )}
          {payload?.truncated && (
            <span className={styles.truncatedWarning}>
              ⚠ 결과가 너무 많아 일부만 표시됩니다. 필터를 사용해 범위를 좁혀보세요.
            </span>
          )}
        </div>
      )}

      {/* Controls */}
      <div className={styles.controls}>
        <div className={styles.controlGroup}>
          <span className={styles.controlLabel}>이름 검색</span>
          <input
            className={styles.searchInput}
            type="search"
            placeholder="엔티티 이름으로 검색…"
            value={nameQuery}
            onChange={(e) => setNameQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && loadFull()}
          />
        </div>

        {entityTypes.length > 0 && (
          <div className={styles.controlGroup}>
            <span className={styles.controlLabel}>타입 필터</span>
            <div className={styles.typeChips}>
              {entityTypes.map((type) => (
                <button
                  key={type}
                  className={`${styles.typeChip} ${selectedTypes.includes(type) ? styles.typeChipActive : ""}`}
                  onClick={() => toggleType(type)}
                  style={
                    selectedTypes.includes(type)
                      ? { background: typeColor(type), borderColor: typeColor(type) }
                      : {}
                  }
                >
                  {type}
                </button>
              ))}
            </div>
          </div>
        )}

        {mode === "neighborhood" && (
          <div className={styles.controlGroup}>
            <span className={styles.controlLabel}>탐색 depth</span>
            <select
              className={styles.depthSelect}
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
            >
              <option value={1}>1-hop</option>
              <option value={2}>2-hop</option>
            </select>
          </div>
        )}

        <button className={styles.btnGhost} onClick={loadFull} disabled={loading}>
          {loading ? "불러오는 중…" : "적용"}
        </button>
        <button className={styles.btnReset} onClick={handleReset} disabled={loading}>
          초기화
        </button>
      </div>

      {error && (
        <p className={styles.muted} style={{ color: "#ef4444", marginBottom: 8 }}>
          오류: {error}
        </p>
      )}

      {/* Main area */}
      <div className={styles.mainArea}>
        <div className={styles.canvasWrap} ref={canvasRef}>
          {loading ? (
            <div className={styles.canvasPlaceholder}>
              <span>그래프 불러오는 중…</span>
            </div>
          ) : !hasGraph ? (
            <div className={styles.canvasPlaceholder}>
              <span className={styles.canvasPlaceholderIcon}>🕸</span>
              <span>표시할 엔티티가 없습니다.</span>
              <span style={{ fontSize: 11 }}>문서를 인제스트하면 엔티티가 추출됩니다.</span>
            </div>
          ) : (
            <GraphCanvas
              nodes={payload!.nodes}
              edges={payload!.edges}
              selectedNodeId={selectedNode?.id ?? null}
              onNodeClick={(node) => setSelectedNode(node)}
              width={canvasWidth}
              height={CANVAS_HEIGHT}
            />
          )}
        </div>

        {/* Side panel */}
        <div className={styles.sidePanel}>
          {selectedNode ? (
            <div className={styles.nodePanelCard}>
              <div>
                <span
                  className={styles.nodeTypeBadge}
                  style={{
                    background: typeColor(selectedNode.entity_type) + "30",
                    color: typeColor(selectedNode.entity_type),
                  }}
                >
                  {selectedNode.entity_type}
                </span>
              </div>
              <p className={styles.nodePanelTitle}>{selectedNode.name}</p>

              <div className={styles.nodeMeta}>
                <div className={styles.nodeMetaRow}>
                  <span>연결 수</span>
                  <span className={styles.nodeMetaValue}>{selectedNode.degree}</span>
                </div>
                <div className={styles.nodeMetaRow}>
                  <span>청크 수</span>
                  <span className={styles.nodeMetaValue}>{selectedNode.chunk_count}</span>
                </div>
              </div>

              {selectedNode.description && (
                <p className={styles.nodeDescription}>{selectedNode.description}</p>
              )}

              <button
                className={styles.btnFocus}
                onClick={() => loadNeighborhood(selectedNode)}
                disabled={loading}
              >
                이 노드 중심으로 보기
              </button>
            </div>
          ) : (
            <div className={styles.nodePanelCard}>
              <p className={styles.muted} style={{ fontSize: 12 }}>
                노드를 클릭하면 상세 정보가 표시됩니다.
              </p>
            </div>
          )}

          {/* Legend */}
          {entityTypes.length > 0 && (
            <div className={styles.legendCard}>
              <p className={styles.legendTitle}>범례</p>
              <div className={styles.legendItems}>
                {entityTypes.slice(0, 8).map((type) => (
                  <div key={type} className={styles.legendItem}>
                    <span
                      className={styles.legendDot}
                      style={{ background: typeColor(type) }}
                    />
                    {type}
                  </div>
                ))}
                {entityTypes.length > 8 && (
                  <span className={styles.muted} style={{ fontSize: 11 }}>
                    +{entityTypes.length - 8}개 더
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
