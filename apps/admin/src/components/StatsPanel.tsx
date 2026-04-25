"use client";

import { useEffect, useState } from "react";
import { apiFetch, type DailyUsage, type LanguageBreakdown, type Stats } from "@/lib/api";
import styles from "./StatsPanel.module.css";

interface AllStats {
  stats: Stats;
  daily: DailyUsage[];
  langs: LanguageBreakdown[];
}

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString();
}

function fmtMs(ms: number | null): string {
  if (ms == null) return "—";
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function DailyChart({ data }: { data: DailyUsage[] }) {
  if (!data.length) return <p className={styles.empty}>데이터 없음</p>;

  const W = 600;
  const H = 110;
  const PAD = { top: 8, right: 8, bottom: 28, left: 40 };
  const chartW = W - PAD.left - PAD.right;
  const chartH = H - PAD.top - PAD.bottom;

  const maxCalls = Math.max(...data.map((d) => d.call_count), 1);
  const maxTokens = Math.max(...data.map((d) => d.input_tokens + d.output_tokens), 1);

  const barW = Math.max(2, (chartW / data.length) * 0.6);
  const gap = chartW / data.length;

  const tokenPoints = data
    .map((d, i) => {
      const x = PAD.left + i * gap + gap / 2;
      const y = PAD.top + chartH - (d.input_tokens + d.output_tokens) / maxTokens * chartH;
      return `${x},${y}`;
    })
    .join(" ");

  const yLabels = [0, Math.round(maxCalls / 2), maxCalls];

  const showEveryNth = Math.ceil(data.length / 8);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={styles.chart} aria-label="일별 호출 추이">
      {/* y-axis grid + labels */}
      {yLabels.map((v) => {
        const y = PAD.top + chartH - (v / maxCalls) * chartH;
        return (
          <g key={v}>
            <line x1={PAD.left} y1={y} x2={PAD.left + chartW} y2={y} className={styles.gridLine} />
            <text x={PAD.left - 4} y={y + 4} className={styles.axisLabel} textAnchor="end">
              {v}
            </text>
          </g>
        );
      })}

      {/* bars */}
      {data.map((d, i) => {
        const x = PAD.left + i * gap + gap / 2 - barW / 2;
        const barH = Math.max(1, (d.call_count / maxCalls) * chartH);
        const y = PAD.top + chartH - barH;
        return (
          <rect key={i} x={x} y={y} width={barW} height={barH} className={styles.bar}>
            <title>{`${d.date}: ${d.call_count}건`}</title>
          </rect>
        );
      })}

      {/* token line */}
      {maxTokens > 0 && (
        <polyline points={tokenPoints} className={styles.tokenLine} fill="none" />
      )}

      {/* x-axis labels */}
      {data.map((d, i) => {
        if (i % showEveryNth !== 0) return null;
        const x = PAD.left + i * gap + gap / 2;
        const label = d.date.slice(5); // MM-DD
        return (
          <text key={i} x={x} y={H - 4} className={styles.axisLabel} textAnchor="middle">
            {label}
          </text>
        );
      })}
    </svg>
  );
}

function LangBars({ data }: { data: LanguageBreakdown[] }) {
  if (!data.length) return <p className={styles.empty}>데이터 없음</p>;
  const total = data.reduce((s, d) => s + d.count, 0);
  return (
    <div className={styles.langList}>
      {data.map((d) => {
        const pct = total ? Math.round((d.count / total) * 100) : 0;
        return (
          <div key={d.lang_code} className={styles.langRow}>
            <span className={styles.langCode}>{d.lang_code}</span>
            <div className={styles.langBarTrack}>
              <div className={styles.langBar} style={{ width: `${pct}%` }} />
            </div>
            <span className={styles.langCount}>{d.count.toLocaleString()} ({pct}%)</span>
          </div>
        );
      })}
    </div>
  );
}

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

