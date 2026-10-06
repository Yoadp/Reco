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
              shrink-0 px-4 py-1.5 rounded-full text-sm font-medium transition-all
              ${isActive
                ? `bg-gradient-to-r ${category.gradient} ${category.textColor} shadow-sm border border-current/20`
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"}
            `}
          >
            {sub.label}
          </button>
        );
      })}
    </div>
  );
}
