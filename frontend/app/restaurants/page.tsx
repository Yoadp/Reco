"use client";

import { useState, useEffect, useCallback, useRef, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { searchPlaces, smartSearchPlaces, getSavedIds, type SmartSearchResult } from "@/lib/api";
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
  const router = useRouter();

  // Read initial state from URL (set when user previously searched and navigated away)
  const initialQ = searchParams.get("q") ?? "";
  const initialSmart = searchParams.get("smart") === "1";
  const initialCat = searchParams.get("cat");
  const initialSub = searchParams.get("sub");
  const initialCity = searchParams.get("city") ?? "";
  const initialOpen = searchParams.get("open") === "1";

  const [view, setView] = useState<ViewMode>("grid");
  const [q, setQ] = useState(initialQ);
  const [search, setSearch] = useState(initialQ);
  const [smartResult, setSmartResult] = useState<SmartSearchResult | null>(null);
  const [smartLoading, setSmartLoading] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(initialCat);
  const [selectedSub, setSelectedSub] = useState<string | null>(initialSub);
  const [cityFilter, setCityFilter] = useState<string>(initialCity);
  const [openNow, setOpenNow] = useState(initialOpen);
  const [userLat, setUserLat] = useState<number | null>(null);
  const [userLng, setUserLng] = useState<number | null>(null);
  const [gpsLoading, setGpsLoading] = useState(false);
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set());
  const isLoggedIn = typeof window !== "undefined" && !!localStorage.getItem("token");

  // Re-run smart search on mount if it was active when user navigated away
  const didRestoreSmartRef = useRef(false);
  useEffect(() => {
    if (!didRestoreSmartRef.current && initialSmart && initialQ) {
      didRestoreSmartRef.current = true;
      setSmartLoading(true);
      smartSearchPlaces(initialQ, initialCity || undefined)
        .then(setSmartResult)
        .finally(() => setSmartLoading(false));
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync meaningful state to URL so browser back-button restores it
  const urlSyncSkipFirst = useRef(true);
  useEffect(() => {
    if (urlSyncSkipFirst.current) { urlSyncSkipFirst.current = false; return; }
    const params = new URLSearchParams();
    if (search) params.set("q", search);
    if (smartResult) params.set("smart", "1");
    if (selectedCategory) params.set("cat", selectedCategory);
    if (selectedSub) params.set("sub", selectedSub);
    if (cityFilter) params.set("city", cityFilter);
    if (openNow) params.set("open", "1");
    const qs = params.toString();
    router.replace(qs ? `/restaurants?${qs}` : "/restaurants", { scroll: false });
  }, [search, !!smartResult, selectedCategory, selectedSub, cityFilter, openNow]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load saved IDs for heart buttons
  useEffect(() => {
    if (!isLoggedIn) return;
    getSavedIds()
      .then((rows) => setSavedIds(new Set(rows.map((r) => r.place_id))))
      .catch(() => {});
  }, [isLoggedIn]);

  // Debounce: fire fast SQL search 400ms after user stops typing
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(q);
      if (smartResult && q !== smartResult.parsed.dish && q !== smartResult.parsed.cuisine) {
        setSmartResult(null);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const cuisineFilter = selectedSub
    ? subcategoryToCuisine(selectedSub)
    : selectedCategory
    ? categoryToCuisine(selectedCategory)
    : undefined;

  const { data: fastPlaces = [], isLoading: fastLoading } = useQuery({
    queryKey: ["places", search, cuisineFilter, cityFilter, openNow, userLat, userLng],
    queryFn: () =>
      searchPlaces({
        q: search || undefined,
        cuisine: cuisineFilter,
        city: cityFilter || undefined,
        open_now: openNow || undefined,
        lat: userLat ?? undefined,
        lng: userLng ?? undefined,
        radius_km: userLat != null ? 10 : undefined,
      }),
    enabled: !smartResult,
  });

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setSmartLoading(true);
    try {
      const result = await smartSearchPlaces(q, cityFilter || undefined);
      setSmartResult(result);
    } finally {
      setSmartLoading(false);
    }
  }

  function handleCategorySelect(id: string | null) {
    setSelectedCategory(id);
    setSelectedSub(null);
    setSmartResult(null);
  }

  function clearSmartSearch() {
    setSmartResult(null);
    setQ("");
    setSearch("");
  }

  function handleNearMe() {
    if (userLat != null) {
      // Toggle off
      setUserLat(null);
      setUserLng(null);
      return;
    }
    if (!navigator.geolocation) return;
    setGpsLoading(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setUserLat(pos.coords.latitude);
        setUserLng(pos.coords.longitude);
        setGpsLoading(false);
      },
      () => setGpsLoading(false),
      { timeout: 10000 }
    );
  }

  const handleSaveToggle = useCallback((placeId: string, _listType: string, saved: boolean) => {
    setSavedIds((prev) => {
      const next = new Set(prev);
      saved ? next.add(placeId) : next.delete(placeId);
      return next;
    });
  }, []);

  const isLoading = smartResult ? smartLoading : fastLoading;
  const allPlaces = smartResult
    ? [...smartResult.exact, ...smartResult.similar]
    : fastPlaces;

  const parsed = smartResult?.parsed;

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
          >
            🗺️ מפה
          </button>
        </div>
      </div>

      {/* Category row */}
      <div className="mb-3">
        <CategoryRow selected={selectedCategory} onSelect={handleCategorySelect} />
      </div>

      {/* Subcategory chips */}
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
      <form onSubmit={handleSearch} className="flex gap-2 mb-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="נסה: פסטה ברוטב לימון במחיר 60-80, סושי ברמת גן..."
          className="flex-1 border border-gray-200 bg-gray-50 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:bg-white transition-colors"
        />
        <button
          type="submit"
          disabled={smartLoading}
          className="bg-indigo-600 text-white px-5 py-2.5 rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors shrink-0 disabled:opacity-60"
        >
          {smartLoading ? "מחפש..." : "חיפוש"}
        </button>
      </form>

      {/* Filter action row: Open Now + Near Me */}
      <div className="flex gap-2 mb-3">
        <button
          onClick={() => setOpenNow((v) => !v)}
          className={`flex items-center gap-1.5 text-sm font-medium px-3.5 py-1.5 rounded-full border transition-all ${
            openNow
              ? "bg-green-600 text-white border-green-600 shadow-sm"
              : "bg-white text-gray-600 border-gray-300 hover:border-green-500 hover:text-green-700"
          }`}
        >
          <span className={`w-2 h-2 rounded-full ${openNow ? "bg-white" : "bg-green-400"}`} />
          פתוח עכשיו
        </button>

        <button
          onClick={handleNearMe}
          disabled={gpsLoading}
          className={`flex items-center gap-1.5 text-sm font-medium px-3.5 py-1.5 rounded-full border transition-all disabled:opacity-50 ${
            userLat != null
              ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
              : "bg-white text-gray-600 border-gray-300 hover:border-indigo-400 hover:text-indigo-700"
          }`}
        >
          {gpsLoading ? "מאתר..." : userLat != null ? "📍 קרוב אליי ×" : "📍 קרוב אליי"}
        </button>
      </div>

      {/* City filter chips */}
      <div className="flex gap-2 overflow-x-auto pb-2 mb-4 -mx-4 px-4" style={{ scrollbarWidth: "none" }}>
        {["תל אביב","יפו","רמת גן","גבעתיים","בני ברק","פתח תקווה","ראשון לציון","חולון","בת ים","הרצליה","רעננה","כפר סבא","הוד השרון","נתניה","רחובות","נס ציונה","מודיעין"].map(city => (
          <button
            key={city}
            onClick={() => setCityFilter(cityFilter === city ? "" : city)}
            className={`shrink-0 text-sm font-medium px-3.5 py-1.5 rounded-full border transition-all ${
              cityFilter === city
                ? "bg-indigo-600 text-white border-indigo-600 shadow-sm"
                : "bg-white text-gray-600 border-gray-300 hover:border-indigo-400 hover:text-indigo-700"
            }`}
          >
            {city}
          </button>
        ))}
      </div>

      {/* Parsed query chips — shown after smart search */}
      {parsed && (
        <div className="mb-4 flex items-center gap-2 flex-wrap">
          {parsed.dish && (
            <span className="text-xs bg-indigo-50 text-indigo-700 px-3 py-1 rounded-full font-medium">
              🍽️ {parsed.dish}
            </span>
          )}
          {parsed.cuisine && !parsed.dish && (
            <span className="text-xs bg-indigo-50 text-indigo-700 px-3 py-1 rounded-full font-medium">
              🍴 {parsed.cuisine}
            </span>
          )}
          {(parsed.price_min_ils || parsed.price_max_ils) && (
            <span className="text-xs bg-green-50 text-green-700 px-3 py-1 rounded-full font-medium">
              💰 {parsed.price_min_ils && parsed.price_max_ils
                ? `${parsed.price_min_ils}–${parsed.price_max_ils} ₪`
                : parsed.price_max_ils
                ? `עד ${parsed.price_max_ils} ₪`
                : `מ-${parsed.price_min_ils} ₪`}
            </span>
          )}
          {parsed.city && (
            <span className="text-xs bg-indigo-50 text-indigo-700 px-3 py-1 rounded-full font-medium">
              📍 {parsed.city}
            </span>
          )}
          {parsed.party_size != null && (
            <span className="text-xs bg-purple-50 text-purple-700 px-3 py-1 rounded-full font-medium">
              👥 {parsed.party_size} סועדים
            </span>
          )}
          {parsed.open_at_hour != null && (() => {
            const DAY_NAMES = ["ראשון","שני","שלישי","רביעי","חמישי","שישי","שבת"];
            const todayGoogle = (new Date().getDay());
            const dayLabel = parsed.open_at_day === todayGoogle
              ? "היום"
              : parsed.open_at_day === (todayGoogle + 1) % 7
              ? "מחר"
              : parsed.open_at_day != null ? DAY_NAMES[parsed.open_at_day] : "היום";
            return (
              <span className="text-xs bg-amber-50 text-amber-700 px-3 py-1 rounded-full font-medium">
                🕐 {dayLabel} ב-{String(parsed.open_at_hour).padStart(2,"0")}:00
              </span>
            );
          })()}
          <button
            onClick={clearSmartSearch}
            className="text-xs text-gray-400 hover:text-gray-600 px-2"
          >
            × נקה
          </button>
        </div>
      )}

      {/* Active filter chips — shown when no smart result */}
      {!smartResult && (cuisineFilter || search || cityFilter || openNow || userLat != null) && (
        <div className="mb-4 flex items-center gap-2 flex-wrap">
          {cityFilter && (
            <span className="text-xs bg-indigo-50 text-indigo-700 px-3 py-1 rounded-full font-medium">
              📍 {cityFilter}
              <button onClick={() => setCityFilter("")} className="mr-1.5 opacity-60 hover:opacity-100">×</button>
            </span>
          )}
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
          <span className="text-xs text-gray-400">{fastPlaces.length} תוצאות</span>
        </div>
      )}

      {/* Smart search results */}
      {smartResult && !smartLoading && view === "grid" && (
        <>
          {smartResult.exact.length > 0 ? (
            <section className="mb-6">
              <div className="flex items-center gap-2 mb-3">
                <span className="w-2.5 h-2.5 rounded-full bg-green-500 shrink-0" />
                <h2 className="text-sm font-bold text-gray-800">תוצאות מדויקות</h2>
                <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">{smartResult.exact.length}</span>
              </div>
              <PlaceGrid
                places={smartResult.exact}
                isLoading={false}
                savedIds={savedIds}
                isLoggedIn={isLoggedIn}
                userLat={userLat}
                userLng={userLng}
                onSaveToggle={handleSaveToggle}
              />
            </section>
          ) : (
            <p className="text-sm text-gray-500 mb-4 bg-amber-50 border border-amber-100 rounded-xl px-4 py-3">
              לא נמצאו תוצאות מדויקות — הנה מקומות שאולי יתאימו:
            </p>
          )}

          {smartResult.similar.length > 0 && (
            <section className="mb-6">
              {smartResult.exact.length > 0 && (
                <div className="flex items-center gap-2 mb-3">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-400 shrink-0" />
                  <h2 className="text-sm font-bold text-gray-600">תוצאות דומות</h2>
                  <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">{smartResult.similar.length}</span>
                </div>
              )}
              <PlaceGrid
                places={smartResult.similar}
                isLoading={false}
                savedIds={savedIds}
                isLoggedIn={isLoggedIn}
                userLat={userLat}
                userLng={userLng}
                onSaveToggle={handleSaveToggle}
              />
            </section>
          )}

          {smartResult.exact.length === 0 && smartResult.similar.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              <p className="text-lg mb-1">לא נמצאו תוצאות</p>
              <p className="text-sm">נסה לשנות את החיפוש או לבחור קטגוריה</p>
            </div>
          )}
        </>
      )}

      {/* Map view */}
      {view === "map" && <MapView places={allPlaces} />}

      {/* Regular (non-smart) grid results */}
      {!smartResult && view === "grid" && (
        <PlaceGrid
          places={fastPlaces}
          isLoading={fastLoading}
          savedIds={savedIds}
          isLoggedIn={isLoggedIn}
          userLat={userLat}
          userLng={userLng}
          onSaveToggle={handleSaveToggle}
        />
      )}

      {/* Loading spinner for smart search */}
      {smartLoading && (
        <div className="flex flex-col items-center justify-center py-16 gap-3 text-gray-400">
          <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
          <p className="text-sm">מנתח את החיפוש שלך...</p>
        </div>
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