function daysAgoStr(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export default function StatsPanel({ apiKey }: { apiKey: string }) {
  const [data, setData] = useState<AllStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    const qs = new URLSearchParams();
    if (startDate) qs.set("start_date", startDate);
    if (endDate) qs.set("end_date", endDate);
    const q = qs.toString() ? `?${qs.toString()}` : "";

    Promise.all([
      apiFetch<Stats>(`/analytics/stats${q}`, apiKey),
      apiFetch<DailyUsage[]>(`/analytics/daily-usage${q}`, apiKey),
      apiFetch<LanguageBreakdown[]>(`/analytics/language-breakdown${q}`, apiKey),
    ])
      .then(([stats, daily, langs]) => setData({ stats, daily, langs }))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [apiKey, startDate, endDate]);

  const presets = [
    { label: "오늘", onClick: () => { setStartDate(todayStr()); setEndDate(todayStr()); } },
    { label: "7일", onClick: () => { setStartDate(daysAgoStr(6)); setEndDate(todayStr()); } },
    { label: "30일", onClick: () => { setStartDate(daysAgoStr(29)); setEndDate(todayStr()); } },
    { label: "90일", onClick: () => { setStartDate(daysAgoStr(89)); setEndDate(todayStr()); } },
    { label: "전체", onClick: () => { setStartDate(""); setEndDate(""); } },
  ];

  const chartLabel = startDate || endDate
    ? `${startDate || "…"} ~ ${endDate || "…"}`
    : "전체 기간";

  if (loading) return <p className={styles.loading}>불러오는 중…</p>;
  if (error) return <p className={styles.error}>{error}</p>;
  if (!data) return null;

  const { stats, daily, langs } = data;

  const topCards = [
    { label: "대화", value: fmt(stats.conversation_count), unit: "건" },
    { label: "메시지", value: fmt(stats.message_count), unit: "개" },
    { label: "입력 토큰", value: fmt(stats.total_input_tokens), unit: "" },
    { label: "출력 토큰", value: fmt(stats.total_output_tokens), unit: "" },
    { label: "평균 응답", value: fmtMs(stats.avg_latency_ms), unit: "" },
    { label: "대화당 메시지", value: String(stats.avg_messages_per_conversation), unit: "개" },
  ];

  return (
    <div className={styles.root}>
      <h2 className={styles.heading}>현황 통계</h2>

      <div className={styles.dateBar}>
        <div className={styles.presets}>
          {presets.map(({ label, onClick }) => (
            <button key={label} className={styles.presetBtn} onClick={onClick} type="button">
              {label}
            </button>
          ))}
        </div>
        <div className={styles.dateInputs}>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className={styles.dateInput}
            aria-label="시작일"
          />
          <span className={styles.dateSep}>~</span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className={styles.dateInput}
            aria-label="종료일"
          />
        </div>
      </div>

      <div className={styles.grid}>
        {topCards.map(({ label, value, unit }) => (
          <div key={label} className={styles.card}>
            <span className={styles.value}>{value}</span>
            {unit && <span className={styles.unit}>{unit}</span>}
            <span className={styles.label}>{label}</span>
          </div>
        ))}
      </div>

      <div className={styles.grid2}>
        <section className={styles.section}>
          <h3 className={styles.subheading}>일별 호출 추이 ({chartLabel})</h3>
          <div className={styles.legend}>
            <span className={styles.legendBar}>■</span> 호출 수
            <span className={styles.legendLine}>—</span> 토큰 합계
          </div>
          <DailyChart data={daily} />
        </section>

        <section className={styles.section}>
          <h3 className={styles.subheading}>언어별 분포</h3>
          <LangBars data={langs} />
        </section>
      </div>

      <div className={styles.subGrid}>
        <div className={styles.card}>
          <span className={styles.value}>{fmt(stats.document_count)}</span>
          <span className={styles.unit}>개</span>
          <span className={styles.label}>문서</span>
        </div>
        <div className={styles.card}>
          <span className={styles.value}>{fmt(stats.chunk_count)}</span>
          <span className={styles.unit}>개</span>
          <span className={styles.label}>청크</span>
        </div>
      </div>
    </div>
  );
}
