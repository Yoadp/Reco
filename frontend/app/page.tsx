"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { MagnifyingGlass, ArrowLeft, Sparkle, UserCircle } from "@phosphor-icons/react";
import { searchPlaces, getMe, photoUrl, type Place } from "@/lib/api";

function PlacePhotoCard({ place }: { place: Place }) {
  const photo = photoUrl(place.photos?.[0]);
  return (
    <Link
      href={`/places/${place.slug}`}
      className="relative block rounded-xl overflow-hidden hover:scale-[1.02] transition-transform duration-200 active:scale-[0.98] aspect-[2/3]"
    >
      {photo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={photo} alt={place.name} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full" style={{ background: "var(--border)" }} />
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black/65 via-black/10 to-transparent" />
      <div className="absolute bottom-0 left-0 right-0 p-3 text-white">
        <p className="font-semibold text-xs leading-tight truncate">{place.name}</p>
        <div className="flex items-center justify-between mt-0.5">
          <span className="text-[10px] text-white/65 truncate">{place.cuisine?.[0] ?? place.city ?? ""}</span>
          {place.aggregated_score && (
            <span className="text-[10px] font-bold text-amber-300 shrink-0">★ {place.aggregated_score.toFixed(1)}</span>
          )}
        </div>
      </div>
    </Link>
  );
}

function PlaceWideCard({ place }: { place: Place }) {
  const photo = photoUrl(place.photos?.[0]);
  return (
    <Link
      href={`/places/${place.slug}`}
      className="relative block rounded-xl overflow-hidden hover:scale-[1.02] transition-transform duration-200 active:scale-[0.98] h-44"
    >
      {photo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={photo} alt={place.name} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full" style={{ background: "var(--border)" }} />
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black/65 via-black/10 to-transparent" />
      <div className="absolute bottom-0 left-0 right-0 p-3 text-white">
        <p className="font-semibold text-base leading-tight truncate">{place.name}</p>
        <span className="text-xs text-white/65">{place.city} · {place.cuisine?.[0] ?? ""}</span>
      </div>
      {place.aggregated_score && (
        <span className="absolute top-1.5 right-1.5 text-[10px] font-bold text-amber-300 bg-black/40 px-1.5 py-0.5 rounded-full">
          ★ {place.aggregated_score.toFixed(1)}
        </span>
      )}
    </Link>
  );
}

function DiscoverySection({
  title,
  sort,
  description,
  layout = "grid",
  headingSize = "md",
}: {
  title: string;
  sort: string;
  description: string;
  layout?: "grid" | "featured";
  headingSize?: "sm" | "md" | "lg";
}) {
  const { data: places = [], isLoading } = useQuery({
    queryKey: ["discovery", sort],
    queryFn: () => searchPlaces({ sort, limit: 8 }),
    staleTime: 5 * 60 * 1000,
  });

  const skeletonCount = layout === "featured" ? 3 : 4;
  const headingClass =
    headingSize === "lg"
      ? "text-2xl font-bold"
      : headingSize === "sm"
      ? "text-base font-semibold"
      : "text-xl font-bold";

  return (
    <section className="mb-14">
      <div className="flex items-end justify-between mb-5">
        <div>
          <h2 className={headingClass} style={{ color: "var(--text)" }}>{title}</h2>
          <p className="text-sm mt-0.5" style={{ color: "var(--text-faint)" }}>{description}</p>
        </div>
        <Link
          href={`/restaurants?sort=${sort}`}
          className="flex items-center gap-1 text-sm font-medium shrink-0 pb-0.5 transition-opacity hover:opacity-70"
          style={{ color: "var(--accent)" }}
        >
          הכל
          <ArrowLeft size={14} />
        </Link>
      </div>

      {isLoading ? (
        <div className={`grid gap-2 ${layout === "featured" ? "grid-cols-3" : "grid-cols-4"}`}>
          {Array.from({ length: skeletonCount }).map((_, i) => (
            <div
              key={i}
              className={`rounded-xl animate-pulse ${layout === "featured" ? "h-36" : "aspect-[2/3]"}`}
              style={{ background: "var(--border)" }}
            />
          ))}
        </div>
      ) : places.length === 0 ? null : layout === "featured" ? (
        <div className="grid grid-cols-3 gap-2">
          {places.slice(0, 3).map((p) => (
            <PlaceWideCard key={p.id} place={p} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-2">
          {places.slice(0, 4).map((p) => (
            <PlacePhotoCard key={p.id} place={p} />
          ))}
        </div>
      )}
    </section>
  );
}

function HeroMosaic() {
  const { data: places = [] } = useQuery({
    queryKey: ["discovery", "trending"],
    queryFn: () => searchPlaces({ sort: "trending", limit: 12 }),
    staleTime: 5 * 60 * 1000,
  });

  const photos = places.map((p) => photoUrl(p.photos?.[0])).filter(Boolean).slice(0, 6) as string[];
  if (photos.length === 0) return null;

  return (
    <div
      className="absolute inset-0 grid gap-0.5 opacity-35"
      style={{ gridTemplateColumns: `repeat(${photos.length}, 1fr)` }}
    >
      {photos.map((url, i) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={i}
          src={url}
          alt=""
          aria-hidden
          className="w-full h-full object-cover"
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = "0"; }}
        />
      ))}
    </div>
  );
}

function ForYouSection() {
  const [token, setToken] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    setToken(localStorage.getItem("token"));
  }, []);

  const { data: profile } = useQuery({
    queryKey: ["me"],
    queryFn: getMe,
    enabled: !!token,
    retry: false,
  });

  const topCuisine = profile?.cuisine_preferences?.[0];

  const { data: places = [], isLoading } = useQuery({
    queryKey: ["forYou", topCuisine],
    queryFn: () => searchPlaces({ cuisine: topCuisine!, limit: 8 }),
    enabled: !!topCuisine,
    staleTime: 5 * 60 * 1000,
  });

  if (token === undefined) return null;

  if (!token) {
    return (
      <section className="mb-14 rounded-2xl p-6 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <div className="flex justify-center mb-3">
          <div className="w-11 h-11 rounded-full flex items-center justify-center" style={{ background: "var(--accent-light)" }}>
            <Sparkle size={22} weight="fill" style={{ color: "var(--accent)" }} />
          </div>
        </div>
        <h3 className="text-base font-semibold mb-1" style={{ color: "var(--text)" }}>המלצות שמחכות לך</h3>
        <p className="text-sm mb-5" style={{ color: "var(--text-muted)" }}>הצטרף כדי לקבל הצעות מותאמות לטעם שלך</p>
        <Link
          href="/register"
          className="inline-block text-sm font-semibold px-6 py-2.5 rounded-full transition-all active:scale-[0.97]"
          style={{ background: "var(--accent)", color: "#fff" }}
          onMouseEnter={e => (e.currentTarget.style.background = "var(--accent-dark)")}
          onMouseLeave={e => (e.currentTarget.style.background = "var(--accent)")}
        >
          הרשמה בחינם
        </Link>
      </section>
    );
  }

  if (profile && !topCuisine) {
    return (
      <section className="mb-14 rounded-2xl p-6 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <div className="flex justify-center mb-3">
          <div className="w-11 h-11 rounded-full flex items-center justify-center" style={{ background: "var(--accent-light)" }}>
            <UserCircle size={22} weight="fill" style={{ color: "var(--accent)" }} />
          </div>
        </div>
        <h3 className="text-base font-semibold mb-1" style={{ color: "var(--text)" }}>ספר לנו מה אתה אוהב</h3>
        <p className="text-sm mb-5" style={{ color: "var(--text-muted)" }}>הגדר טעמים כדי לקבל המלצות אישיות</p>
        <Link
          href="/profile"
          className="inline-block text-sm font-semibold px-6 py-2.5 rounded-full transition-all active:scale-[0.97]"
          style={{ background: "var(--accent)", color: "#fff" }}
          onMouseEnter={e => (e.currentTarget.style.background = "var(--accent-dark)")}
          onMouseLeave={e => (e.currentTarget.style.background = "var(--accent)")}
        >
          הגדר טעמים
        </Link>
      </section>
    );
  }

  if (!topCuisine || (!isLoading && places.length === 0)) return null;

  return (
    <section className="mb-14">
      <div className="flex items-end justify-between mb-5">
        <div>
          <h2 className="text-xl font-bold" style={{ color: "var(--text)" }}>בשבילך</h2>
          <p className="text-sm mt-0.5" style={{ color: "var(--text-faint)" }}>על בסיס {topCuisine}</p>
        </div>
        <Link
          href={`/restaurants?cuisine=${encodeURIComponent(topCuisine)}`}
          className="flex items-center gap-1 text-sm font-medium shrink-0 pb-0.5 transition-opacity hover:opacity-70"
          style={{ color: "var(--accent)" }}
        >
          הכל
          <ArrowLeft size={14} />
        </Link>
      </div>
      {isLoading ? (
        <div className="grid grid-cols-4 gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-xl animate-pulse aspect-[2/3]" style={{ background: "var(--border)" }} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-2">
          {places.slice(0, 4).map((p) => (
            <PlacePhotoCard key={p.id} place={p} />
          ))}
        </div>
      )}
    </section>
  );
}

