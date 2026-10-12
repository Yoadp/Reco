"use client";

import Link from "next/link";
import { useState, useCallback } from "react";
import { Heart, MapPin, ForkKnife } from "@phosphor-icons/react";
import { type Place, savePlace, unsavePlace, photoUrl } from "@/lib/api";
import { getPlaceGradient, getPlaceEmoji } from "@/lib/categories";

const PRICE = ["", "₪", "₪₪", "₪₪₪", "₪₪₪₪"];

function isOpenNow(hours: Record<string, unknown> | null): boolean | null {
  if (!hours || !Array.isArray(hours.periods)) return null;
  const now = new Date();
  const today = now.getDay();
  const currentMins = now.getHours() * 60 + now.getMinutes();
  for (const period of hours.periods as Array<Record<string, Record<string, number>>>) {
    const openDay = period.open?.day;
    const openMins = (period.open?.hour ?? 0) * 60 + (period.open?.minute ?? 0);
    const closeInfo = period.close;
    if (!closeInfo) return true;
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
  const photo = photoUrl(place.photos?.[0]);
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
      className="relative block rounded-xl overflow-hidden aspect-[3/4] hover:scale-[1.02] transition-transform duration-200 active:scale-[0.98]"
    >
      {/* Photo or gradient fill */}
      {photo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={photo}
          alt={place.name}
          className="absolute inset-0 w-full h-full object-cover"
          onError={(e) => {
            const el = e.currentTarget as HTMLImageElement;
            el.style.display = "none";
            const fb = el.nextElementSibling as HTMLElement | null;
            if (fb) fb.style.display = "flex";
          }}
        />
      ) : null}
      <div
        className={`absolute inset-0 bg-gradient-to-br ${gradient} flex items-center justify-center`}
        style={{ display: photo ? "none" : "flex" }}
      >
        <span className="text-5xl">{emoji}</span>
      </div>

      {/* Gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/15 to-transparent" />

      {/* Score top-right */}
      {place.aggregated_score && (
        <span className="absolute top-2.5 right-2.5 text-xs font-bold text-amber-300 bg-black/40 px-2 py-0.5 rounded-full backdrop-blur-sm">
          ★ {place.aggregated_score.toFixed(1)}
        </span>
      )}

      {/* Heart top-left */}
      {isLoggedIn && (
        <button
          onClick={handleHeart}
          className={`absolute top-2.5 left-2.5 w-7 h-7 flex items-center justify-center rounded-full backdrop-blur-sm transition-all ${saving ? "opacity-50" : ""}`}
          style={{
            background: isSaved ? "var(--accent)" : "rgba(255,255,255,0.8)",
            color: isSaved ? "#fff" : "var(--text-muted)",
          }}
          aria-label={isSaved ? "הסר מהרשימה" : "שמור"}
        >
          <Heart size={14} weight={isSaved ? "fill" : "regular"} />
        </button>
      )}

      {/* Bottom overlay: all info */}
      <div className="absolute bottom-0 left-0 right-0 p-3 text-white">
        {/* Meta row above name */}
        <div className="flex items-center gap-1.5 mb-1 flex-wrap">
          {place.cuisine && place.cuisine.length > 0 && (
            <span className="text-xs font-medium px-1.5 py-0.5 rounded-full bg-white/20 backdrop-blur-sm">
              {place.cuisine[0]}
            </span>
          )}
          {openStatus !== null && (
            <span
              className="text-xs font-medium px-1.5 py-0.5 rounded-full backdrop-blur-sm"
              style={openStatus
                ? { background: "rgba(21,128,61,0.75)" }
                : { background: "rgba(220,38,38,0.65)" }
              }
            >
              {openStatus ? "פתוח" : "סגור"}
            </span>
          )}
          {place.price_range && (
            <span className="text-xs font-semibold text-white/70">
              {PRICE[place.price_range]}
            </span>
          )}
          {dist !== null && (
            <span className="flex items-center gap-0.5 text-xs text-white/60">
              <MapPin size={10} weight="fill" />
              {dist < 1 ? `${Math.round(dist * 1000)} מ'` : `${dist.toFixed(1)} ק״מ`}
            </span>
          )}
        </div>

        <h3 className="font-semibold text-sm leading-tight line-clamp-2">{place.name}</h3>

        {place.city && (
          <p className="text-xs text-white/55 mt-0.5">{place.city}</p>
        )}

        {/* Matched dishes */}
        {place.matched_dishes && place.matched_dishes.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {place.matched_dishes.slice(0, 2).map((dish) => (
              <span
                key={dish}
                className="text-xs px-1.5 py-0.5 rounded-full truncate max-w-[80px] bg-white/15 backdrop-blur-sm"
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
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="rounded-xl animate-pulse aspect-[3/4]" style={{ background: "var(--border)" }} />
        ))}
      </div>
    );
  }

  if (places.length === 0) {
    return (
      <div className="py-16 text-center">
        <div className="flex justify-center mb-3">
          <ForkKnife size={36} style={{ color: "var(--text-faint)" }} />
        </div>
        <p style={{ color: "var(--text-muted)" }}>לא נמצאו מסעדות</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
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
