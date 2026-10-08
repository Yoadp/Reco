"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { searchPlaces } from "@/lib/api";
import PlaceGrid from "@/components/PlaceGrid";

function DiscoverySection({
  title,
  emoji,
  sort,
  description,
}: {
  title: string;
  emoji: string;
  sort: string;
  description: string;
}) {
  const { data: places = [], isLoading } = useQuery({
    queryKey: ["discovery", sort],
    queryFn: () => searchPlaces({ sort, limit: 8 }),
    staleTime: 5 * 60 * 1000,
  });

  return (
    <section className="mb-10">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-extrabold text-gray-900 flex items-center gap-2">
            <span>{emoji}</span> {title}
          </h2>
          <p className="text-sm text-gray-400 mt-0.5">{description}</p>
        </div>
        <Link
          href={`/restaurants?sort=${sort}`}
          className="text-sm text-indigo-600 font-medium hover:underline shrink-0"
        >
          הכל ←
        </Link>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-2xl bg-gray-100 animate-pulse h-40" />
          ))}
        </div>
      ) : places.length === 0 ? null : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {places.slice(0, 4).map((p) => (
            <Link
              key={p.id}
              href={`/places/${p.slug}`}
              className="block rounded-2xl overflow-hidden bg-white border border-gray-100 shadow-sm hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200"
            >
              {p.photos && p.photos[0] ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={p.photos[0]}
                  alt={p.name}
                  className="w-full h-28 object-cover"
                />
              ) : (
                <div className="w-full h-28 bg-gradient-to-br from-indigo-100 to-purple-100 flex items-center justify-center text-3xl">
                  🍽️
                </div>
              )}
              <div className="p-2.5">
                <h3 className="font-bold text-sm text-gray-800 truncate">{p.name}</h3>
                <div className="flex items-center justify-between mt-1">
                  <span className="text-xs text-gray-400 truncate">
                    {p.cuisine?.[0] ?? p.city ?? ""}
                  </span>
                  {p.aggregated_score && (
                    <span className="text-xs font-bold text-green-600">★ {p.aggregated_score.toFixed(1)}</span>
                  )}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

export default function HomePage() {
  const [q, setQ] = useState("");
  const router = useRouter();

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const term = q.trim();
    router.push(term ? `/restaurants?q=${encodeURIComponent(term)}&nlp=true` : "/restaurants");
  }

  return (
    <div className="flex flex-col">
      {/* Hero */}
      <section className="bg-gradient-to-b from-indigo-50 to-white px-4 py-16 text-center">
        <h1 className="text-4xl font-extrabold text-gray-900 mb-4 leading-tight">
          גלה את המקומות הטובים ביותר
        </h1>
        <p className="text-lg text-gray-500 max-w-md mx-auto mb-8">
          המלצות אמיתיות מאנשים אמיתיים. דרג, המלץ וצבור נקודות.
        </p>

        <form onSubmit={handleSearch} className="flex max-w-lg mx-auto gap-2 mb-4">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="נסה: פסטה בתל אביב, סושי, חומוס יפו..."
            className="flex-1 border border-gray-200 bg-white rounded-xl px-4 py-3 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            dir="rtl"
          />
          <button
            type="submit"
            className="bg-indigo-600 text-white px-6 py-3 rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors shrink-0"
          >
            חפש
          </button>
        </form>

        <Link href="/restaurants" className="text-sm text-indigo-500 hover:underline">
          או עיין בכל המסעדות ←
        </Link>
      </section>

      {/* Discovery sections */}
      <div className="max-w-3xl mx-auto px-4 py-10 w-full">
        <DiscoverySection
          title="חם עכשיו"
          emoji="🔥"
          sort="trending"
          description="המקומות הפופולריים השבוע"
        />

        <DiscoverySection
          title="פנינים נסתרות"
          emoji="💎"
          sort="hidden_gems"
          description="ציוני מעולים שעוד לא כולם מכירים"
        />

        <DiscoverySection
          title="חדש ב-Reco"
          emoji="✨"
          sort="new"
          description="מסעדות שהתווספו לאחרונה"
        />
      </div>

      {/* How it works */}
      <section className="max-w-3xl mx-auto px-4 pb-16 w-full">
        <h2 className="text-2xl font-bold text-center mb-8">איך זה עובד?</h2>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          <div className="bg-white border border-gray-200 rounded-2xl p-6 text-center">
            <div className="text-4xl mb-3">🔍</div>
            <h3 className="font-bold text-lg mb-1">חפש</h3>
            <p className="text-gray-500 text-sm">מצא מסעדות לפי שם, מטבח או עיר</p>
          </div>
          <div className="bg-white border border-gray-200 rounded-2xl p-6 text-center">
            <div className="text-4xl mb-3">✍️</div>
            <h3 className="font-bold text-lg mb-1">המלץ</h3>
            <p className="text-gray-500 text-sm">שתף את החוויה שלך ועזור לאחרים לבחור</p>
          </div>
          <div className="bg-white border border-gray-200 rounded-2xl p-6 text-center">
            <div className="text-4xl mb-3">🏆</div>
            <h3 className="font-bold text-lg mb-1">צבור נקודות</h3>
            <p className="text-gray-500 text-sm">המלצות טובות מזכות אותך בנקודות ודרגה גבוהה יותר</p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-indigo-600 px-4 py-14 text-center text-white">
        <h2 className="text-2xl font-bold mb-3">מוכן להתחיל?</h2>
        <p className="text-indigo-200 mb-6">הצטרף לקהילה וצבור נקודות על המלצות מדויקות</p>
        <div className="flex justify-center gap-3">
          <Link
            href="/register"
            className="bg-white text-indigo-600 font-semibold px-6 py-2.5 rounded-xl hover:bg-indigo-50 transition-colors"
          >
            הרשמה חינם
          </Link>
          <Link
            href="/restaurants"
            className="border border-white text-white font-semibold px-6 py-2.5 rounded-xl hover:bg-indigo-500 transition-colors"
          >
            גלה מסעדות
          </Link>
        </div>
      </section>
    </div>
  );
}
