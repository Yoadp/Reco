"use client";

import Link from "next/link";
import { useState, useCallback } from "react";
import { type Place, savePlace, unsavePlace } from "@/lib/api";
import { getPlaceGradient, getPlaceEmoji } from "@/lib/categories";

const PRICE = ["", "₪", "₪₪", "₪₪₪", "₪₪₪₪"];

function scoreColor(score: number | null): string {
  if (!score) return "bg-gray-200 text-gray-600";
  if (score >= 4.7) return "bg-green-600 text-white";
  if (score >= 4.0) return "bg-green-500 text-white";
  if (score >= 3.5) return "bg-amber-500 text-white";
  return "bg-red-500 text-white";
}

function isOpenNow(hours: Record<string, unknown> | null): boolean | null {
  if (!hours || !Array.isArray(hours.periods)) return null;

  const now = new Date();
  // Convert JS day (0=Sun) to same format as Google (0=Sun) — they match
  const today = now.getDay();
  const currentMins = now.getHours() * 60 + now.getMinutes();

  // Note: JS uses local time; for Israel the server is already in the right TZ for open/closed display purposes.
  // The browser will use the user's local clock which is typically also Israel time.
  for (const period of hours.periods as Array<Record<string, Record<string, number>>>) {
    const openDay = period.open?.day;
    const openMins = (period.open?.hour ?? 0) * 60 + (period.open?.minute ?? 0);
    const closeInfo = period.close;

    if (!closeInfo) return true; // 24/7

    const closeDay = closeInfo.day;
    const closeMins = (closeInfo.hour ?? 0) * 60 + (closeInfo.minute ?? 0);

    if (openDay === closeDay) {
      if (today === openDay && openMins <= currentMins && currentMins < closeMins) return true;
    } else {
      if (today === openDay && currentMins >= openMins) return true;
      if (today === closeDay && currentMins < closeMins) return true;
    }
  }
  return false;
}

function distanceKm(
  userLat: number, userLng: number,
  placeLat: number | null, placeLng: number | null
): number | null {
  if (!placeLat || !placeLng) return null;
  const R = 6371;
  const dLat = ((placeLat - userLat) * Math.PI) / 180;
  const dLng = ((placeLng - userLng) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((userLat * Math.PI) / 180) *
      Math.cos((placeLat * Math.PI) / 180) *
      Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

interface PlaceCardProps {
  place: Place;
  savedIds?: Set<string>;
  isLoggedIn?: boolean;
  userLat?: number | null;
  userLng?: number | null;
  onSaveToggle?: (placeId: string, listType: string, saved: boolean) => void;
}

function PlaceCard({ place, savedIds, isLoggedIn, userLat, userLng, onSaveToggle }: PlaceCardProps) {
  const gradient = getPlaceGradient(place.cuisine);
  const emoji = getPlaceEmoji(place.cuisine);
  const openStatus = isOpenNow(place.hours);
  const dist = userLat != null && userLng != null ? distanceKm(userLat, userLng, place.lat, place.lng) : null;
  const isSaved = savedIds?.has(place.id) ?? false;
  const [saving, setSaving] = useState(false);

  const handleHeart = useCallback(
    async (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (!isLoggedIn || saving) return;
      setSaving(true);
      try {
        if (isSaved) {
          await unsavePlace(place.id, "wishlist");
          onSaveToggle?.(place.id, "wishlist", false);
        } else {
          await savePlace(place.id, "wishlist");
          onSaveToggle?.(place.id, "wishlist", true);
        }
      } finally {
        setSaving(false);
      }
    },
    [isSaved, isLoggedIn, saving, place.id, onSaveToggle]
  );

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

        {/* Heart / save button */}
        {isLoggedIn && (
          <button
            onClick={handleHeart}
            className={`absolute top-2 left-2 w-7 h-7 flex items-center justify-center rounded-full transition-all ${
              isSaved ? "bg-red-500 text-white" : "bg-white/80 text-gray-400 hover:text-red-400"
            } ${saving ? "opacity-50" : ""}`}
            aria-label={isSaved ? "הסר מהרשימה" : "שמור"}
          >
            {isSaved ? "♥" : "♡"}
          </button>
        )}

        <span className="text-4xl mb-2">{emoji}</span>
        <h3 className="font-extrabold text-gray-800 text-center text-sm leading-tight line-clamp-2 w-full px-1">
          {place.name}
        </h3>
      </div>

      {/* Info strip */}
      <div className="px-3 py-2.5 bg-white">
        <div className="flex items-center justify-between gap-1 mb-1">
          <div className="min-w-0 flex-1">
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

        {/* Open status + distance row */}
        <div className="flex items-center gap-2 mt-1">
          {openStatus !== null && (
            <span className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${openStatus ? "bg-green-100 text-green-700" : "bg-red-50 text-red-500"}`}>
              {openStatus ? "● פתוח" : "● סגור"}
            </span>
          )}
          {dist !== null && (
            <span className="text-xs text-indigo-500 font-medium">
              📍 {dist < 1 ? `${Math.round(dist * 1000)} מ'` : `${dist.toFixed(1)} ק״מ`}
            </span>
          )}
        </div>

        {/* Matched dishes badge */}
        {place.matched_dishes && place.matched_dishes.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {place.matched_dishes.slice(0, 3).map((dish) => (
              <span
                key={dish}
                className="text-xs bg-orange-50 text-orange-700 border border-orange-200 px-1.5 py-0.5 rounded-full truncate max-w-[90px]"
                title={dish}
              >
                {dish}
              </span>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}

interface Props {
  places: Place[];
  isLoading: boolean;
  savedIds?: Set<string>;
  isLoggedIn?: boolean;
  userLat?: number | null;
  userLng?: number | null;
  onSaveToggle?: (placeId: string, listType: string, saved: boolean) => void;
}

export default function PlaceGrid({ places, isLoading, savedIds, isLoggedIn, userLat, userLng, onSaveToggle }: Props) {
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
        <PlaceCard
          key={p.id}
          place={p}
          savedIds={savedIds}
          isLoggedIn={isLoggedIn}
          userLat={userLat}
          userLng={userLng}
          onSaveToggle={onSaveToggle}
        />
      ))}
    </div>
  );
}
