"use client";

import { useState, useEffect, useCallback, useRef, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { MagnifyingGlass, MapPin, GridFour, MapTrifold, X, SlidersHorizontal } from "@phosphor-icons/react";
import { searchPlaces, smartSearchPlaces, getSavedIds, getMe, type SmartSearchResult } from "@/lib/api";
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
  return cat?.cuisineQuery ?? cat?.label;
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
  const [sortMode, setSortMode] = useState<string>(searchParams.get("sort") ?? "");
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
    if (sortMode) params.set("sort", sortMode);
    const qs = params.toString();
    router.replace(qs ? `/restaurants?${qs}` : "/restaurants", { scroll: false });
  }, [search, !!smartResult, selectedCategory, selectedSub, cityFilter, openNow, sortMode]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load saved IDs for heart buttons
  useEffect(() => {
    if (!isLoggedIn) return;
    getSavedIds()
      .then((rows) => setSavedIds(new Set(rows.map((r) => r.place_id))))
      .catch(() => {});
  }, [isLoggedIn]);

  // Load user preferences (for result boosting)
  const { data: profile } = useQuery({
    queryKey: ["me"],
    queryFn: getMe,
    enabled: isLoggedIn,
    retry: false,
    staleTime: 10 * 60 * 1000,
  });

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
    queryKey: ["places", search, cuisineFilter, cityFilter, openNow, userLat, userLng, sortMode],
    queryFn: () =>
      searchPlaces({
        q: search || undefined,
        cuisine: cuisineFilter,
        city: cityFilter || undefined,
        open_now: openNow || undefined,
        lat: userLat ?? undefined,
        lng: userLng ?? undefined,
        radius_km: userLat != null ? 10 : undefined,
        sort: sortMode || undefined,
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
  const rawPlaces = smartResult
    ? [...smartResult.exact, ...smartResult.similar]
    : fastPlaces;

  // Boost places matching user's cuisine preferences to the top (only when no explicit cuisine filter active)
  const allPlaces = (() => {
    const prefs = profile?.cuisine_preferences;
    if (!prefs?.length || cuisineFilter) return rawPlaces;
    const preferred = rawPlaces.filter(p => p.cuisine?.some(c => prefs.includes(c)));
    const rest = rawPlaces.filter(p => !p.cuisine?.some(c => prefs.includes(c)));
    return preferred.length > 0 && preferred.length < rawPlaces.length
      ? [...preferred, ...rest]
      : rawPlaces;
  })();

  const parsed = smartResult?.parsed;

  const chipSm = "shrink-0 text-xs font-medium px-3 py-1.5 rounded-full border transition-all";
  const chipActive = { background: "var(--accent)", color: "#fff", borderColor: "var(--accent)" };
  const chipIdle = { background: "var(--surface)", color: "var(--text-muted)", borderColor: "var(--border)" };

  const CITIES = ["תל אביב","יפו","רמת גן","גבעתיים","בני ברק","פתח תקווה","ראשון לציון","חולון","בת ים","הרצליה","רעננה","כפר סבא","הוד השרון","נתניה","רחובות","נס ציונה","מודיעין"];

  return (
    <div>
      {/* Sticky search + filter header */}
      <div
        className="sticky top-14 z-30 px-4 pt-3 pb-2"
        style={{ background: "rgba(249,247,244,0.95)", backdropFilter: "blur(12px)", borderBottom: "1px solid var(--border)" }}
      >
        {/* Search bar full-width */}
        <form onSubmit={handleSearch} className="flex gap-2 mb-2.5">
          <div className="relative flex-1">
            <MagnifyingGlass
              size={15}
              className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none"
              style={{ color: "var(--text-faint)" }}
            />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="פסטה, סושי, חומוס יפו..."
              className="w-full rounded-xl pr-9 pl-4 py-2.5 text-sm focus:outline-none transition-colors"
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                color: "var(--text)",
              }}
              onFocus={e => (e.currentTarget.style.borderColor = "var(--accent)")}
              onBlur={e => (e.currentTarget.style.borderColor = "var(--border)")}
            />
          </div>
          <button
            type="submit"
            disabled={smartLoading}
            className="px-4 py-2.5 rounded-xl text-sm font-semibold shrink-0 disabled:opacity-60 transition-all active:scale-[0.97]"
            style={{ background: "var(--accent)", color: "#fff" }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--accent-dark)")}
            onMouseLeave={e => (e.currentTarget.style.background = "var(--accent)")}
          >
            {smartLoading ? "..." : "חיפוש"}
          </button>
        </form>

        {/* Single scrolling filter row */}
        <div className="flex gap-2 overflow-x-auto no-scrollbar -mx-4 px-4 pb-1">
          {/* Open now */}
          <button
            onClick={() => setOpenNow((v) => !v)}
            className={chipSm}
            style={openNow ? { background: "#15803d", color: "#fff", borderColor: "#15803d" } : chipIdle}
          >
            פתוח עכשיו
          </button>

          {/* Near me */}
          <button
            onClick={handleNearMe}
            disabled={gpsLoading}
            className={`${chipSm} flex items-center gap-1 disabled:opacity-50`}
            style={userLat != null ? chipActive : chipIdle}
          >
            <MapPin size={11} weight={userLat != null ? "fill" : "regular"} />
            {gpsLoading ? "מאתר..." : userLat != null ? "קרוב אליי ×" : "קרוב אליי"}
          </button>

          {/* Sort */}
          <select
            value={sortMode}
            onChange={e => { setSortMode(e.target.value); setSmartResult(null); }}
            className={`${chipSm} cursor-pointer focus:outline-none`}
            style={sortMode
              ? { background: "var(--accent-light)", borderColor: "var(--accent-muted)", color: "var(--accent)" }
              : chipIdle}
          >
            <option value="">מיין לפי</option>
            <option value="rating">הכי מדורגות</option>
            <option value="trending">חם עכשיו</option>
            <option value="hidden_gems">פנינים נסתרות</option>
            <option value="new">חדש ב-Reco</option>
          </select>

          {/* Divider */}
          <div className="w-px shrink-0 self-stretch" style={{ background: "var(--border)" }} />

          {/* City chips inline */}
          {CITIES.map(city => (
            <button
              key={city}
              onClick={() => setCityFilter(cityFilter === city ? "" : city)}
              className={chipSm}
              style={cityFilter === city ? chipActive : chipIdle}
            >
              {city}
            </button>
          ))}
        </div>
      </div>

      {/* Category row */}
      <div className="px-4 pt-3 pb-1">
        <CategoryRow selected={selectedCategory} onSelect={handleCategorySelect} />
      </div>

      {/* Subcategory chips */}
      {selectedCategory && (
        <div className="px-4 pb-2">
          <SubcategoryChips
            categoryId={selectedCategory}
            selected={selectedSub}
            onSelect={setSelectedSub}
          />
        </div>
      )}

      {/* Active filter summary + view toggle */}
      <div className="px-4 py-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-wrap flex-1 min-w-0">
          {parsed && (
            <>
              {parsed.dish && (
                <span className="text-xs px-2.5 py-1 rounded-full font-medium" style={{ background: "var(--accent-light)", color: "var(--accent)" }}>
                  {parsed.dish}
                </span>
              )}
              {parsed.cuisine && !parsed.dish && (
                <span className="text-xs px-2.5 py-1 rounded-full font-medium" style={{ background: "var(--accent-light)", color: "var(--accent)" }}>
                  {parsed.cuisine}
                </span>
              )}
              {(parsed.price_min_ils || parsed.price_max_ils) && (
                <span className="text-xs px-2.5 py-1 rounded-full font-medium" style={{ background: "#dcfce7", color: "#15803d" }}>
                  {parsed.price_min_ils && parsed.price_max_ils
                    ? `${parsed.price_min_ils}–${parsed.price_max_ils} ₪`
                    : parsed.price_max_ils
                    ? `עד ${parsed.price_max_ils} ₪`
                    : `מ-${parsed.price_min_ils} ₪`}
                </span>
              )}
              {parsed.city && (
                <span className="text-xs px-2.5 py-1 rounded-full font-medium" style={{ background: "var(--accent-light)", color: "var(--accent)" }}>
                  {parsed.city}
                </span>
              )}
              {parsed.party_size != null && (
                <span className="text-xs px-2.5 py-1 rounded-full" style={{ background: "var(--border)", color: "var(--text-muted)" }}>
                  {parsed.party_size} סועדים
                </span>
              )}
              {parsed.open_at_hour != null && (() => {
                const DAY_NAMES = ["ראשון","שני","שלישי","רביעי","חמישי","שישי","שבת"];
                const todayGoogle = new Date().getDay();
                const dayLabel = parsed.open_at_day === todayGoogle ? "היום"
                  : parsed.open_at_day === (todayGoogle + 1) % 7 ? "מחר"
                  : parsed.open_at_day != null ? DAY_NAMES[parsed.open_at_day] : "היום";
                return (
                  <span className="text-xs px-2.5 py-1 rounded-full" style={{ background: "#fef9c3", color: "#a16207" }}>
                    {dayLabel} ב-{String(parsed.open_at_hour).padStart(2,"0")}:00
                  </span>
                );
              })()}
              <button
                onClick={clearSmartSearch}
                className="flex items-center gap-0.5 text-xs"
                style={{ color: "var(--text-faint)" }}
              >
                <X size={11} /> נקה
              </button>
            </>
          )}

          {!smartResult && (cityFilter || cuisineFilter || search) && (
            <>
              {cityFilter && (
                <span className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-full font-medium" style={{ background: "var(--accent-light)", color: "var(--accent)" }}>
                  {cityFilter}
                  <button onClick={() => setCityFilter("")} className="flex items-center opacity-60 hover:opacity-100"><X size={10} /></button>
                </span>
              )}
              {cuisineFilter && (
                <span className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-full font-medium" style={{ background: "var(--accent-light)", color: "var(--accent)" }}>
                  {cuisineFilter}
                  <button onClick={() => { setSelectedCategory(null); setSelectedSub(null); }} className="flex items-center opacity-60 hover:opacity-100"><X size={10} /></button>
                </span>
              )}
              {search && (
                <span className="text-xs" style={{ color: "var(--text-faint)" }}>
                  {fastPlaces.length} תוצאות
                </span>
              )}
            </>
          )}
        </div>

        {/* View toggle - compact, right side */}
        <div className="flex shrink-0 gap-1">
          <button
            onClick={() => setView("grid")}
            className="w-8 h-8 flex items-center justify-center rounded-lg transition-all"
            style={view === "grid"
              ? { background: "var(--accent)", color: "#fff" }
              : { background: "transparent", color: "var(--text-faint)" }}
            title="תצוגת רשת"
          >
            <GridFour size={16} />
          </button>
          <button
            onClick={() => setView("map")}
            className="w-8 h-8 flex items-center justify-center rounded-lg transition-all"
            style={view === "map"
              ? { background: "var(--accent)", color: "#fff" }
              : { background: "transparent", color: "var(--text-faint)" }}
            title="תצוגת מפה"
          >
            <MapTrifold size={16} />
          </button>
        </div>
      </div>

      {/* Content area */}
      <div className="px-4 pb-10">
        {/* Map view */}
        {view === "map" && <MapView places={allPlaces} />}

        {/* Smart search results */}
        {smartResult && !smartLoading && view === "grid" && (
          <>
            {smartResult.exact.length > 0 ? (
              <section className="mb-6">
                <p className="text-xs font-medium mb-3" style={{ color: "var(--text-faint)" }}>
                  {smartResult.exact.length} תוצאות מדויקות
                </p>
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
              <p className="text-sm mb-4 rounded-xl px-4 py-3" style={{ background: "var(--accent-light)", color: "var(--accent)" }}>
                לא נמצאו תוצאות מדויקות — הנה מקומות שאולי יתאימו:
              </p>
            )}

            {smartResult.similar.length > 0 && (
              <section className="mb-6">
                {smartResult.exact.length > 0 && (
                  <p className="text-xs font-medium mb-3" style={{ color: "var(--text-faint)" }}>
                    {smartResult.similar.length} תוצאות דומות
                  </p>
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
              <div className="text-center py-16" style={{ color: "var(--text-faint)" }}>
                <p className="text-base mb-1">לא נמצאו תוצאות</p>
                <p className="text-sm">נסה לשנות את החיפוש</p>
              </div>
            )}
          </>
        )}

        {/* Regular grid */}
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

        {/* Smart search loading */}
        {smartLoading && (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <div
              className="w-7 h-7 border-[3px] rounded-full animate-spin"
              style={{ borderColor: "var(--border)", borderTopColor: "var(--accent)" }}
            />
            <p className="text-sm" style={{ color: "var(--text-faint)" }}>מנתח את החיפוש שלך...</p>
          </div>
        )}
      </div>
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
