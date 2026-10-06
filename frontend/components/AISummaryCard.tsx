"use client";

import { useState } from "react";
import api from "@/lib/api";

interface AISummary {
  summary: string;
  match_score: number;
  highlights: string[];
  warnings: string[];
}

interface Props {
  placeSlug: string;
}

const PREFERENCE_CHIPS = [
  { id: "vegetarian", label: "🌿 צמחוני" },
  { id: "vegan", label: "🌱 טבעוני" },
  { id: "spicy", label: "🌶️ חריף" },
  { id: "romantic", label: "❤️ רומנטי" },
  { id: "family", label: "👨‍👩‍👧 משפחות" },
  { id: "bar", label: "🍷 בר" },
  { id: "budget", label: "💰 מחיר טוב" },
  { id: "glutenfree", label: "🌾 ללא גלוטן" },
];

function ScoreRing({ score }: { score: number }) {
  const r = 28;
  const circumference = 2 * Math.PI * r;
  const filled = (score / 100) * circumference;
  const color = score >= 80 ? "#22c55e" : score >= 60 ? "#f59e0b" : "#ef4444";

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-20 h-20">
        <svg className="w-20 h-20 -rotate-90" viewBox="0 0 72 72">
          <circle cx="36" cy="36" r={r} fill="none" stroke="#e5e7eb" strokeWidth="6" />
          <circle
            cx="36" cy="36" r={r}
            fill="none"
            stroke={color}
            strokeWidth="6"
            strokeDasharray={`${filled} ${circumference}`}
            strokeLinecap="round"
            style={{ transition: "stroke-dasharray 0.8s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xl font-extrabold text-gray-800">{score}%</span>
        </div>
      </div>
      <span className="text-xs font-semibold text-gray-500">התאמה</span>
    </div>
  );
}

export default function AISummaryCard({ placeSlug }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [freeText, setFreeText] = useState("");
  const [result, setResult] = useState<AISummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleChip(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function getSummary() {
    setIsLoading(true);
    setError(null);
    setResult(null);

    const selectedLabels = PREFERENCE_CHIPS
      .filter((c) => selected.has(c.id))
      .map((c) => c.label.replace(/[^\u0000-ɏ֐-׿ ]/g, "").trim());
    const preferences = [...selectedLabels, freeText.trim()].filter(Boolean).join(", ");

    try {
      const res = await api.post<AISummary>("/ai/summarize", {
        place_slug: placeSlug,
        preferences: preferences || undefined,
      });
      setResult(res.data);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      if (msg?.includes("GEMINI_API_KEY")) {
        setError("מפתח AI לא מוגדר — הוסף GEMINI_API_KEY לשרת");
      } else {
        setError(msg ?? "שגיאה בקבלת הסיכום");
      }
    } finally {
      setIsLoading(false);
    }
  }

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className="w-full flex items-center justify-between bg-gradient-to-br from-indigo-50 to-purple-50 border border-indigo-100 rounded-2xl px-5 py-3.5 text-right hover:border-indigo-300 transition-colors"
      >
        <span className="font-semibold text-gray-700 flex items-center gap-2">
          <span>✨</span> סיכום AI
        </span>
        <span className="text-gray-400 text-sm">▼ לחץ להרחבה</span>
      </button>
    );
  }

  return (
    <section className="bg-gradient-to-br from-indigo-50 to-purple-50 border border-indigo-100 rounded-2xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-bold text-lg text-gray-800 flex items-center gap-2">
          <span className="text-xl">✨</span> סיכום חכם
        </h2>
        <button onClick={() => setExpanded(false)} className="text-gray-400 text-sm hover:text-gray-600">▲ סגור</button>
      </div>

      {/* Preference chips */}
      <p className="text-xs text-gray-500 mb-2 font-medium">מה מחפשים?</p>
      <div className="flex flex-wrap gap-2 mb-3">
        {PREFERENCE_CHIPS.map((chip) => (
          <button
            key={chip.id}
            onClick={() => toggleChip(chip.id)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-all font-medium ${
              selected.has(chip.id)
                ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
                : "bg-white text-gray-600 border-gray-200 hover:border-indigo-300"
            }`}
          >
            {chip.label}
          </button>
        ))}
      </div>

      {/* Free text */}
      <input
        value={freeText}
        onChange={(e) => setFreeText(e.target.value)}
        placeholder="העדפות נוספות (אופציונלי)..."
        className="w-full text-sm border border-gray-200 rounded-xl px-3 py-2 mb-3 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-300"
      />

      {/* Submit */}
      <button
        onClick={getSummary}
        disabled={isLoading}
        className="w-full bg-indigo-600 text-white font-semibold text-sm py-2.5 rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
      >
        {isLoading ? (
          <>
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            מנתח...
          </>
        ) : (
          "קבל סיכום אישי ←"
        )}
      </button>

      {/* Error */}
      {error && (
        <p className="mt-3 text-sm text-red-500 bg-red-50 rounded-xl px-3 py-2">{error}</p>
      )}

      {/* Result */}
      {result && (
        <div className="mt-5 pt-5 border-t border-indigo-100">
          <div className="flex items-start gap-4 mb-4">
            <ScoreRing score={result.match_score} />
            <p className="text-sm text-gray-700 leading-relaxed flex-1 pt-1">{result.summary}</p>
          </div>

          {result.highlights.length > 0 && (
            <ul className="space-y-1.5 mb-2">
              {result.highlights.map((h, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                  <span className="text-green-500 font-bold mt-0.5">✓</span>
                  {h}
                </li>
              ))}
            </ul>
          )}

          {result.warnings.length > 0 && (
            <ul className="space-y-1.5 mt-2">
              {result.warnings.map((w, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-amber-700">
                  <span className="font-bold mt-0.5">⚠</span>
                  {w}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
