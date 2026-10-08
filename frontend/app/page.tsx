"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { searchPlaces, photoUrl, type Place } from "@/lib/api";

function PlacePhotoCard({ place }: { place: Place }) {
  const photo = photoUrl(place.photos?.[0]);
  return (
    <Link
      href={`/places/${place.slug}`}
      className="relative block rounded-2xl overflow-hidden shadow-md hover:shadow-xl hover:-translate-y-0.5 transition-all duration-200 aspect-[3/4]"
    >
      {photo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={photo} alt={place.name} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full bg-gray-200" />
      )}
      {/* gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
      <div className="absolute bottom-0 left-0 right-0 p-3 text-white">
        <p className="font-bold text-sm leading-tight truncate">{place.name}</p>
        <div className="flex items-center justify-between mt-0.5">
          <span className="text-xs text-white/70 truncate">{place.cuisine?.[0] ?? place.city ?? ""}</span>
          {place.aggregated_score && (
            <span className="text-xs font-bold text-yellow-300 shrink-0">★ {place.aggregated_score.toFixed(1)}</span>
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
      className="relative block rounded-2xl overflow-hidden shadow-md hover:shadow-xl hover:-translate-y-0.5 transition-all duration-200 h-44"
    >
      {photo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={photo} alt={place.name} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full bg-gray-200" />
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
      <div className="absolute bottom-0 left-0 right-0 p-3 text-white">
        <p className="font-bold text-base leading-tight truncate">{place.name}</p>
        <div className="flex items-center justify-between mt-0.5">
          <span className="text-xs text-white/70 truncate">{place.city} · {place.cuisine?.[0] ?? ""}</span>
          {place.aggregated_score && (
            <span className="text-xs font-bold text-yellow-300 shrink-0">★ {place.aggregated_score.toFixed(1)}</span>
          )}
        </div>
      </div>
    </Link>
  );
}

function DiscoverySection({
  title,
  sort,
  description,
  layout = "grid",
}: {
  title: string;
  sort: string;
  description: string;
  layout?: "grid" | "featured";
}) {
  const { data: places = [], isLoading } = useQuery({
    queryKey: ["discovery", sort],
    queryFn: () => searchPlaces({ sort, limit: 8 }),
    staleTime: 5 * 60 * 1000,
  });

  const skeletonCount = layout === "featured" ? 3 : 4;

  return (
    <section className="mb-12">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-extrabold text-gray-900">{title}</h2>
          <p className="text-sm text-gray-400 mt-0.5">{description}</p>
        </div>
        <Link
          href={`/restaurants?sort=${sort}`}
          className="text-sm text-indigo-600 font-medium hover:underline shrink-0"
        >
          הכל ←
        </Link>
      </div>

      {isLoading ? (
        <div className={layout === "featured" ? "grid grid-cols-2 gap-3 sm:grid-cols-3" : "grid grid-cols-2 gap-3 sm:grid-cols-4"}>
          {Array.from({ length: skeletonCount }).map((_, i) => (
            <div key={i} className={`rounded-2xl bg-gray-100 animate-pulse ${layout === "featured" ? "h-44" : "aspect-[3/4]"}`} />
          ))}
        </div>
      ) : places.length === 0 ? null : layout === "featured" ? (
        /* Featured layout: 1 big + 2 smaller or 3 equal wide cards */
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {places.slice(0, 3).map((p) => (
            <PlaceWideCard key={p.id} place={p} />
          ))}
        </div>
      ) : (
        /* Portrait grid: 4 tall cards */
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
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
    <div className="absolute inset-0 grid gap-0.5 opacity-40"
      style={{ gridTemplateColumns: `repeat(${photos.length}, 1fr)` }}>
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
      {/* Hero with photo mosaic background */}
      <section className="relative overflow-hidden bg-gray-900 px-4 py-20 text-center">
        <HeroMosaic />
        {/* dark overlay on top of mosaic */}
        <div className="absolute inset-0 bg-gradient-to-b from-gray-900/80 via-gray-900/60 to-gray-900/90" />

        <div className="relative z-10">
          <h1 className="text-4xl font-extrabold text-white mb-3 leading-tight">
            גלה את המקומות הטובים ביותר
          </h1>
          <p className="text-lg text-white/70 max-w-md mx-auto mb-8">
            המלצות אמיתיות מאנשים אמיתיים. דרג, המלץ וצבור נקודות.
          </p>

          <form onSubmit={handleSearch} className="flex max-w-lg mx-auto gap-2 mb-4">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="נסה: פסטה בתל אביב, סושי, חומוס יפו..."
              className="flex-1 border border-white/20 bg-white/10 backdrop-blur text-white placeholder-white/50 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-white/40"
              dir="rtl"
            />
            <button
              type="submit"
              className="bg-indigo-500 text-white px-6 py-3 rounded-xl text-sm font-semibold hover:bg-indigo-400 transition-colors shrink-0"
            >
              חפש
            </button>
          </form>

          <Link href="/restaurants" className="text-sm text-white/60 hover:text-white/90 transition-colors">
            או עיין בכל המסעדות ←
          </Link>
        </div>
      </section>

      {/* Discovery sections */}
      <div className="max-w-3xl mx-auto px-4 py-10 w-full">
        <DiscoverySection
          title="חם עכשיו"
          sort="trending"
          description="המקומות הפופולריים השבוע"
          layout="grid"
        />

        <DiscoverySection
          title="פנינים נסתרות"
          sort="hidden_gems"
          description="ציוני מעולים שעוד לא כולם מכירים"
          layout="featured"
        />

        <DiscoverySection
          title="חדש ב-Reco"
          sort="new"
          description="מסעדות שהתווספו לאחרונה"
          layout="grid"
        />
      </div>

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
