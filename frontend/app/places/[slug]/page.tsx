"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { use } from "react";
import { getPlace, getRecommendations, createRecommendation, vote, type Recommendation, type DataSource } from "@/lib/api";
import PhotoGallery from "@/components/PhotoGallery";
import AISummaryCard from "@/components/AISummaryCard";
import MenuButton from "@/components/MenuButton";
import VisitRating from "@/components/VisitRating";

const PRICE = ["", "₪", "₪₪", "₪₪₪", "₪₪₪₪"];

const STATUS_LABELS: Record<string, string> = {
  pending: "ממתין לאישור",
  approved: "מאושר",
  rejected: "נדחה",
  flagged: "מסומן לבדיקה",
};

const SOURCE_STYLES: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  google_places: { bg: "bg-green-50",  border: "border-green-200", text: "text-green-700",  icon: "🟢" },
  yelp:          { bg: "bg-red-50",    border: "border-red-200",   text: "text-red-700",    icon: "🔴" },
  article:       { bg: "bg-blue-50",   border: "border-blue-200",  text: "text-blue-700",   icon: "📰" },
  menu:          { bg: "bg-teal-50",   border: "border-teal-200",  text: "text-teal-700",   icon: "🍽️" },
  tabit:         { bg: "bg-purple-50", border: "border-purple-200",text: "text-purple-700", icon: "📋" },
  ontopo:        { bg: "bg-orange-50", border: "border-orange-200",text: "text-orange-700", icon: "🔖" },
  wolt:          { bg: "bg-yellow-50", border: "border-yellow-200",text: "text-yellow-700", icon: "🟡" },
};

function trustBarColor(confidence: number): string {
  if (confidence >= 0.75) return "bg-green-400";
  if (confidence >= 0.5)  return "bg-yellow-400";
  return "bg-orange-400";
}

