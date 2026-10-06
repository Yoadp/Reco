"use client";

import { useState } from "react";
import Image from "next/image";

interface Props {
  photos: string[];
  placeName: string;
}

export default function PhotoGallery({ photos, placeName }: Props) {
  const [lightbox, setLightbox] = useState<string | null>(null);

  if (!photos || photos.length === 0) return null;

  return (
    <>
      {/* Horizontal scroll gallery */}
      <div
        className="flex gap-3 overflow-x-auto -mx-4 px-4 pb-2"
        style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
      >
        {photos.map((url, i) => (
          <button
            key={i}
            onClick={() => setLightbox(url)}
            className="shrink-0 w-56 h-44 rounded-2xl overflow-hidden relative shadow-sm hover:shadow-md transition-shadow active:scale-[0.98] transition-transform"
          >
            <Image
              src={url}
              alt={`${placeName} תמונה ${i + 1}`}
              fill
              className="object-cover"
              sizes="224px"
              unoptimized
            />
          </button>
        ))}
      </div>

      {/* Lightbox */}
      {lightbox && (
        <div
          className="fixed inset-0 bg-black/90 z-50 flex items-center justify-center p-4"
          onClick={() => setLightbox(null)}
        >
          <button
            className="absolute top-4 left-4 text-white text-2xl font-bold leading-none opacity-80 hover:opacity-100"
            onClick={() => setLightbox(null)}
          >
            ✕
          </button>
          <div className="relative w-full max-w-lg aspect-[4/3] rounded-2xl overflow-hidden">
            <Image
              src={lightbox}
              alt={placeName}
              fill
              className="object-cover"
              sizes="512px"
              unoptimized
            />
          </div>
        </div>
      )}
    </>
  );
}
