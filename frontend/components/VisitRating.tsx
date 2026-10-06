"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getPlaceRating, ratePlace } from "@/lib/api";

interface Props {
  placeId: string;
}

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

export default function VisitRating({ placeId }: Props) {
  const qc = useQueryClient();
  const loggedIn = isLoggedIn();

  const { data: rating } = useQuery({
    queryKey: ["rating", placeId],
    queryFn: () => getPlaceRating(placeId),
  });

  const rateMutation = useMutation({
    mutationFn: (score: number) => ratePlace(placeId, score),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rating", placeId] }),
  });

  return (
    <section className="bg-gradient-to-br from-amber-50 to-yellow-50 border border-amber-100 rounded-2xl p-5">
      <h2 className="font-bold text-lg text-gray-800 mb-1 flex items-center gap-2">
        <span>⭐</span> ביקרת פה? מה הדירוג שלך?
      </h2>

      {rating && rating.count > 0 && (
        <p className="text-sm text-gray-500 mb-3">
          ממוצע קהילה: <span className="font-semibold text-gray-700">{rating.avg_score}</span>
          {" "}· {rating.count} {rating.count === 1 ? "דירוג" : "דירוגים"}
        </p>
      )}

      <div className="flex gap-1.5 flex-wrap">
        {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => {
          const isSelected = rating?.user_score === n;
          return (
            <button
              key={n}
              onClick={() => loggedIn && rateMutation.mutate(n)}
              disabled={!loggedIn || rateMutation.isPending}
              title={!loggedIn ? "התחבר כדי לדרג" : undefined}
              className={`w-9 h-9 rounded-xl border text-sm font-bold transition-all ${
                isSelected ? selectedColor(n) : scoreColor(n)
              } ${!loggedIn ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
            >
              {n}
            </button>
          );
        })}
      </div>

      {!loggedIn && (
        <p className="mt-2 text-xs text-gray-400">
          <a href="/login" className="text-indigo-500 hover:underline">התחבר</a> כדי לדרג את המסעדה
        </p>
      )}

      {rating?.user_score && (
        <p className="mt-2 text-xs text-gray-500">
          הדירוג שלך: <span className="font-semibold">{rating.user_score}/10</span> · לחץ שוב לשינוי
        </p>
      )}
    </section>
  );
}
