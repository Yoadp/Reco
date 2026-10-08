"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { use } from "react";
import { useRouter } from "next/navigation";
import {
  getPlace, getRecommendations, createRecommendation, vote,
  getPlaceRating, ratePlace, getPlaceVisits, getPlaceMenu, getAvailability,
  type Recommendation, type DataSource, type UserVisit, type MenuItem,
} from "@/lib/api";
import PhotoGallery from "@/components/PhotoGallery";
import AISummaryCard from "@/components/AISummaryCard";
import BookingConfirmModal from "@/components/BookingConfirmModal";

const PRICE = ["", "₪", "₪₪", "₪₪₪", "₪₪₪₪"];

const RESERVATION_SOURCE_PRIORITY = ["tabit", "ontopo"] as const;
const MENU_LINK_TYPES = new Set(["menu_link"]);

function scoreColor(n: number) {
  if (n <= 4) return "bg-red-100 text-red-700 border-red-200 hover:bg-red-200";
  if (n <= 7) return "bg-amber-100 text-amber-700 border-amber-200 hover:bg-amber-200";
  return "bg-green-100 text-green-700 border-green-200 hover:bg-green-200";
}

function selectedColor(n: number) {
  if (n <= 4) return "bg-red-500 text-white border-red-500";
  if (n <= 7) return "bg-amber-500 text-white border-amber-500";
  return "bg-green-500 text-white border-green-500";
}

function isLoggedIn() {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem("token");
}

function isPastOrToday(dateStr: string | null): boolean {
  if (!dateStr) return false;
  return dateStr <= new Date().toISOString().split("T")[0];
}

// ─── Source Cards ──────────────────────────────────────────────────────────

const SOURCE_STYLES: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  google_places: { bg: "bg-green-50",  border: "border-green-200", text: "text-green-700",  icon: "🟢" },
  yelp:          { bg: "bg-red-50",    border: "border-red-200",   text: "text-red-700",    icon: "🔴" },
  article:       { bg: "bg-blue-50",   border: "border-blue-200",  text: "text-blue-700",   icon: "📰" },
  menu:          { bg: "bg-teal-50",   border: "border-teal-200",  text: "text-teal-700",   icon: "🍽️" },
  menu_link:     { bg: "bg-teal-50",   border: "border-teal-200",  text: "text-teal-700",   icon: "📋" },
  tabit:         { bg: "bg-purple-50", border: "border-purple-200",text: "text-purple-700", icon: "📋" },
  ontopo:        { bg: "bg-orange-50", border: "border-orange-200",text: "text-orange-700", icon: "🔖" },
  wolt:          { bg: "bg-yellow-50", border: "border-yellow-200",text: "text-yellow-700", icon: "🟡" },
};

