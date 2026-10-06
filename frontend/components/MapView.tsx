"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { GoogleMap, useJsApiLoader, Marker, InfoWindow } from "@react-google-maps/api";
import Link from "next/link";
import { type Place } from "@/lib/api";
import { getPlaceGradient } from "@/lib/categories";

const TEL_AVIV_CENTER = { lat: 32.08, lng: 34.78 };

const PRICE = ["", "₪", "₪₪", "₪₪₪", "₪₪₪₪"];

const mapStyles: google.maps.MapTypeStyle[] = [
  { featureType: "poi.business", stylers: [{ visibility: "off" }] },
  { featureType: "transit", elementType: "labels.icon", stylers: [{ visibility: "off" }] },
];

interface Props {
  places: Place[];
}

function markerIcon(cuisine: string[] | null): string {
  const gradient = getPlaceGradient(cuisine);
  const colors: Record<string, string> = {
    "from-amber-100": "#f59e0b",
    "from-rose-100": "#f43f5e",
    "from-emerald-100": "#10b981",
    "from-yellow-100": "#eab308",
    "from-orange-100": "#f97316",
    "from-violet-100": "#8b5cf6",
    "from-sky-100": "#0ea5e9",
    "from-stone-100": "#78716c",
    "from-indigo-100": "#6366f1",
  };
  const key = gradient.split(" ")[0];
  return colors[key] ?? "#6366f1";
}

export default function MapView({ places }: Props) {
  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";

  const { isLoaded, loadError } = useJsApiLoader({
    googleMapsApiKey: apiKey,
    id: "reco-google-map",
  });

  const [center, setCenter] = useState(TEL_AVIV_CENTER);
  const [selected, setSelected] = useState<Place | null>(null);
  const mapRef = useRef<google.maps.Map | null>(null);

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => setCenter({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => setCenter(TEL_AVIV_CENTER)
    );
  }, []);

  const onLoad = useCallback((map: google.maps.Map) => {
    mapRef.current = map;
  }, []);

  if (!apiKey) {
    return (
      <div className="w-full h-[60vh] flex items-center justify-center bg-gray-100 rounded-2xl text-center p-6">
        <div>
          <p className="text-4xl mb-3">🗺️</p>
          <p className="font-bold text-gray-700 mb-1">מפת המסעדות</p>
          <p className="text-sm text-gray-500">
            הוסף{" "}
            <code className="bg-gray-200 px-1 rounded text-xs">NEXT_PUBLIC_GOOGLE_MAPS_API_KEY</code>{" "}
            לקובץ <code className="bg-gray-200 px-1 rounded text-xs">.env.local</code> כדי להפעיל את המפה
          </p>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="w-full h-[60vh] flex items-center justify-center bg-red-50 rounded-2xl">
        <p className="text-red-500 text-sm">שגיאה בטעינת המפה</p>
      </div>
    );
  }

  if (!isLoaded) {
    return (
      <div className="w-full h-[60vh] flex items-center justify-center bg-gray-100 rounded-2xl animate-pulse">
        <p className="text-gray-400">טוען מפה...</p>
      </div>
    );
  }

  return (
    <div className="w-full rounded-2xl overflow-hidden shadow-md">
      <GoogleMap
        mapContainerStyle={{ width: "100%", height: "60vh" }}
        center={center}
        zoom={14}
        onLoad={onLoad}
        options={{
          styles: mapStyles,
          disableDefaultUI: false,
          zoomControl: true,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: false,
        }}
        onClick={() => setSelected(null)}
      >
        {places.map((place) => {
          if (!place.lat || !place.lng) return null;
          const color = markerIcon(place.cuisine);
          return (
            <Marker
              key={place.id}
              position={{ lat: place.lat, lng: place.lng }}
              onClick={() => setSelected(place)}
              icon={{
                path: google.maps.SymbolPath.CIRCLE,
                fillColor: color,
                fillOpacity: 1,
                strokeColor: "#ffffff",
                strokeWeight: 2,
                scale: 10,
              }}
            />
          );
        })}

        {selected && selected.lat && selected.lng && (
          <InfoWindow
            position={{ lat: selected.lat, lng: selected.lng }}
            onCloseClick={() => setSelected(null)}
          >
            <div className="p-1 min-w-[140px] text-right" dir="rtl">
              <p className="font-bold text-gray-900 text-sm leading-snug">{selected.name}</p>
              {selected.address && (
                <p className="text-xs text-gray-500 mt-0.5 truncate">{selected.address}</p>
              )}
              <div className="mt-1.5 flex items-center gap-2">
                {selected.aggregated_score && (
                  <span className="text-xs bg-green-100 text-green-700 font-bold px-2 py-0.5 rounded-full">
                    ★ {selected.aggregated_score.toFixed(1)}
                  </span>
                )}
                {selected.price_range && (
                  <span className="text-xs text-gray-500">{PRICE[selected.price_range]}</span>
                )}
              </div>
              {selected.cuisine && selected.cuisine.length > 0 && (
                <p className="text-xs text-indigo-600 mt-1">{selected.cuisine[0]}</p>
              )}
              <Link
                href={`/places/${selected.slug}`}
                className="mt-2 block text-center text-xs bg-indigo-600 text-white rounded-lg py-1 px-3 hover:bg-indigo-700 transition-colors"
              >
                פרטים ←
              </Link>
            </div>
          </InfoWindow>
        )}
      </GoogleMap>
    </div>
  );
}