export default function HomePage() {
  const [q, setQ] = useState("");
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const router = useRouter();

  useEffect(() => {
    setIsLoggedIn(!!localStorage.getItem("token"));
  }, []);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const term = q.trim();
    router.push(term ? `/restaurants?q=${encodeURIComponent(term)}&nlp=true` : "/restaurants");
  }

  return (
    <div className="flex flex-col">
      {/* Hero */}
      <section className="relative overflow-hidden min-h-[360px] flex items-center" style={{ background: "#16130F" }}>
        <HeroMosaic />
        {/* Directional overlay: heavier on the right (RTL), lighter on the left where text is */}
        <div className="absolute inset-0" style={{
          background: "linear-gradient(to left, rgba(22,19,15,0.95) 0%, rgba(22,19,15,0.75) 40%, rgba(22,19,15,0.55) 100%)"
        }} />

        <div className="relative z-10 w-full max-w-3xl mx-auto px-5 py-16 md:py-20">
          {/* Text: right-aligned (RTL = right is the natural start) */}
          <div className="max-w-lg mr-0 ml-auto text-right md:text-right">
            <h1 className="text-3xl md:text-4xl font-bold text-white leading-tight mb-3">
              גלה את המקומות הטובים ביותר
            </h1>
            <p className="text-base text-white/65 mb-7 leading-relaxed">
              המלצות אמיתיות מאנשים אמיתיים. דרג, המלץ וצבור נקודות.
            </p>

            <form onSubmit={handleSearch} className="flex gap-2">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="פסטה בתל אביב, סושי, חומוס יפו..."
                className="flex-1 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 min-w-0"
                style={{
                  background: "rgba(255,255,255,0.1)",
                  border: "1px solid rgba(255,255,255,0.18)",
                  color: "#fff",
                  caretColor: "#fff",
                }}
                dir="rtl"
              />
              <button
                type="submit"
                className="flex items-center gap-2 px-5 py-3 rounded-xl text-sm font-semibold shrink-0 transition-all active:scale-[0.97]"
                style={{ background: "var(--accent)", color: "#fff" }}
                onMouseEnter={e => (e.currentTarget.style.background = "var(--accent-dark)")}
                onMouseLeave={e => (e.currentTarget.style.background = "var(--accent)")}
              >
                <MagnifyingGlass size={15} weight="bold" />
                חפש
              </button>
            </form>

            <div className="mt-4">
              <Link
                href="/restaurants"
                className="text-sm text-white/50 hover:text-white/80 transition-colors"
              >
                או עיין בכל המסעדות
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Discovery sections */}
      <div className="max-w-3xl mx-auto px-4 pt-12 pb-6 w-full">
        <ForYouSection />

        <DiscoverySection
          title="חם עכשיו"
          sort="trending"
          description="הפופולריים השבוע"
          layout="grid"
          headingSize="lg"
        />

        <DiscoverySection
          title="פנינים נסתרות"
          sort="hidden_gems"
          description="ציוני מעולים שעוד לא כולם מכירים"
          layout="featured"
          headingSize="md"
        />

        <DiscoverySection
          title="חדש ב-Reco"
          sort="new"
          description="נוספו לאחרונה"
          layout="grid"
          headingSize="sm"
        />
      </div>

      {/* Join CTA */}
      <section className="mt-4 mb-0 mx-4 md:mx-auto md:max-w-3xl rounded-2xl overflow-hidden mb-10">
        <div className="relative px-8 py-12 text-center" style={{ background: "var(--text)" }}>
          {isLoggedIn ? (
            <>
              <h2 className="text-2xl font-bold text-white mb-2">מה אוכלים הערב?</h2>
              <p className="mb-7" style={{ color: "rgba(255,255,255,0.55)" }}>
                חפש, גלה, ושתף המלצות עם הקהילה
              </p>
              <div className="flex justify-center gap-3">
                <Link
                  href="/restaurants"
                  className="text-sm font-semibold px-6 py-2.5 rounded-full transition-all active:scale-[0.97]"
                  style={{ background: "var(--accent)", color: "#fff" }}
                  onMouseEnter={e => (e.currentTarget.style.background = "var(--accent-dark)")}
                  onMouseLeave={e => (e.currentTarget.style.background = "var(--accent)")}
                >
                  גלה מסעדות
                </Link>
                <Link
                  href="/profile"
                  className="text-sm font-semibold px-6 py-2.5 rounded-full border transition-all"
                  style={{ borderColor: "rgba(255,255,255,0.25)", color: "#fff" }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.5)"; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.25)"; }}
                >
                  הפרופיל שלי
                </Link>
              </div>
            </>
          ) : (
            <>
              <h2 className="text-2xl font-bold text-white mb-2">מוכן להתחיל?</h2>
              <p className="mb-7" style={{ color: "rgba(255,255,255,0.55)" }}>
                הצטרף לקהילה וצבור נקודות על המלצות מדויקות
              </p>
              <div className="flex justify-center gap-3">
                <Link
                  href="/register"
                  className="text-sm font-semibold px-6 py-2.5 rounded-full transition-all active:scale-[0.97]"
                  style={{ background: "var(--accent)", color: "#fff" }}
                  onMouseEnter={e => (e.currentTarget.style.background = "var(--accent-dark)")}
                  onMouseLeave={e => (e.currentTarget.style.background = "var(--accent)")}
                >
                  הרשמה בחינם
                </Link>
                <Link
                  href="/restaurants"
                  className="text-sm font-semibold px-6 py-2.5 rounded-full border transition-all"
                  style={{ borderColor: "rgba(255,255,255,0.25)", color: "#fff" }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.5)"; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.25)"; }}
                >
                  גלה מסעדות
                </Link>
              </div>
            </>
          )}
        </div>
      </section>
      <div className="h-10" />
    </div>
  );
}
