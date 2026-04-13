"use client";

interface Props {
  className: string;
}

export default function LogoutButton({ className }: Props) {
  async function logout() {
    await fetch("/rag/admin/api/auth/logout", { method: "POST" });
    window.location.href = "/rag/admin/login";
  }
  return (
    <button className={className} onClick={logout}>
      로그아웃
    </button>
  );
}
