"use client";

import { CATEGORIES, type Category } from "@/lib/categories";

interface Props {
  selected: string | null;
  onSelect: (id: string | null) => void;
}

function CategoryTile({ cat, isSelected, onSelect }: { cat: Category; isSelected: boolean; onSelect: () => void }) {
  return (
    <button
      onClick={onSelect}
      className={`
        shrink-0 flex flex-col items-center justify-center gap-1
        w-20 h-20 rounded-2xl snap-start transition-all duration-200
        ${isSelected
          ? `${cat.solidActive} shadow-lg scale-105 ring-2 ring-offset-2 ring-current`
          : `bg-gradient-to-br ${cat.gradient} opacity-80 hover:opacity-100 hover:scale-105`}
      `}
    >
      <span className="text-2xl leading-none">{cat.emoji}</span>
      <span className={`text-xs font-bold text-center leading-tight px-1 ${isSelected ? "text-white" : cat.textColor}`}>
        {cat.label}
      </span>
    </button>
  );
}

export default function CategoryRow({ selected, onSelect }: Props) {
  return (
    <div
      className="flex gap-3 overflow-x-auto pb-2 -mx-4 px-4 snap-x snap-mandatory"
      style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
    >
      {/* All button */}
      <button
        onClick={() => onSelect(null)}
        className={`
          shrink-0 flex flex-col items-center justify-center gap-1
          w-20 h-20 rounded-2xl snap-start transition-all duration-200
          ${selected === null
            ? "bg-indigo-600 text-white shadow-lg scale-105 ring-2 ring-offset-2 ring-indigo-600"
            : "bg-gray-100 hover:bg-gray-200 text-gray-600"}
        `}
      >
        <span className="text-2xl leading-none">🍽️</span>
        <span className="text-xs font-bold text-center leading-tight">הכל</span>
      </button>

      {CATEGORIES.map((cat) => (
        <CategoryTile
          key={cat.id}
          cat={cat}
          isSelected={selected === cat.id}
          onSelect={() => onSelect(selected === cat.id ? null : cat.id)}
        />
      ))}
    </div>
  );
}
