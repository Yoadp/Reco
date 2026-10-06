"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postVisit } from "@/lib/api";

interface Props {
  placeName: string;
  placeId: string;
  source: string;
  onClose: () => void;
}

function tomorrow(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().split("T")[0];
}

function today(): string {
  return new Date().toISOString().split("T")[0];
}

export default function BookingConfirmModal({ placeName, placeId, source, onClose }: Props) {
  const qc = useQueryClient();
  const [visitDate, setVisitDate] = useState(tomorrow());

  const visitMutation = useMutation({
    mutationFn: () => postVisit(placeId, source, visitDate),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["visits", placeId] });
      qc.invalidateQueries({ queryKey: ["pendingVisits"] });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6 flex flex-col gap-4"
        dir="rtl"
        onClick={e => e.stopPropagation()}
      >
        <div>
          <h2 className="text-lg font-bold text-gray-900">🗓 הזמנת שולחן ב{placeName}?</h2>
          <p className="text-sm text-gray-500 mt-1">נשאל אותך למחרת הביקור איך היה</p>
        </div>

        <div className="flex gap-3">
          <button
            onClick={() => visitMutation.mutate()}
            disabled={visitMutation.isPending}
            className="flex-1 bg-indigo-600 text-white py-2.5 rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {visitMutation.isPending ? "שומר..." : "כן, הזמנתי ✓"}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-xl text-sm text-gray-500 border border-gray-200 hover:bg-gray-50 transition-colors"
          >
            לא
          </button>
        </div>

        {visitMutation.data === undefined && !visitMutation.isPending && (
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-500">מתי הביקור?</label>
            <input
              type="date"
              value={visitDate}
              min={today()}
              onChange={e => setVisitDate(e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>
        )}
      </div>
    </div>
  );
}
