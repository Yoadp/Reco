"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import api, { getMe } from "@/lib/api";

const TIER_COLORS = {
  bronze: "text-amber-700 bg-amber-50",
  silver: "text-slate-600 bg-slate-100",
  gold: "text-yellow-600 bg-yellow-50",
};

const TIER_LABELS: Record<string, string> = {
  bronze: "ברונזה",
  silver: "כסף",
  gold: "זהב",
};

const REASON_LABELS: Record<string, string> = {
  community_approved: "אושר על ידי הקהילה",
  moderator_approved: "אושר על ידי מנהל",
  first_rec: "המלצה ראשונה במקום",
  inaccurate: "המלצה לא מדויקת",
  spam: "ספאם",
  saved_by_10: "נשמר על ידי 10 משתמשים",
};

interface Transaction {
  id: string;
  delta: number;
  reason: string;
}

export default function ProfilePage() {
  const router = useRouter();

  useEffect(() => {
    if (!localStorage.getItem("token")) router.push("/login");
  }, [router]);

  const { data: user } = useQuery({ queryKey: ["me"], queryFn: getMe });
  const { data: txns } = useQuery<Transaction[]>({
    queryKey: ["transactions"],
    queryFn: () => api.get("/users/me/transactions").then((r) => r.data),
    enabled: !!user,
  });

  if (!user) return <div className="p-8 text-center text-gray-400">טוען...</div>;

  const tierClass = TIER_COLORS[user.tier] ?? "text-gray-600 bg-gray-100";
  const nextTierPts = user.tier === "bronze" ? 100 : user.tier === "silver" ? 500 : null;

  return (
    <div className="max-w-lg mx-auto px-4 py-10">
      <div className="bg-white border border-gray-200 rounded-2xl p-6 mb-8">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-full bg-indigo-100 flex items-center justify-center text-2xl font-bold text-indigo-600">
            {user.username[0].toUpperCase()}
          </div>
          <div>
            <h1 className="text-xl font-bold">{user.username}</h1>
            <span className={`text-sm font-semibold px-2 py-0.5 rounded-full ${tierClass}`}>
              {TIER_LABELS[user.tier] ?? user.tier}
            </span>
          </div>
          <div className="mr-auto text-left">
            <p className="text-3xl font-bold text-indigo-600">{user.points_balance}</p>
            <p className="text-sm text-gray-400">נקודות</p>
          </div>
        </div>

        <div className="mt-4 bg-gray-100 rounded-full h-2 overflow-hidden">
          <div
            className="bg-indigo-500 h-2 rounded-full transition-all"
            style={{ width: `${Math.min((user.points_balance / 500) * 100, 100)}%` }}
          />
        </div>
        <p className="text-xs text-gray-400 mt-1 text-left">
          {nextTierPts
            ? `עוד ${nextTierPts - user.points_balance} נקודות לדרגה הבאה`
            : "דרגת זהב — המקסימום!"}
        </p>
      </div>

      <h2 className="font-semibold text-lg mb-3">פעילות אחרונה</h2>
      {!txns || txns.length === 0 ? (
        <p className="text-gray-400 text-sm">עדיין אין פעילות — שלח המלצה כדי להרוויח נקודות!</p>
      ) : (
        <div className="flex flex-col gap-2">
          {txns.map((tx) => (
            <div key={tx.id} className="flex items-center justify-between bg-white border border-gray-200 rounded-lg px-4 py-3">
              <span className="text-sm text-gray-700">
                {REASON_LABELS[tx.reason] ?? tx.reason}
              </span>
              <span className={`font-bold text-sm ${tx.delta > 0 ? "text-green-600" : "text-red-500"}`}>
                {tx.delta > 0 ? `+${tx.delta}` : tx.delta}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