function SourceCard({ source }: { source: DataSource }) {
  const style = SOURCE_STYLES[source.source_type] ?? SOURCE_STYLES.article;
  const pct = Math.round(source.confidence * 100);

  return (
    <div className={`shrink-0 w-56 rounded-xl border ${style.border} ${style.bg} p-4 flex flex-col gap-2`}>
      <div className="flex items-center justify-between">
        <span className={`text-sm font-bold ${style.text} flex items-center gap-1`}>
          {style.icon} {source.source_name ?? source.source_type}
        </span>
      </div>

      {source.excerpt && (
        <p className="text-xs text-gray-600 leading-relaxed line-clamp-3">&ldquo;{source.excerpt}&rdquo;</p>
      )}

      {source.review_count && (
        <p className="text-xs text-gray-400">{source.review_count.toLocaleString()} ביקורות</p>
      )}

      <div className="mt-auto">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-gray-400">אמינות</span>
          <span className={`text-xs font-bold ${style.text}`}>{pct}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-1.5">
          <div
            className={`h-1.5 rounded-full ${trustBarColor(source.confidence)}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {source.url && (
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className={`text-xs ${style.text} hover:underline mt-1`}
          onClick={(e) => e.stopPropagation()}
        >
          קישור למקור ↗
        </a>
      )}
    </div>
  );
}

function RecommendationCard({ rec, placeId }: { rec: Recommendation; placeId: string }) {
  const qc = useQueryClient();
  const voteMutation = useMutation({
    mutationFn: (value: 1 | -1) => vote(rec.id, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recs", placeId] }),
  });

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <p className="text-gray-800">{rec.content}</p>
      {rec.tags && rec.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {rec.tags.map((t) => (
            <span key={t} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
              #{t}
            </span>
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
        <span className="mr-auto text-xs text-gray-400">{STATUS_LABELS[rec.status] ?? rec.status}</span>
      </div>
    </div>
  );
}

export default function PlacePage(props: PageProps<"/places/[slug]">) {
  const { slug } = use(props.params);
  const qc = useQueryClient();
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");

  const { data: place, isLoading } = useQuery({
    queryKey: ["place", slug],
    queryFn: () => getPlace(slug),
  });

  const { data: recs } = useQuery({
    queryKey: ["recs", place?.id],
    queryFn: () => getRecommendations(place!.id),
    enabled: !!place,
  });

  const addRec = useMutation({
    mutationFn: () =>
      createRecommendation({
        place_id: place!.id,
        content,
        tags: tags ? tags.split(",").map((t) => t.trim()).filter(Boolean) : undefined,
      }),
    onSuccess: () => {
      setContent("");
      setTags("");
      qc.invalidateQueries({ queryKey: ["recs", place?.id] });
    },
  });

  if (isLoading) return <div className="p-8 text-center text-gray-400">טוען...</div>;
  if (!place) return <div className="p-8 text-center text-gray-400">המקום לא נמצא.</div>;

  return (
    <>
      <div className="max-w-2xl mx-auto px-4 py-6 pb-24">

        {/* Photo gallery */}
        {place.photos && place.photos.length > 0 && (
          <div className="mb-6">
            <PhotoGallery photos={place.photos} placeName={place.name} />
          </div>
        )}

        {/* Header */}
        <div className="mb-6">
          <div className="flex items-start justify-between gap-4">
            <h1 className="text-3xl font-extrabold text-gray-900">{place.name}</h1>
            {place.aggregated_score && (
              <span className="shrink-0 bg-indigo-600 text-white font-bold px-3 py-1.5 rounded-full text-lg">
                ★ {place.aggregated_score.toFixed(1)}
              </span>
            )}
          </div>
          {place.address && <p className="text-gray-500 mt-1">📍 {place.address}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            {place.cuisine?.map((c) => (
              <span key={c} className="text-sm bg-indigo-50 text-indigo-700 font-medium px-3 py-0.5 rounded-full">
                {c}
              </span>
            ))}
            {place.price_range && (
              <span className="text-sm bg-green-50 text-green-700 font-medium px-3 py-0.5 rounded-full">
                {PRICE[place.price_range]}
              </span>
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-3 text-sm text-gray-500">
            {place.phone && <span>📞 {place.phone}</span>}
            {place.website && (
              <a href={place.website} target="_blank" rel="noopener noreferrer"
                 className="text-indigo-600 hover:underline font-medium">
                🌐 אתר המסעדה
              </a>
            )}
          </div>

          {/* Navigation buttons */}
          {place.lat && place.lng && (
            <div className="mt-3 flex gap-2 flex-wrap">
              <a
                href={`https://waze.com/ul?ll=${place.lat},${place.lng}&navigate=yes&zoom=17`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-full border border-gray-200 bg-gray-50 text-gray-700 hover:bg-gray-100 transition-colors"
              >
                🚗 נווט בוייז
              </a>
              <a
                href={`https://maps.google.com/?q=${place.lat},${place.lng}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-full border border-gray-200 bg-gray-50 text-gray-700 hover:bg-gray-100 transition-colors"
              >
                📍 מפות גוגל
              </a>
            </div>
          )}
        </div>

        {/* AI Summary */}
        <div className="mb-6">
          <AISummaryCard placeSlug={slug} />
        </div>

        {/* Source Cards */}
        {place.sources && place.sources.length > 0 && (
          <section className="mb-6">
            <h2 className="font-bold text-lg mb-3">מה אומרים עליהם</h2>
            <div className="flex gap-3 overflow-x-auto pb-2 -mx-4 px-4">
              {place.sources.map((s, i) => (
                <SourceCard key={i} source={s} />
              ))}
            </div>
          </section>
        )}

        {/* Visit Rating */}
        <div className="mb-6">
          <VisitRating placeId={place.id} />
        </div>

        {/* Community Recommendations */}
        <section className="mb-6">
          <h2 className="font-bold text-lg mb-3">המלצות הקהילה</h2>
          {!recs || recs.length === 0 ? (
            <p className="text-gray-400 text-sm">עדיין אין המלצות — היה הראשון!</p>
          ) : (
            <div className="flex flex-col gap-3">
              {recs.map((r) => (
                <RecommendationCard key={r.id} rec={r} placeId={place.id} />
              ))}
            </div>
          )}
        </section>

        {/* Add Recommendation */}
        <section>
          <h2 className="font-bold text-lg mb-3">הוסף המלצה</h2>
          <div className="bg-white border border-gray-200 rounded-xl p-4 flex flex-col gap-3">
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="שתף את החוויה שלך..."
              rows={3}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="תגיות (מופרדות בפסיקים): ארוחת צהריים מעולה, רועש בלילה..."
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
            <button
              onClick={() => addRec.mutate()}
              disabled={!content.trim() || addRec.isPending}
              className="self-start bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
            >
              {addRec.isPending ? "שולח..." : "שלח"}
            </button>
            {addRec.isError && (
              <p className="text-red-500 text-sm">שליחה נכשלה. אנא התחבר תחילה.</p>
            )}
          </div>
        </section>
      </div>

      {/* Floating menu button — outside scroll container so it stays fixed */}
      {place.sources && <MenuButton sources={place.sources} />}
    </>
  );
}
