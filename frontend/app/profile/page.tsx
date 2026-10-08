"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import api, { getMe, getSavedPlaces, updatePreferences, type SavedPlaceEntry } from "@/lib/api";
import PlaceGrid from "@/components/PlaceGrid";

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

const CUISINE_OPTIONS = [
  "איטלקי", "יפני", "ים תיכוני", "בשר", "ישראלי",
  "מזרח תיכוני", "אסייתי", "צרפתי", "מקסיקני", "אמריקאי",
];

const DIETARY_OPTIONS = [
  { id: "כשר", label: "🔵 כשר" },
  { id: "טבעוני", label: "🌱 טבעוני" },
  { id: "צמחוני", label: "🌿 צמחוני" },
  { id: "ללא גלוטן", label: "🌾 ללא גלוטן" },
  { id: "חלאל", label: "🟢 חלאל" },
];

const PRICE_LABELS = ["", "₪ זול", "₪₪ בינוני", "₪₪₪ יקר", "₪₪₪₪ יוקרתי"];

type ProfileTab = "activity" | "wishlist" | "favorites" | "preferences";

export default function ProfilePage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<ProfileTab>("activity");
  const [localCuisine, setLocalCuisine] = useState<string[]>([]);
  const [localDietary, setLocalDietary] = useState<string[]>([]);
  const [localPrice, setLocalPrice] = useState<number>(0);
  const [prefsSaved, setPrefsSaved] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem("token")) router.push("/login");
  }, [router]);

  const { data: user } = useQuery({ queryKey: ["me"], queryFn: getMe });
  const { data: txns } = useQuery<Transaction[]>({
    queryKey: ["transactions"],
    queryFn: () => api.get("/users/me/transactions").then((r) => r.data),
    enabled: !!user,
  });
  const { data: wishlist = [], isLoading: wishlistLoading } = useQuery<SavedPlaceEntry[]>({
    queryKey: ["saved", "wishlist"],
    queryFn: () => getSavedPlaces("wishlist"),
    enabled: activeTab === "wishlist" && !!user,
  });
  const { data: favorites = [], isLoading: favoritesLoading } = useQuery<SavedPlaceEntry[]>({
    queryKey: ["saved", "favorite"],
    queryFn: () => getSavedPlaces("favorite"),
    enabled: activeTab === "favorites" && !!user,
  });

  // Populate local prefs from user data
  useEffect(() => {
    if (user) {
      setLocalCuisine(user.cuisine_preferences ?? []);
      setLocalDietary(user.dietary_restrictions ?? []);
      setLocalPrice(user.price_preference ?? 0);
    }
  }, [user]);

  const prefsMutation = useMutation({
    mutationFn: () =>
      updatePreferences({
        cuisine_preferences: localCuisine,
        dietary_restrictions: localDietary,
        price_preference: localPrice || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
      setPrefsSaved(true);
      setTimeout(() => setPrefsSaved(false), 2000);
    },
  });

  if (!user) return <div className="p-8 text-center text-gray-400">טוען...</div>;

  const tierClass = TIER_COLORS[user.tier] ?? "text-gray-600 bg-gray-100";
  const nextTierPts = user.tier === "bronze" ? 100 : user.tier === "silver" ? 500 : null;

  const tabs: { id: ProfileTab; label: string; emoji: string }[] = [
    { id: "activity", label: "פעילות", emoji: "📊" },
    { id: "wishlist", label: "רוצה לנסות", emoji: "❤️" },
    { id: "favorites", label: "מועדפים", emoji: "⭐" },
    { id: "preferences", label: "העדפות", emoji: "🎯" },
  ];

  return (
    <div className="max-w-lg mx-auto px-4 py-10">
      {/* User card */}
      <div className="bg-white border border-gray-200 rounded-2xl p-6 mb-6">
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

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 mb-6 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 shrink-0 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === tab.id
                ? "bg-white text-indigo-600 shadow"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <span>{tab.emoji}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Activity tab */}
      {activeTab === "activity" && (
        <>
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
        </>
      )}

      {/* Wishlist tab */}
      {activeTab === "wishlist" && (
        <>
          <p className="text-sm text-gray-500 mb-4">מקומות שרצית לנסות</p>
          <PlaceGrid places={wishlist} isLoading={wishlistLoading} />
        </>
      )}

      {/* Favorites tab */}
      {activeTab === "favorites" && (
        <>
          <p className="text-sm text-gray-500 mb-4">המקומות האהובים עליך</p>
          <PlaceGrid places={favorites} isLoading={favoritesLoading} />
        </>
      )}

      {/* Preferences tab */}
      {activeTab === "preferences" && (
        <div className="space-y-6">
          {/* Cuisine preferences */}
          <div>
            <h3 className="font-semibold text-gray-800 mb-2">מטבחות מועדפים</h3>
            <div className="flex flex-wrap gap-2">
              {CUISINE_OPTIONS.map((c) => (
                <button
                  key={c}
                  onClick={() =>
                    setLocalCuisine((prev) =>
                      prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]
                    )
                  }
                  className={`text-sm px-3 py-1.5 rounded-full border font-medium transition-all ${
                    localCuisine.includes(c)
                      ? "bg-indigo-600 text-white border-indigo-600"
                      : "bg-white text-gray-600 border-gray-200 hover:border-indigo-300"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>

          {/* Dietary restrictions */}
          <div>
            <h3 className="font-semibold text-gray-800 mb-2">הגבלות תזונתיות</h3>
            <div className="flex flex-wrap gap-2">
              {DIETARY_OPTIONS.map((d) => (
                <button
                  key={d.id}
                  onClick={() =>
                    setLocalDietary((prev) =>
                      prev.includes(d.id) ? prev.filter((x) => x !== d.id) : [...prev, d.id]
                    )
                  }
                  className={`text-sm px-3 py-1.5 rounded-full border font-medium transition-all ${
                    localDietary.includes(d.id)
                      ? "bg-green-600 text-white border-green-600"
                      : "bg-white text-gray-600 border-gray-200 hover:border-green-300"
                  }`}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          {/* Price preference */}
          <div>
            <h3 className="font-semibold text-gray-800 mb-2">טווח מחיר מועדף</h3>
            <div className="flex gap-2 flex-wrap">
              {[0, 1, 2, 3, 4].map((p) => (
                <button
                  key={p}
                  onClick={() => setLocalPrice(p)}
                  className={`text-sm px-3 py-1.5 rounded-full border font-medium transition-all ${
                    localPrice === p
                      ? "bg-amber-500 text-white border-amber-500"
                      : "bg-white text-gray-600 border-gray-200 hover:border-amber-300"
                  }`}
                >
                  {p === 0 ? "לא משנה" : PRICE_LABELS[p]}
                </button>
              ))}
            </div>
          </div>

          {/* Save button */}
          <button
            onClick={() => prefsMutation.mutate()}
            disabled={prefsMutation.isPending}
            className="w-full bg-indigo-600 text-white font-semibold py-3 rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {prefsSaved ? "✓ נשמר!" : prefsMutation.isPending ? "שומר..." : "שמור העדפות"}
          </button>
        </div>
      )}
    </div>
  );
}
