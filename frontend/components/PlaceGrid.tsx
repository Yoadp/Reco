"use client";

import Link from "next/link";
import { type Place } from "@/lib/api";
import { getPlaceGradient, getPlaceEmoji } from "@/lib/categories";

const PRICE = ["", "₪", "₪₪", "₪₪₪", "₪₪₪₪"];

function scoreColor(score: number | null): string {
  if (!score) return "bg-white/70 text-gray-700";
  if (score >= 4.5) return "bg-green-500 text-white";
  if (score >= 3.5) return "bg-amber-500 text-white";
  return "bg-red-500 text-white";
}

function PlaceCard({ place }: { place: Place }) {
  const gradient = getPlaceGradient(place.cuisine);
  const emoji = getPlaceEmoji(place.cuisine);
  const sourceCount = place.sources?.length ?? 0;

  return (
    <Link
      href={`/places/${place.slug}`}
      className="block rounded-2xl overflow-hidden shadow-md hover:shadow-xl transition-shadow active:scale-[0.98] transition-transform"
    >
      {/* Top gradient half */}
      <div className={`relative aspect-square bg-gradient-to-br ${gradient} flex flex-col`}>
        {/* Score badge top-left */}
        {place.aggregated_score && (
          <span className={`absolute top-2 right-2 text-xs font-bold px-2 py-0.5 rounded-full ${scoreColor(place.aggregated_score)}`}>
            ★ {place.aggregated_score.toFixed(1)}
          </span>
        )}

        {/* Source count badge top-right */}
        {sourceCount > 0 && (
          <span className="absolute top-2 left-2 text-xs bg-black/20 text-white px-1.5 py-0.5 rounded-full">
            {sourceCount} מקורות
          </span>
        )}

        {/* Emoji + name centered */}
        <div className="flex-1 flex flex-col items-center justify-center px-2 gap-2 pb-2">
          <span className="text-5xl">{emoji}</span>
          <h3 className="font-extrabold text-gray-800 text-center text-sm leading-tight line-clamp-2 w-full px-1">
            {place.name}
          </h3>
        </div>

        {/* Bottom info strip */}
        <div className="bg-white/60 backdrop-blur-sm px-3 py-2 flex items-center justify-between gap-1">
          {place.cuisine && place.cuisine.length > 0 && (
            <span className="text-xs text-gray-600 truncate">{place.cuisine[0]}</span>
          )}
          <div className="flex items-center gap-1.5 shrink-0">
            {place.price_range && (
              <span className="text-xs text-gray-500 font-medium">{PRICE[place.price_range]}</span>
            )}
          </div>
        </div>
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
          <div key={i} className="aspect-square rounded-2xl bg-gray-100 animate-pulse" />
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
