"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { use } from "react";
import {
  getPlace, getRecommendations, createRecommendation, vote,
  getPlaceRating, ratePlace, getPlaceVisits, getPlaceMenu,
  type Recommendation, type DataSource, type UserVisit, type MenuItem,
} from "@/lib/api";
import PhotoGallery from "@/components/PhotoGallery";
import AISummaryCard from "@/components/AISummaryCard";
import BookingConfirmModal from "@/components/BookingConfirmModal";

const PRICE = ["", "₪", "₪₪", "₪₪₪", "₪₪₪₪"];

const BOOKING_SOURCES = new Set(["menu", "tabit", "ontopo", "wolt"]);

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

function MenuSection({ slug }: { slug: string }) {
  const [open, setOpen] = useState(true);
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
        <span className="text-xs text-gray-400 group-hover:text-indigo-600 transition-colors bg-gray-100 group-hover:bg-indigo-50 px-2.5 py-1 rounded-full">
          {open ? "▲ סגור" : "▼ הצג"}
        </span>
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

// ─── Main Page ─────────────────────────────────────────────────────────────

export default function PlacePage(props: { params: Promise<{ slug: string }> }) {
  const { slug } = use(props.params);
  const qc = useQueryClient();
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [showTipForm, setShowTipForm] = useState(false);
  const [bookingModal, setBookingModal] = useState<{ source: DataSource } | null>(null);

  function handleBookingClick(source: DataSource) {
    if (source.url) window.open(source.url, "_blank");
    setBookingModal({ source });
  }

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

  const bookingSources = place.sources?.filter(s => BOOKING_SOURCES.has(s.source_type) && s.url) ?? [];
  const pendingVisitForBanner = visits.find(v => !v.rated && isPastOrToday(v.visit_date));

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">

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
          {bookingSources.length > 0 && (
            <button
              onClick={() => handleBookingClick(bookingSources[0])}
              className="inline-flex items-center gap-1.5 text-sm font-semibold px-4 py-2 rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
            >
              🗓 הזמן מקום
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
          {place.website && (
            <a
              href={place.website} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm font-medium px-3 py-2 rounded-xl border border-gray-200 bg-gray-50 text-gray-700 hover:bg-gray-100 transition-colors"
            >
              🌐 אתר
            </a>
          )}
        </div>
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

      {/* Featured review — best-confidence source */}
      {(() => {
        const best = place.sources
          ?.filter(s => s.excerpt && s.excerpt.length > 30)
          .sort((a, b) => b.confidence - a.confidence)[0];
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
      <MenuSection slug={slug} />

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
