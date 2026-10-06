"use client";

import { useState } from "react";
import { type DataSource } from "@/lib/api";

const MENU_SOURCE_TYPES = new Set(["menu", "tabit", "ontopo", "wolt"]);

const SOURCE_ICONS: Record<string, string> = {
  tabit: "📋",
  ontopo: "🔖",
  wolt: "🟡",
  menu: "🍽️",
};

const SOURCE_NAMES: Record<string, string> = {
  tabit: "Tabit",
  ontopo: "Ontopo",
  wolt: "Wolt",
  menu: "תפריט",
};

interface Props {
  sources: DataSource[];
}

export default function MenuButton({ sources }: Props) {
  const [open, setOpen] = useState(false);
  const menuSources = sources.filter(
    (s) => MENU_SOURCE_TYPES.has(s.source_type) && s.url
  );

  if (menuSources.length === 0) return null;

  // Single menu source — direct link
  if (menuSources.length === 1) {
    return (
      <a
        href={menuSources[0].url!}
        target="_blank"
        rel="noopener noreferrer"
        className="fixed bottom-6 left-6 z-50 flex items-center gap-2 bg-white border border-gray-200 shadow-lg rounded-full px-4 py-2.5 text-sm font-semibold text-gray-800 hover:bg-gray-50 hover:shadow-xl transition-all active:scale-95"
      >
        <span className="text-base">🍽️</span>
        תפריט
      </a>
    );
  }

  // Multiple menu sources — sheet
  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 left-6 z-50 flex items-center gap-2 bg-white border border-gray-200 shadow-lg rounded-full px-4 py-2.5 text-sm font-semibold text-gray-800 hover:bg-gray-50 hover:shadow-xl transition-all active:scale-95"
      >
        <span className="text-base">🍽️</span>
        תפריט
      </button>

      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/30 z-50"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Bottom sheet */}
      <div
        className={`fixed bottom-0 left-0 right-0 z-50 bg-white rounded-t-3xl shadow-2xl transition-transform duration-300 ${
          open ? "translate-y-0" : "translate-y-full"
        }`}
      >
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-10 h-1 bg-gray-200 rounded-full" />
        </div>
        <div className="px-5 pb-8 pt-2">
          <h3 className="font-bold text-gray-800 mb-4 text-base">בחר פלטפורמה לתפריט</h3>
          <div className="flex flex-col gap-2">
            {menuSources.map((s, i) => {
              const icon = SOURCE_ICONS[s.source_type] ?? "🍽️";
              const name = s.source_name ?? SOURCE_NAMES[s.source_type] ?? s.source_type;
              return (
                <a
                  key={i}
                  href={s.url!}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-3 px-4 py-3 rounded-xl bg-gray-50 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                >
                  <span className="text-xl">{icon}</span>
                  <span className="font-medium text-sm">{name}</span>
                  <span className="mr-auto text-gray-400 text-xs">פתח ←</span>
                </a>
              );
            })}
          </div>
        </div>
      </div>
    </>
  );
}
