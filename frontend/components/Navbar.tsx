"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import api, { type UserProfile } from "@/lib/api";

export default function Navbar() {
  const [user, setUser] = useState<UserProfile | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) return;
    api.get<UserProfile>("/users/me").then((r) => setUser(r.data)).catch(() => {});
  }, []);

  function logout() {
    localStorage.removeItem("token");
    setUser(null);
    window.location.href = "/";
  }

  return (
    <nav dir="ltr" className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-6">
      <Link href="/" className="font-bold text-xl text-indigo-600">
        Reco
      </Link>
      <Link href="/restaurants" className="text-sm font-medium text-gray-600 hover:text-gray-900">
        מסעדות
      </Link>
      <div className="flex-1" />
      {user ? (
        <div className="flex items-center gap-4">
          <Link href="/profile" className="text-sm font-medium">
            {user.username}{" "}
            <span className="text-indigo-600 font-bold">{user.points_balance} נקודות</span>
          </Link>
          <button onClick={logout} className="text-sm text-gray-500 hover:text-gray-800">
            התנתק
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <Link href="/login" className="text-sm font-medium text-gray-600 hover:text-gray-900">
            התחברות
          </Link>
          <Link
            href="/register"
            className="text-sm font-medium bg-indigo-600 text-white px-3 py-1.5 rounded-lg hover:bg-indigo-700"
          >
            הרשמה
          </Link>
        </div>
      )}
    </nav>
  );
}
