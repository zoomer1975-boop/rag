"use client";

import { useState, useEffect } from "react";
import { adminFetch, type SubAdmin, type Tenant } from "@/lib/api";
import styles from "./SubAdminManager.module.css";

interface SubAdminManagerProps {
  onBack: () => void;
  onSubAdminsUpdated: () => void;
}

export default function SubAdminManager({
  onBack,
  onSubAdminsUpdated,
}: SubAdminManagerProps) {
  const [subAdmins, setSubAdmins] = useState<SubAdmin[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    username: "",
    password: "",
    allowed_ips: "",
    tenant_ids: [] as number[],
  });
  const [editingId, setEditingId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  // 부관리자 목록 불러오기
  const loadSubAdmins = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await adminFetch<SubAdmin[]>("/admin/sub-admins");
      setSubAdmins(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  // 테넌트 목록 불러오기
  const loadTenants = async () => {
    try {
      const data = await adminFetch<Tenant[]>("/tenants/");
      setTenants(data);
    } catch (e) {
      console.error("테넌트 목록 불러오기 실패:", e);
    }
  };

  useEffect(() => {
    loadSubAdmins();
    loadTenants();
  }, []);

  // 폼 초기화
  const resetForm = () => {
    setFormData({
      name: "",
      username: "",
      password: "",
      allowed_ips: "",
      tenant_ids: [],
    });
    setEditingId(null);
    setShowForm(false);
  };

  // 생성/수정
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      if (editingId) {
        // 수정: 비밀번호가 있으면 포함, 없으면 제외
        const updateData: any = {
          name: formData.name,
          allowed_ips: formData.allowed_ips,
          tenant_ids: formData.tenant_ids,
        };
        if (formData.password) {
          updateData.password = formData.password;
        }
        await adminFetch(`/admin/sub-admins/${editingId}`, {
          method: "PATCH",
          body: JSON.stringify(updateData),
        });
      } else {
        // 생성
        await adminFetch("/admin/sub-admins", {
          method: "POST",
          body: JSON.stringify(formData),
        });
      }
      resetForm();
      loadSubAdmins();
      onSubAdminsUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  // 삭제
  const handleDelete = async (id: number) => {
    if (!confirm("정말 삭제하시겠습니까?")) return;
    setDeleting(id);
    setError("");
    try {
      await adminFetch(`/admin/sub-admins/${id}`, { method: "DELETE" });
      loadSubAdmins();
      onSubAdminsUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "오류가 발생했습니다.");
    } finally {
      setDeleting(null);
    }
  };

  // 수정 모드로 변경
  const handleEdit = (sub: SubAdmin) => {
    setFormData({
      name: sub.name,
      username: sub.username,
      password: "",
      allowed_ips: sub.allowed_ips,
      tenant_ids: sub.tenant_ids,
    });
    setEditingId(sub.id);
    setShowForm(true);
  };

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h1 className={styles.title}>부관리자 관리</h1>
        <button className={styles.btnBack} onClick={onBack}>
          ← 돌아가기
        </button>
      </div>

      <div className={styles.panel}>
        <div className={styles.actions}>
          <button
            className={styles.btnPrimary}
            onClick={() => setShowForm(!showForm)}
            disabled={loading}
          >
            {showForm ? "취소" : "새 부관리자 추가"}
          </button>
        </div>

        {error && <p className={styles.error}>{error}</p>}

        {showForm && (
          <form onSubmit={handleSubmit} className={styles.form}>
            <fieldset>
              <legend>{editingId ? "부관리자 수정" : "부관리자 추가"}</legend>

              <div className={styles.formGroup}>
                <label htmlFor="name">이름</label>
                <input
                  id="name"
                  type="text"
                  value={formData.name}
                  onChange={(e) =>
                    setFormData({ ...formData, name: e.target.value })
                  }
                  required
                  disabled={loading || editingId !== null}
                />
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="username">아이디</label>
                <input
                  id="username"
                  type="text"
                  value={formData.username}
                  onChange={(e) =>
                    setFormData({ ...formData, username: e.target.value })
                  }
                  required
                  disabled={loading || editingId !== null}
                />
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="password">
                  {editingId ? "비밀번호 (변경할 경우만)" : "비밀번호"}
                </label>
                <input
                  id="password"
                  type="password"
                  value={formData.password}
                  onChange={(e) =>
                    setFormData({ ...formData, password: e.target.value })
                  }
                  required={!editingId}
                  minLength={8}
                  disabled={loading}
                />
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="allowed_ips">
                  허용 IP (공백 = 모두 허용, 쉼표로 구분)
                </label>
                <input
                  id="allowed_ips"
                  type="text"
                  value={formData.allowed_ips}
                  onChange={(e) =>
                    setFormData({ ...formData, allowed_ips: e.target.value })
                  }
                  placeholder="192.168.1.100, 10.0.0.0/8"
                  disabled={loading}
                />
              </div>

              <div className={styles.formGroup}>
                <label>할당 테넌트</label>
                <div className={styles.checkboxGroup}>
                  {tenants.map((tenant) => (
                    <label key={tenant.id} className={styles.checkbox}>
                      <input
                        type="checkbox"
                        checked={formData.tenant_ids.includes(tenant.id)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setFormData({
                              ...formData,
                              tenant_ids: [
                                ...formData.tenant_ids,
                                tenant.id,
                              ],
                            });
                          } else {
                            setFormData({
                              ...formData,
                              tenant_ids: formData.tenant_ids.filter(
                                (id) => id !== tenant.id
                              ),
                            });
                          }
                        }}
                        disabled={loading}
                      />
                      {tenant.name}
                    </label>
                  ))}
                </div>
              </div>

              <div className={styles.formActions}>
                <button
                  type="submit"
                  className={styles.btnPrimary}
                  disabled={loading}
                >
                  {loading ? "저장 중…" : editingId ? "수정" : "추가"}
                </button>
                <button
                  type="button"
                  className={styles.btnSecondary}
                  onClick={resetForm}
                  disabled={loading}
                >
                  취소
                </button>
              </div>
            </fieldset>
          </form>
        )}

        <div className={styles.list}>
          {subAdmins.length === 0 && !loading && (
            <p className={styles.empty}>부관리자가 없습니다.</p>
          )}
          {subAdmins.map((sub) => (
            <div key={sub.id} className={styles.item}>
              <div className={styles.itemInfo}>
                <h3>{sub.name}</h3>
                <p className={styles.meta}>
                  아이디: <code>{sub.username}</code>
                </p>
                <p className={styles.meta}>
                  할당 테넌트:{" "}
                  {sub.tenant_ids.length === 0
                    ? "없음"
                    : tenants
                        .filter((t) => sub.tenant_ids.includes(t.id))
                        .map((t) => t.name)
                        .join(", ")}
                </p>
                {sub.allowed_ips && (
                  <p className={styles.meta}>
                    허용 IP: <code>{sub.allowed_ips}</code>
                  </p>
                )}
                <span
                  className={`${styles.badge} ${
                    sub.is_active ? styles.badgeGreen : styles.badgeRed
                  }`}
                >
                  {sub.is_active ? "활성" : "비활성"}
                </span>
              </div>
              <div className={styles.itemActions}>
                <button
                  className={styles.btnSecondary}
                  onClick={() => handleEdit(sub)}
                  disabled={loading || deleting === sub.id}
                >
                  수정
                </button>
                <button
                  className={styles.btnDanger}
                  onClick={() => handleDelete(sub.id)}
                  disabled={deleting === sub.id || loading}
                >
                  {deleting === sub.id ? "삭제 중…" : "삭제"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
