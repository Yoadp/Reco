"use client";

import { getCategoryById } from "@/lib/categories";

interface Props {
  categoryId: string;
  selected: string | null;
  onSelect: (id: string | null) => void;
}

export default function SubcategoryChips({ categoryId, selected, onSelect }: Props) {
  const category = getCategoryById(categoryId);
  if (!category) return null;

  return (
    <div
      className="flex gap-2 overflow-x-auto pb-1 -mx-4 px-4"
      style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
    >
      {category.subcategories.map((sub) => {
        const isActive = selected === sub.id;
        return (
          <button
            key={sub.id}
            onClick={() => onSelect(isActive ? null : sub.id)}
            className={`
              shrink-0 px-4 py-1.5 rounded-full text-sm font-semibold transition-all duration-150
              ${isActive
                ? `${category.solidActive} shadow-md scale-105`
                : "bg-white text-gray-600 border border-gray-200 hover:border-gray-400 hover:text-gray-800"}
            `}
          >
            {sub.label}
          </button>
        );
      })}
    </div>
  );
}
