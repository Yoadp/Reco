"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Bell } from "@phosphor-icons/react";
import api, { type UserProfile, getPendingVisits, type UserVisit } from "@/lib/api";

export default function Navbar() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [pendingVisits, setPendingVisits] = useState<UserVisit[]>([]);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) return;
    api.get<UserProfile>("/users/me").then((r) => setUser(r.data)).catch(() => {});
    getPendingVisits().then(setPendingVisits).catch(() => {});
  }, []);

  function logout() {
    localStorage.removeItem("token");
    setUser(null);
    window.location.href = "/";
  }

  return (
    <nav
      dir="ltr"
      className="sticky top-0 z-40 flex items-center gap-6 px-5 py-0 h-14"
      style={{
        background: "rgba(249,247,244,0.92)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <Link href="/" className="font-bold text-lg tracking-tight" style={{ color: "var(--accent)" }}>
        Reco
      </Link>
      <Link
        href="/restaurants"
        className="text-sm font-medium transition-colors"
        style={{ color: "var(--text-muted)" }}
        onMouseEnter={e => (e.currentTarget.style.color = "var(--text)")}
        onMouseLeave={e => (e.currentTarget.style.color = "var(--text-muted)")}
      >
        מסעדות
      </Link>

      <div className="flex-1" />

      {user ? (
        <div className="flex items-center gap-4">
          <Link href="/profile" className="flex items-center gap-2 text-sm font-medium relative" style={{ color: "var(--text)" }}>
            {user.username}
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full" style={{ background: "var(--accent-light)", color: "var(--accent)" }}>
              {user.points_balance} נק׳
            </span>
            {pendingVisits.length > 0 && (
              <Bell size={14} weight="fill" className="text-red-500" aria-label="יש דירוגים ממתינים" />
            )}
          </Link>
          <button
            onClick={logout}
            className="text-sm transition-colors"
            style={{ color: "var(--text-faint)" }}
            onMouseEnter={e => (e.currentTarget.style.color = "var(--text)")}
            onMouseLeave={e => (e.currentTarget.style.color = "var(--text-faint)")}
          >
            התנתק
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="text-sm font-medium transition-colors"
            style={{ color: "var(--text-muted)" }}
            onMouseEnter={e => (e.currentTarget.style.color = "var(--text)")}
            onMouseLeave={e => (e.currentTarget.style.color = "var(--text-muted)")}
          >
            התחברות
          </Link>
          <Link
            href="/register"
            className="text-sm font-semibold px-4 py-1.5 rounded-full transition-all active:scale-[0.97]"
            style={{ background: "var(--accent)", color: "#fff" }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--accent-dark)")}
            onMouseLeave={e => (e.currentTarget.style.background = "var(--accent)")}
          >
            הרשמה
          </Link>
        </div>
      )}
    </nav>
  );
}
