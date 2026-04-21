"use client";

import { useEffect, useState } from "react";
import {
  type BoilerplatePattern,
  type BoilerplatePatternCreate,
  createBoilerplatePattern,
  deleteBoilerplatePattern,
  listBoilerplatePatterns,
  previewBoilerplatePatterns,
  updateBoilerplatePattern,
} from "@/lib/api";
import styles from "./BoilerplatePanel.module.css";

interface Props {
  tenantId: number;
}

const EMPTY_FORM: BoilerplatePatternCreate = {
  pattern_type: "literal",
  pattern: "",
  description: "",
  is_active: true,
  sort_order: 0,
};

export default function BoilerplatePanel({ tenantId }: Props) {
  const [patterns, setPatterns] = useState<BoilerplatePattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<BoilerplatePatternCreate>({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Preview state
  const [previewText, setPreviewText] = useState("");
  const [previewResult, setPreviewResult] = useState<{
    original: string;
    applied: string;
    removed_count: number;
  } | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listBoilerplatePatterns(tenantId);
      setPatterns(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "로드 실패");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [tenantId]); // eslint-disable-line react-hooks/exhaustive-deps

  function openCreate() {
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
    setFormError(null);
    setShowForm(true);
  }

  function openEdit(p: BoilerplatePattern) {
    setEditingId(p.id);
    setForm({
      pattern_type: p.pattern_type,
      pattern: p.pattern,
      description: p.description ?? "",
      is_active: p.is_active,
      sort_order: p.sort_order,
    });
    setFormError(null);
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditingId(null);
    setFormError(null);
  }

  async function handleSave() {
    if (!form.pattern.trim()) {
      setFormError("패턴을 입력하세요.");
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      if (editingId !== null) {
        await updateBoilerplatePattern(tenantId, editingId, {
          pattern_type: form.pattern_type,
          pattern: form.pattern.trim(),
          description: form.description || null,
          is_active: form.is_active,
          sort_order: form.sort_order,
        });
      } else {
        await createBoilerplatePattern(tenantId, {
          ...form,
          pattern: form.pattern.trim(),
          description: form.description || undefined,
        });
      }
      closeForm();
      await load();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(p: BoilerplatePattern) {
    try {
      const updated = await updateBoilerplatePattern(tenantId, p.id, { is_active: !p.is_active });
      setPatterns((prev) => prev.map((x) => (x.id === p.id ? updated : x)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "수정 실패");
    }
  }

  async function handleDelete(p: BoilerplatePattern) {
    if (!confirm(`"${p.pattern}" 패턴을 삭제하시겠습니까?`)) return;
    try {
      await deleteBoilerplatePattern(tenantId, p.id);
      setPatterns((prev) => prev.filter((x) => x.id !== p.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "삭제 실패");
    }
  }

  async function handlePreview() {
    if (!previewText.trim()) return;
    setPreviewing(true);
    setPreviewError(null);
    try {
      const result = await previewBoilerplatePatterns(tenantId, previewText);
      setPreviewResult(result);
    } catch (e) {
      setPreviewError(e instanceof Error ? e.message : "미리보기 실패");
    } finally {
      setPreviewing(false);
    }
  }

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <span className={styles.heading}>상용문구 제거 패턴</span>
        <button className={styles.btnPrimary} onClick={openCreate}>
          + 패턴 추가
        </button>
      </div>

      {error && <p className={styles.errorMsg}>{error}</p>}

      {/* ── Form ── */}
      {showForm && (
        <div className={styles.formBox}>
          <p className={styles.formTitle}>{editingId !== null ? "패턴 수정" : "새 패턴 추가"}</p>

          <div className={styles.row2}>
            <div className={styles.field}>
              <label className={styles.label}>유형</label>
              <select
                className={styles.select}
                value={form.pattern_type}
                onChange={(e) =>
                  setForm((f) => ({ ...f, pattern_type: e.target.value as "literal" | "regex" }))
                }
              >
                <option value="literal">단순 문자열 (literal)</option>
                <option value="regex">정규식 (regex)</option>
              </select>
            </div>
            <div className={styles.field}>
              <label className={styles.label}>정렬 순서</label>
              <input
                type="number"
                className={styles.input}
                value={form.sort_order}
                onChange={(e) => setForm((f) => ({ ...f, sort_order: Number(e.target.value) }))}
              />
            </div>
          </div>

          <div className={styles.field}>
            <label className={styles.label}>패턴 *</label>
            <textarea
              className={styles.textarea}
              rows={3}
              placeholder={
                form.pattern_type === "literal"
                  ? "제거할 문자열을 입력하세요"
                  : "정규식을 입력하세요 (예: \\s*Copyright.*\\n)"
              }
              value={form.pattern}
              onChange={(e) => setForm((f) => ({ ...f, pattern: e.target.value }))}
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label}>설명 (선택)</label>
            <input
              type="text"
              className={styles.input}
              placeholder="이 패턴의 용도를 간략히 적어주세요"
              value={form.description ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>

          <div className={styles.field}>
            <label className={styles.checkLabel}>
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
              />
              활성화
            </label>
          </div>

          {formError && <p className={styles.errorMsg}>{formError}</p>}

          <div className={styles.formFooter}>
            <button className={styles.btnPrimary} onClick={handleSave} disabled={saving}>
              {saving ? "저장 중…" : "저장"}
            </button>
            <button className={styles.btnSecondary} onClick={closeForm} disabled={saving}>
              취소
            </button>
          </div>
        </div>
      )}

      {/* ── Pattern list ── */}
      {loading ? (
        <p className={styles.empty}>로딩 중…</p>
      ) : patterns.length === 0 ? (
        <p className={styles.empty}>등록된 패턴이 없습니다.</p>
      ) : (
        <div className={styles.patternList}>
          {patterns.map((p) => (
            <div key={p.id} className={`${styles.patternCard} ${!p.is_active ? styles.inactive : ""}`}>
              <div className={styles.patternMain}>
                <div className={styles.patternTopRow}>
                  <span className={`${styles.typeBadge} ${styles[p.pattern_type]}`}>
                    {p.pattern_type}
                  </span>
                  {!p.is_active && <span className={styles.inactiveBadge}>비활성</span>}
                  {p.description && (
                    <span className={styles.patternDesc}>{p.description}</span>
                  )}
                </div>
                <code className={styles.patternValue}>{p.pattern}</code>
              </div>
              <div className={styles.patternActions}>
                <button
                  className={styles.btnSecondary}
                  onClick={() => handleToggle(p)}
                  title={p.is_active ? "비활성화" : "활성화"}
                >
                  {p.is_active ? "끄기" : "켜기"}
                </button>
                <button className={styles.btnSecondary} onClick={() => openEdit(p)}>
                  수정
                </button>
                <button className={styles.btnDanger} onClick={() => handleDelete(p)}>
                  삭제
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Preview ── */}
      <div className={styles.previewBox}>
        <p className={styles.formTitle}>미리보기</p>
        <p className={styles.hint}>
          현재 저장된 활성 패턴 기준으로 샘플 텍스트에 적용한 결과를 확인합니다.
        </p>
        <textarea
          className={styles.textarea}
          rows={6}
          placeholder="샘플 텍스트를 붙여넣으세요…"
          value={previewText}
          onChange={(e) => {
            setPreviewText(e.target.value);
            setPreviewResult(null);
          }}
        />
        <div className={styles.previewFooter}>
          <button
            className={styles.btnSecondary}
            onClick={handlePreview}
            disabled={previewing || !previewText.trim()}
          >
            {previewing ? "적용 중…" : "패턴 적용"}
          </button>
          {previewResult && (
            <span className={styles.previewStat}>
              {previewResult.removed_count}개 패턴 매칭
            </span>
          )}
        </div>
        {previewError && <p className={styles.errorMsg}>{previewError}</p>}
        {previewResult && (
          <div className={styles.previewResult}>
            <p className={styles.previewLabel}>적용 결과:</p>
            <pre className={styles.previewPre}>{previewResult.applied || "(비어 있음)"}</pre>
          </div>
        )}
      </div>
    </div>
  );
}
