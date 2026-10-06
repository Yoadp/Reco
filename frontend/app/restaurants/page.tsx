"use client";

import { useState, useEffect, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import { searchPlaces } from "@/lib/api";
import CategoryRow from "@/components/CategoryRow";
import SubcategoryChips from "@/components/SubcategoryChips";
import PlaceGrid from "@/components/PlaceGrid";
import { CATEGORIES } from "@/lib/categories";

// Load map lazily — avoids SSR issues with Google Maps
const MapView = dynamic(() => import("@/components/MapView"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-[60vh] rounded-2xl bg-gray-100 animate-pulse flex items-center justify-center">
      <p className="text-gray-400">טוען מפה...</p>
    </div>
  ),
});

type ViewMode = "grid" | "map";

function subcategoryToCuisine(subId: string): string | undefined {
  for (const cat of CATEGORIES) {
    const sub = cat.subcategories.find((s) => s.id === subId);
    if (sub) return sub.label;
  }
  return undefined;
}

function categoryToCuisine(catId: string): string | undefined {
  const cat = CATEGORIES.find((c) => c.id === catId);
  return cat?.label;
}

function RestaurantsPage() {
  const searchParams = useSearchParams();
  const initialQ = searchParams.get("q") ?? "";
  const initialNlp = searchParams.get("nlp") === "true";

  const [view, setView] = useState<ViewMode>("grid");
  const [q, setQ] = useState(initialQ);
  const [search, setSearch] = useState(initialQ);
  const [nlp, setNlp] = useState(initialNlp);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSub, setSelectedSub] = useState<string | null>(null);

  // Debounce: fire fast SQL search 400ms after user stops typing (no NLP)
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(q);
      setNlp(false);
    }, 400);
    return () => clearTimeout(timer);
  }, [q]);

  const cuisineFilter = selectedSub
    ? subcategoryToCuisine(selectedSub)
    : selectedCategory
    ? categoryToCuisine(selectedCategory)
    : undefined;

  const { data: places = [], isLoading } = useQuery({
    queryKey: ["places", search, cuisineFilter, nlp],
    queryFn: () =>
      searchPlaces({
        q: search || undefined,
        cuisine: cuisineFilter,
        nlp: nlp || undefined,
      }),
  });

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setSearch(q);
    setNlp(true);  // button click / Enter → Groq NLP
  }

  function handleCategorySelect(id: string | null) {
    setSelectedCategory(id);
    setSelectedSub(null);
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      {/* Header row */}
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-2xl font-extrabold text-gray-900">גלה מסעדות</h1>

        {/* View toggle */}
        <div className="flex bg-gray-100 rounded-xl p-1 gap-1">
          <button
            onClick={() => setView("grid")}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
              view === "grid"
                ? "bg-white shadow text-indigo-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
            title="תצוגת רשת"
          >
            ⊞ רשת
          </button>
          <button
            onClick={() => setView("map")}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
              view === "map"
                ? "bg-white shadow text-indigo-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
            title="תצוגת מפה"
          >
            🗺️ מפה
          </button>
        </div>
      </div>

      {/* Category row */}
      <div className="mb-3">
        <CategoryRow selected={selectedCategory} onSelect={handleCategorySelect} />
      </div>

      {/* Subcategory chips (when a category is selected) */}
      {selectedCategory && (
        <div className="mb-4">
          <SubcategoryChips
            categoryId={selectedCategory}
            selected={selectedSub}
            onSelect={setSelectedSub}
          />
        </div>
      )}

      {/* Search bar */}
      <form onSubmit={handleSearch} className="flex gap-2 mb-5">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="נסה: פסטה בתל אביב, סושי, חומוס יפו..."
          className="flex-1 border border-gray-200 bg-gray-50 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:bg-white transition-colors"
        />
        <button
          type="submit"
          className="bg-indigo-600 text-white px-5 py-2.5 rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors shrink-0"
        >
          חיפוש
        </button>
      </form>

      {/* Active filter label */}
      {(cuisineFilter || search) && (
        <div className="mb-4 flex items-center gap-2 flex-wrap">
          {cuisineFilter && (
            <span className="text-xs bg-indigo-50 text-indigo-700 px-3 py-1 rounded-full font-medium">
              {cuisineFilter}
              <button
                onClick={() => { setSelectedCategory(null); setSelectedSub(null); }}
                className="mr-1.5 opacity-60 hover:opacity-100"
              >×</button>
            </span>
          )}
          {search && (
            <span className="text-xs bg-gray-100 text-gray-600 px-3 py-1 rounded-full">
              חיפוש: {search}
              <button
                onClick={() => { setQ(""); setSearch(""); }}
                className="mr-1.5 opacity-60 hover:opacity-100"
              >×</button>
            </span>
          )}
          <span className="text-xs text-gray-400">{places.length} תוצאות</span>
        </div>
      )}

      {/* Main content */}
      {view === "map" ? (
        <MapView places={places} />
      ) : (
        <PlaceGrid places={places} isLoading={isLoading} />
      )}
    </div>
  );
}

export default function RestaurantsPageWrapper() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-gray-400">טוען...</div>}>
      <RestaurantsPage />
    </Suspense>
  );
}