function SourceCard({ source }: { source: DataSource }) {
  const style = SOURCE_STYLES[source.source_type] ?? SOURCE_STYLES.article;
  const pct = Math.round(source.confidence * 100);

  return (
    <div className={`shrink-0 w-52 rounded-xl border ${style.border} ${style.bg} p-3.5 flex flex-col gap-2`}>
      <span className={`text-sm font-bold ${style.text} flex items-center gap-1`}>
        {style.icon} {source.source_name ?? source.source_type}
      </span>

      {source.excerpt && (
        <p className="text-xs text-gray-600 leading-relaxed line-clamp-3">&ldquo;{source.excerpt}&rdquo;</p>
      )}

      {source.review_count && (
        <p className="text-xs text-gray-400">{source.review_count.toLocaleString()} ביקורות</p>
      )}

      {/* Simplified trust bar — no % label */}
      <div className="w-full bg-gray-200 rounded-full h-1">
        <div
          className={`h-1 rounded-full ${pct >= 75 ? "bg-green-400" : pct >= 50 ? "bg-yellow-400" : "bg-orange-400"}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {source.url && (
        <a href={source.url} target="_blank" rel="noopener noreferrer"
           className={`text-xs ${style.text} hover:underline`}>
          קישור למקור ↗
        </a>
      )}
    </div>
  );
}

// ─── Recommendation Card ───────────────────────────────────────────────────

function RecommendationCard({ rec, placeId }: { rec: Recommendation; placeId: string }) {
  const qc = useQueryClient();
  const voteMutation = useMutation({
    mutationFn: (value: 1 | -1) => vote(rec.id, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recs", placeId] }),
  });

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <p className="text-gray-800 text-sm">{rec.content}</p>
      {rec.tags && rec.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {rec.tags.map((t) => (
            <span key={t} className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">#{t}</span>
          ))}
        </div>
      )}
      <div className="mt-3 flex items-center gap-3 text-sm">
        <button onClick={() => voteMutation.mutate(1)} className="flex items-center gap-1 text-green-600 hover:text-green-700">
          👍 עזר לי {rec.upvotes > 0 && <span>({rec.upvotes})</span>}
        </button>
        <button onClick={() => voteMutation.mutate(-1)} className="flex items-center gap-1 text-red-500 hover:text-red-600">
          👎 לא עזר {rec.downvotes > 0 && <span>({rec.downvotes})</span>}
        </button>
      </div>
    </div>
  );
}

// ─── Visit Rating Section ──────────────────────────────────────────────────

function VisitSection({ placeId, placeName, visits }: { placeId: string; placeName: string; visits: UserVisit[] }) {
  const qc = useQueryClient();
  const loggedIn = isLoggedIn();

  const { data: rating } = useQuery({
    queryKey: ["rating", placeId],
    queryFn: () => getPlaceRating(placeId),
  });

  const rateMutation = useMutation({
    mutationFn: (score: number) => ratePlace(placeId, score),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rating", placeId] });
      qc.invalidateQueries({ queryKey: ["visits", placeId] });
    },
  });

  const pendingVisit = visits.find(v => !v.rated && isPastOrToday(v.visit_date));
  const hasAnyVisit = visits.length > 0;

  if (!loggedIn) {
    return (
      <p className="text-sm text-gray-400 text-center py-2">
        <a href="/login" className="text-indigo-500 hover:underline">התחבר</a> כדי לדרג את המסעדה
      </p>
    );
  }

  if (rating?.user_score) {
    return (
      <div className="bg-green-50 border border-green-200 rounded-2xl px-5 py-4 flex items-center justify-between">
        <div>
          <p className="font-semibold text-green-800 text-sm">✅ דירגת: {rating.user_score}/10</p>
          {rating.avg_score && (
            <p className="text-xs text-gray-500 mt-0.5">ממוצע קהילה: {rating.avg_score} · {rating.count} דירוגים</p>
          )}
        </div>
        <span className="text-2xl font-extrabold text-green-600">{rating.user_score}</span>
      </div>
    );
  }

  if (pendingVisit) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5">
        <p className="font-bold text-gray-800 mb-1 flex items-center gap-2">
          <span>⭐</span> איך היה ב{placeName}?
        </p>
        {rating?.avg_score && (
          <p className="text-xs text-gray-500 mb-3">ממוצע קהילה: {rating.avg_score} · {rating.count} דירוגים</p>
        )}
        <div className="flex gap-1.5 flex-wrap">
          {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
            <button
              key={n}
              onClick={() => rateMutation.mutate(n)}
              disabled={rateMutation.isPending}
              className={`w-9 h-9 rounded-xl border text-sm font-bold transition-all cursor-pointer ${scoreColor(n)}`}
            >
              {n}
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (hasAnyVisit) {
    // Has a future/unresolved visit but not yet past visit_date
    return (
      <div className="bg-indigo-50 border border-indigo-100 rounded-2xl px-5 py-4 text-sm text-indigo-700">
        📅 ביקור מתוכנן — נשאל אותך לאחריו לדרג
      </div>
    );
  }

  // No visit at all
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-2xl px-5 py-4 text-sm text-gray-500 text-center">
      הזמן מקום כדי לדרג את המסעדה לאחר הביקור
    </div>
  );
}

// ─── Menu Section ─────────────────────────────────────────────────────────

const CATEGORY_ORDER = ["ראשונות", "סלטים", "מרקים", "פיצות", "פסטות", "סושי", "עיקריות", "צדדיות", "קינוחים", "שתייה"];

function MenuSection({ slug, menuUrl }: { slug: string; menuUrl?: string | null }) {
  const [open, setOpen] = useState(false);
  const { data: items = [], isLoading } = useQuery({
    queryKey: ["menu", slug],
    queryFn: () => getPlaceMenu(slug),
    enabled: open,
  });

  const byCategory = items.reduce<Record<string, MenuItem[]>>((acc, item) => {
    const cat = item.category ?? "אחר";
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(item);
    return acc;
  }, {});

  const sortedCats = Object.keys(byCategory).sort(
    (a, b) => (CATEGORY_ORDER.indexOf(a) + 1 || 99) - (CATEGORY_ORDER.indexOf(b) + 1 || 99)
  );

  return (
    <section className="mb-6">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between py-3 group"
      >
        <h2 className="font-bold text-base text-gray-800 flex items-center gap-2">
          🍽️ תפריט
          {!isLoading && items.length > 0 && (
            <span className="text-xs font-normal text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">{items.length} מנות</span>
          )}
        </h2>
        <div className="flex items-center gap-2">
          {menuUrl && (
            <a
              href={menuUrl} target="_blank" rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              className="text-xs font-medium text-teal-600 hover:text-teal-700 bg-teal-50 hover:bg-teal-100 px-2.5 py-1 rounded-full transition-colors"
            >
              תפריט מלא ↗
            </a>
          )}
          <span className="text-xs text-gray-400 group-hover:text-indigo-600 transition-colors bg-gray-100 group-hover:bg-indigo-50 px-2.5 py-1 rounded-full">
            {open ? "▲ סגור" : "▼ הצג"}
          </span>
        </div>
      </button>

      {open && (
        <div className="border border-gray-100 rounded-2xl overflow-hidden">
          {isLoading ? (
            <div className="flex flex-col gap-3 p-4">
              {[1,2,3].map(i => <div key={i} className="h-8 bg-gray-100 rounded-lg animate-pulse" />)}
            </div>
          ) : items.length === 0 ? (
            <p className="text-sm text-gray-400 p-4 text-center">אין נתוני תפריט זמינים</p>
          ) : (
            <div>
              {sortedCats.map((cat, ci) => (
                <div key={cat} className={ci > 0 ? "border-t border-gray-100" : ""}>
                  <div className="px-4 pt-3 pb-1">
                    <span className="text-xs font-bold text-indigo-500 uppercase tracking-widest">{cat}</span>
                  </div>
                  {byCategory[cat].map((item, ii) => (
                    <div key={item.id}
                      className={`flex items-center justify-between gap-3 px-4 py-2.5 ${ii < byCategory[cat].length - 1 ? "border-b border-gray-50" : ""}`}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-800">{item.name}</p>
                        {item.description && (
                          <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{item.description}</p>
                        )}
                      </div>
                      {item.price_ils && (
                        <span className="shrink-0 text-sm font-bold text-indigo-600 bg-indigo-50 px-2.5 py-0.5 rounded-full">
                          {item.price_ils} ₪
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ))}
              <p className="text-xs text-gray-400 text-center py-3 border-t border-gray-50">
                * מחירים משוערים
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

// ─── Availability Chip (hours-based, pure frontend) ───────────────────────

function AvailabilityChip({ hours }: { hours: Record<string, unknown> | null }) {
  if (!hours || !Array.isArray((hours as { periods?: unknown[] }).periods)) return null;

  const now = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Jerusalem" }));
  const googleDay = (now.getDay()); // 0=Sun already matches Google's day numbering
  const curMins = now.getHours() * 60 + now.getMinutes();

  type Period = { open: { day: number; hour: number; minute: number }; close?: { day: number; hour: number; minute: number } };
  const periods = (hours as { periods: Period[] }).periods;

  let openNow = false;
  let closeLabel: string | null = null;

  for (const p of periods) {
    const od = p.open.day;
    const om = p.open.hour * 60 + p.open.minute;
    if (!p.close) { openNow = true; break; }
    const cd = p.close.day;
    const cm = p.close.hour * 60 + p.close.minute;
    if (od === cd) {
      if (googleDay === od && curMins >= om && curMins < cm) {
        openNow = true;
        closeLabel = `${String(p.close.hour).padStart(2, "0")}:${String(p.close.minute).padStart(2, "0")}`;
        break;
      }
    } else {
      // overnight period
      if (googleDay === od && curMins >= om) { openNow = true; break; }
      if (googleDay === cd && curMins < cm) {
        openNow = true;
        closeLabel = `${String(p.close.hour).padStart(2, "0")}:${String(p.close.minute).padStart(2, "0")}`;
        break;
      }
    }
  }

  // Find next opening time if closed
  let nextOpenLabel: string | null = null;
  if (!openNow) {
    const upcoming = periods
      .map(p => ({ day: p.open.day, mins: p.open.hour * 60 + p.open.minute, hour: p.open.hour, minute: p.open.minute }))
      .sort((a, b) => {
        const da = ((a.day - googleDay + 7) % 7) * 1440 + a.mins;
        const db = ((b.day - googleDay + 7) % 7) * 1440 + b.mins;
        return da - db;
      });
    const next = upcoming.find(p => {
      const dayDiff = (p.day - googleDay + 7) % 7;
      return dayDiff > 0 || (dayDiff === 0 && p.mins > curMins);
    });
    if (next) {
      const dayDiff = (next.day - googleDay + 7) % 7;
      const timeStr = `${String(next.hour).padStart(2, "0")}:${String(next.minute).padStart(2, "0")}`;
      nextOpenLabel = dayDiff === 0 ? `היום ב-${timeStr}` : dayDiff === 1 ? `מחר ב-${timeStr}` : `ב-${timeStr}`;
    }
  }

  if (openNow) {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm font-medium px-3 py-2 rounded-xl border border-green-200 bg-green-50 text-green-700">
        <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
        פתוח{closeLabel ? ` · סוגר ב-${closeLabel}` : ""}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium px-3 py-2 rounded-xl border border-red-200 bg-red-50 text-red-700">
      <span className="w-2 h-2 rounded-full bg-red-400 inline-block" />
      סגור{nextOpenLabel ? ` · נפתח ${nextOpenLabel}` : ""}
    </span>
  );
}

// ─── Ontopo Slots Section ──────────────────────────────────────────────────

function OntopoSlots({ slug, fallbackUrl }: { slug: string; fallbackUrl: string }) {
  const todayIso = new Date().toISOString().split("T")[0];
  const { data, isLoading } = useQuery({
    queryKey: ["availability", slug, todayIso],
    queryFn: () => getAvailability(slug, 2, todayIso),
    staleTime: 30 * 60 * 1000,
  });

  // Always use the live venue URL discovered by the backend; fall back to stored URL only if not yet fetched
  const liveUrl = data?.venue_url ?? fallbackUrl;

  if (isLoading) {
    return (
      <div className="mb-4 flex gap-2">
        {[1,2,3].map(i => <div key={i} className="h-9 w-16 bg-gray-100 rounded-xl animate-pulse" />)}
      </div>
    );
  }

  const slots = data?.slots ?? [];

  if (slots.length === 0) {
    return (
      <div className="mb-4 text-sm text-gray-400 flex items-center gap-2">
        <span>🗓</span> אין מקומות פנויים להיום
        <a href={liveUrl} target="_blank" rel="noopener noreferrer" className="text-indigo-500 hover:underline text-xs">בדוק שוב ב-Ontopo ↗</a>
      </div>
    );
  }

  return (
    <div className="mb-4">
      <p className="text-sm font-medium text-gray-600 mb-2">חריצים פנויים הערב:</p>
      <div className="flex flex-wrap gap-2">
        {slots.map(slot => (
          <a
            key={slot}
            href={liveUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center text-sm font-semibold px-3 py-1.5 rounded-xl bg-indigo-50 text-indigo-700 border border-indigo-200 hover:bg-indigo-100 transition-colors"
          >
            {slot}
          </a>
        ))}
        <a
          href={liveUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center text-xs text-gray-400 hover:text-indigo-600 px-2 py-1.5"
        >
          הזמן ↗
        </a>
      </div>
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────

export default function PlacePage(props: { params: Promise<{ slug: string }> }) {
  const { slug } = use(props.params);
  const router = useRouter();
  const qc = useQueryClient();
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [showTipForm, setShowTipForm] = useState(false);
  const [bookingModal, setBookingModal] = useState<{ source: DataSource } | null>(null);

  const { data: place, isLoading } = useQuery({
    queryKey: ["place", slug],
    queryFn: () => getPlace(slug),
  });

  const { data: recs } = useQuery({
    queryKey: ["recs", place?.id],
    queryFn: () => getRecommendations(place!.id),
    enabled: !!place,
  });

  const { data: visits = [] } = useQuery({
    queryKey: ["visits", place?.id],
    queryFn: () => getPlaceVisits(place!.id),
    enabled: !!place && isLoggedIn(),
  });

  // Start availability fetch as soon as place is loaded (Ontopo IDs go stale; discovery fixes them)
  const todayIso = new Date().toISOString().split("T")[0];
  const hasOntopo = !!place?.sources?.some(s => s.source_type === "ontopo" && s.url);
  const { data: availData, isLoading: isAvailLoading } = useQuery({
    queryKey: ["availability", slug, todayIso],
    queryFn: () => getAvailability(slug, 2, todayIso),
    enabled: hasOntopo,
    staleTime: 30 * 60 * 1000,
  });

  const addRec = useMutation({
    mutationFn: () => createRecommendation({
      place_id: place!.id,
      content,
      tags: tags ? tags.split(",").map(t => t.trim()).filter(Boolean) : undefined,
    }),
    onSuccess: () => {
      setContent("");
      setTags("");
      setShowTipForm(false);
      qc.invalidateQueries({ queryKey: ["recs", place?.id] });
    },
  });

  if (isLoading) return <div className="p-8 text-center text-gray-400">טוען...</div>;
  if (!place) return <div className="p-8 text-center text-gray-400">המקום לא נמצא.</div>;

  const reservationSource =
    RESERVATION_SOURCE_PRIORITY
      .flatMap(type => place.sources?.filter(s => s.source_type === type && s.url) ?? [])
      [0] ?? null;
  const menuLinkSource = place.sources?.find(s => MENU_LINK_TYPES.has(s.source_type) && s.url) ?? null;
  const ontopoSource = place.sources?.find(s => s.source_type === "ontopo" && s.url) ?? null;
  const pendingVisitForBanner = visits.find(v => !v.rated && isPastOrToday(v.visit_date));

  // Best reservation URL: discovered live Ontopo URL → restaurant website → stored Ontopo URL
  const liveOntopoUrl =
    availData?.venue_url && availData.venue_url !== ontopoSource?.url
      ? availData.venue_url
      : undefined;
  const reservationUrl = liveOntopoUrl ?? place.website ?? ontopoSource?.url ?? null;

  function handleBookingClick(source: DataSource) {
    if (reservationUrl) window.open(reservationUrl, "_blank");
    setBookingModal({ source });
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">

      {/* Back button */}
      <button
        onClick={() => router.back()}
        className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-gray-500 hover:text-gray-800 transition-colors"
      >
        ← חזרה
      </button>

      {/* Photos */}
      {place.photos && place.photos.length > 0 && (
        <div className="mb-6">
          <PhotoGallery photos={place.photos} placeName={place.name} />
        </div>
      )}

      {/* Header */}
      <div className="mb-6">
        <div className="flex items-start justify-between gap-4 mb-1">
          <h1 className="text-3xl font-extrabold text-gray-900">{place.name}</h1>
          {place.aggregated_score && (
            <span className="shrink-0 bg-indigo-600 text-white font-bold px-3 py-1.5 rounded-full text-lg">
              ★ {place.aggregated_score.toFixed(1)}
            </span>
          )}
        </div>
        {place.address && <p className="text-gray-500 text-sm mb-2">📍 {place.address}</p>}
        <div className="flex flex-wrap gap-2 mb-4">
          {place.cuisine?.map(c => (
            <span key={c} className="text-sm bg-indigo-50 text-indigo-700 font-medium px-3 py-0.5 rounded-full">{c}</span>
          ))}
          {place.price_range && (
            <span className="text-sm bg-green-50 text-green-700 font-medium px-3 py-0.5 rounded-full">
              {PRICE[place.price_range]}
            </span>
          )}
        </div>

        {/* Action bar */}
        <div className="flex flex-wrap gap-2">
          {(reservationSource || ontopoSource) && (
            <button
              onClick={() => handleBookingClick(reservationSource ?? ontopoSource!)}
              disabled={isAvailLoading && hasOntopo}
              className="inline-flex items-center gap-1.5 text-sm font-semibold px-4 py-2 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 transition-colors disabled:opacity-60 disabled:cursor-wait"
            >
              {isAvailLoading && hasOntopo ? "⏳ מחפש..." : "🗓 הזמן מקום"}
            </button>
          )}
          {place.lat && place.lng && (
            <>
              <a
                href={`https://waze.com/ul?ll=${place.lat},${place.lng}&navigate=yes&zoom=17`}
                target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm font-medium px-3 py-2 rounded-xl border border-gray-200 bg-gray-50 text-gray-700 hover:bg-gray-100 transition-colors"
              >
                🚗 Waze
              </a>
              <a
                href={`https://maps.google.com/?q=${place.lat},${place.lng}`}
                target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm font-medium px-3 py-2 rounded-xl border border-gray-200 bg-gray-50 text-gray-700 hover:bg-gray-100 transition-colors"
              >
                📍 Maps
              </a>
            </>
          )}
          {menuLinkSource?.url && (
            <a
              href={menuLinkSource.url} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-semibold px-4 py-2 rounded-xl bg-teal-600 text-white hover:bg-teal-700 transition-colors"
            >
              📋 תפריט
            </a>
          )}
          {place.website && (
            <a
              href={place.website} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm font-medium px-3 py-2 rounded-xl border border-gray-200 bg-gray-50 text-gray-700 hover:bg-gray-100 transition-colors"
            >
              🌐 אתר
            </a>
          )}
          <AvailabilityChip hours={place.hours} />
        </div>

        {/* Ontopo real-time slots */}
        {ontopoSource?.url && (
          <div className="mt-3">
            <OntopoSlots slug={slug} fallbackUrl={ontopoSource.url} />
          </div>
        )}
      </div>

      {/* Pending visit banner */}
      {pendingVisitForBanner && (
        <div className="mb-6 bg-amber-50 border border-amber-300 rounded-2xl px-5 py-3.5 text-sm text-amber-800 font-medium">
          ⭐ ביקרת ב{place.name}? גלול למטה ודרג את החוויה שלך!
        </div>
      )}

      {/* Visit rating */}
      <div className="mb-6">
        <VisitSection placeId={place.id} placeName={place.name} visits={visits} />
      </div>

      {/* Featured review — prefer google_places aggregate, then high review_count, then confidence */}
      {(() => {
        const excerptScore = (s: DataSource) =>
          (s.source_type === "google_places" ? 10000 : 0) +
          (s.review_count ?? 0) * 10 +
          s.confidence * 100;
        const best = place.sources
          ?.filter(s => s.excerpt && s.excerpt.length > 30)
          .sort((a, b) => excerptScore(b) - excerptScore(a))[0];
        if (!best) return null;
        const style = SOURCE_STYLES[best.source_type] ?? SOURCE_STYLES.article;
        return (
          <div className="mb-6 relative bg-gray-50 border border-gray-100 rounded-2xl px-6 pt-6 pb-4">
            <span className="absolute top-3 right-5 text-5xl text-gray-200 font-serif leading-none select-none">&ldquo;</span>
            <p className="text-gray-800 text-base leading-relaxed font-medium">
              {best.excerpt}
            </p>
            <p className={`text-xs mt-3 font-medium ${style.text}`}>
              {style.icon} {best.source_name ?? best.source_type}
            </p>
          </div>
        );
      })()}

      {/* AI Summary — collapsed by default */}
      <div className="mb-6">
        <AISummaryCard placeSlug={slug} />
      </div>

      {/* Menu */}
      <MenuSection slug={slug} menuUrl={menuLinkSource?.url} />

      {/* Source Cards */}
      {place.sources && place.sources.length > 0 && (
        <section className="mb-6">
          <h2 className="font-bold text-base mb-3 text-gray-700">מה אומרים עליהם</h2>
          <div className="flex gap-3 overflow-x-auto pb-2 -mx-4 px-4">
            {place.sources.map((s, i) => <SourceCard key={i} source={s} />)}
          </div>
        </section>
      )}

      {/* Community tips */}
      <section className="mb-6">
        <h2 className="font-bold text-base mb-3 text-gray-700">טיפים מהקהילה</h2>
        {!recs || recs.length === 0 ? (
          <p className="text-gray-400 text-sm">עדיין אין טיפים — היה הראשון!</p>
        ) : (
          <div className="flex flex-col gap-3">
            {recs.map(r => <RecommendationCard key={r.id} rec={r} placeId={place.id} />)}
          </div>
        )}
      </section>

      {/* Add tip */}
      <section className="mb-8">
        {!showTipForm ? (
          <button
            onClick={() => setShowTipForm(true)}
            className="w-full border border-dashed border-gray-300 text-gray-500 rounded-xl py-3 text-sm hover:border-indigo-400 hover:text-indigo-600 transition-colors"
          >
            + הוסף טיפ
          </button>
        ) : (
          <div className="bg-white border border-gray-200 rounded-xl p-4 flex flex-col gap-3">
            <textarea
              value={content}
              onChange={e => setContent(e.target.value)}
              placeholder="שתף את החוויה שלך..."
              rows={3}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <input
              value={tags}
              onChange={e => setTags(e.target.value)}
              placeholder="תגיות (מופרדות בפסיקים): ארוחת צהריים, רועש בלילה..."
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <div className="flex gap-2">
              <button
                onClick={() => addRec.mutate()}
                disabled={!content.trim() || addRec.isPending}
                className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
              >
                {addRec.isPending ? "שולח..." : "שלח"}
              </button>
              <button
                onClick={() => setShowTipForm(false)}
                className="px-4 py-2 rounded-lg text-sm text-gray-500 border border-gray-200 hover:bg-gray-50"
              >
                ביטול
              </button>
            </div>
            {addRec.isError && <p className="text-red-500 text-sm">שליחה נכשלה. אנא התחבר תחילה.</p>}
          </div>
        )}
      </section>

      {/* Booking confirm modal */}
      {bookingModal && (
        <BookingConfirmModal
          placeName={place.name}
          placeId={place.id}
          source={bookingModal.source.source_type}
          onClose={() => setBookingModal(null)}
        />
      )}
    </div>
  );
}
