"use client";

import Link from "next/link";
import { type Place } from "@/lib/api";
import { getPlaceGradient, getPlaceEmoji } from "@/lib/categories";

const PRICE = ["", "₪", "₪₪", "₪₪₪", "₪₪₪₪"];

function scoreColor(score: number | null): string {
  if (!score) return "bg-gray-200 text-gray-600";
  if (score >= 4.7) return "bg-green-600 text-white";
  if (score >= 4.0) return "bg-green-500 text-white";
  if (score >= 3.5) return "bg-amber-500 text-white";
  return "bg-red-500 text-white";
}

function PlaceCard({ place }: { place: Place }) {
  const gradient = getPlaceGradient(place.cuisine);
  const emoji = getPlaceEmoji(place.cuisine);

  return (
    <Link
      href={`/places/${place.slug}`}
      className="block rounded-2xl overflow-hidden bg-white border border-gray-100 shadow-sm hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 active:scale-[0.98]"
    >
      {/* Gradient header with emoji */}
      <div className={`relative bg-gradient-to-br ${gradient} flex flex-col items-center justify-center pt-5 pb-3 px-2`}>
        {/* Score badge */}
        {place.aggregated_score && (
          <span className={`absolute top-2 right-2 text-xs font-bold px-2 py-0.5 rounded-full ${scoreColor(place.aggregated_score)}`}>
            ★ {place.aggregated_score.toFixed(1)}
          </span>
        )}

        <span className="text-4xl mb-2">{emoji}</span>
        <h3 className="font-extrabold text-gray-800 text-center text-sm leading-tight line-clamp-2 w-full px-1">
          {place.name}
        </h3>
      </div>

      {/* Info strip */}
      <div className="px-3 py-2.5 flex items-center justify-between gap-1 bg-white">
        <div className="min-w-0">
          {place.cuisine && place.cuisine.length > 0 && (
            <span className="text-xs text-gray-500 truncate block">{place.cuisine[0]}</span>
          )}
          {place.address && (
            <span className="text-xs text-gray-400 truncate block leading-tight mt-0.5">
              {place.address.split(",")[0]}
            </span>
          )}
        </div>
        {place.price_range && (
          <span className="text-sm font-semibold text-indigo-500 shrink-0">{PRICE[place.price_range]}</span>
        )}
      </div>
    </Link>
  );
}

interface Props {
  places: Place[];
  isLoading: boolean;
}

export default function PlaceGrid({ places, isLoading }: Props) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="rounded-2xl bg-gray-100 animate-pulse h-40" />
        ))}
      </div>
    );
  }

  if (places.length === 0) {
    return (
      <div className="py-16 text-center">
        <p className="text-4xl mb-3">🍽️</p>
        <p className="text-gray-500">לא נמצאו מסעדות</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {places.map((p) => (
        <PlaceCard key={p.id} place={p} />
      ))}
    </div>
  );
}
