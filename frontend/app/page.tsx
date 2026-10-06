"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";

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
      <section className="bg-gradient-to-b from-indigo-50 to-white px-4 py-20 text-center">
        <h1 className="text-4xl font-extrabold text-gray-900 mb-4 leading-tight">
          גלה את המקומות הטובים ביותר
        </h1>
        <p className="text-lg text-gray-500 max-w-md mx-auto mb-8">
          המלצות אמיתיות מאנשים אמיתיים. דרג, המלץ וצבור נקודות.
        </p>

        {/* Hero search */}
        <form onSubmit={handleSearch} className="flex max-w-lg mx-auto gap-2 mb-6">
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

        <Link
          href="/restaurants"
          className="text-sm text-indigo-500 hover:underline"
        >
          או עיין בכל המסעדות ←
        </Link>
      </section>

      {/* How it works */}
      <section className="max-w-3xl mx-auto px-4 py-16 w-full">
        <h2 className="text-2xl font-bold text-center mb-10">איך זה עובד?</h2>
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
