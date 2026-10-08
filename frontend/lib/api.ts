import axios from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
});

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;

// ---- Photo URL helper ----
// Photos are stored as Google Places photo reference names (permanent, never expire).
// e.g. "places/ChIJ.../photos/AXCi2y..."
// The frontend constructs the actual URL using the public Maps API key.
export function photoUrl(ref: string | null | undefined, width = 800): string | null {
  if (!ref) return null;
  // Already a resolved URL (legacy rows before the reference migration)
  if (ref.startsWith("http")) return ref;
  const key = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
  if (!key) return null;
  return `https://places.googleapis.com/v1/${ref}/media?maxWidthPx=${width}&key=${key}`;
}

// ---- Types ----

export interface DataSource {
  source_type: string;
  source_name: string | null;
  url: string | null;
  excerpt: string | null;
  review_count: number | null;
  confidence: number;
  scraped_at: string;
}

export interface Place {
  id: string;
  name: string;
  slug: string;
  address: string | null;
  city: string | null;
  lat: number | null;
  lng: number | null;
  cuisine: string[] | null;
  price_range: number | null;
  aggregated_score: number | null;
  photos: string[] | null;
  phone: string | null;
  website: string | null;
  hours: Record<string, unknown> | null;
  sources?: DataSource[];
  matched_dishes?: string[] | null;
}

export interface Recommendation {
  id: string;
  place_id: string;
  user_id: string;
  content: string;
  tags: string[] | null;
  status: string;
  upvotes: number;
  downvotes: number;
  points_awarded: number | null;
}

export interface UserProfile {
  id: string;
  username: string;
  points_balance: number;
  tier: "bronze" | "silver" | "gold";
  cuisine_preferences: string[] | null;
  dietary_restrictions: string[] | null;
  price_preference: number | null;
}

// ---- API helpers ----

export const searchPlaces = (params: {
  q?: string;
  city?: string;
  cuisine?: string;
  price_range?: number;
  nlp?: boolean;
  limit?: number;
  open_now?: boolean;
  lat?: number;
  lng?: number;
  radius_km?: number;
  sort?: string;
}) => api.get<Place[]>("/places", { params: { limit: 200, ...params } }).then((r) => r.data);

export const getPlace = (slug: string) =>
  api.get<Place & { sources: DataSource[] }>(`/places/${slug}`).then((r) => r.data);

export const getRecommendations = (placeId: string) =>
  api.get<Recommendation[]>(`/recommendations/place/${placeId}`).then((r) => r.data);

export const createRecommendation = (body: {
  place_id: string;
  content: string;
  tags?: string[];
}) => api.post<Recommendation>("/recommendations", body).then((r) => r.data);

export const vote = (recId: string, value: 1 | -1) =>
  api.post(`/recommendations/${recId}/vote`, null, { params: { value } }).then((r) => r.data);

export const getMe = () => api.get<UserProfile>("/users/me").then((r) => r.data);

export const updatePreferences = (prefs: {
  cuisine_preferences?: string[];
  dietary_restrictions?: string[];
  price_preference?: number;
}) => api.patch<UserProfile>("/users/me/preferences", prefs).then((r) => r.data);

export const login = (email: string, password: string) =>
  api.post<{ access_token: string }>("/auth/login", { email, password }).then((r) => r.data);

export const register = (email: string, username: string, password: string) =>
  api.post<{ access_token: string }>("/auth/register", { email, username, password }).then((r) => r.data);

// ---- Visits ----

export interface UserVisit {
  id: string;
  place_id: string;
  source: string | null;
  visit_date: string | null;   // ISO date "YYYY-MM-DD"
  visited_at: string;
  rated: boolean;
}

export const postVisit = (placeId: string, source: string, visitDate?: string) =>
  api.post<UserVisit>("/visits", { place_id: placeId, source, visit_date: visitDate ?? null }).then(r => r.data);

export const getPendingVisits = () =>
  api.get<UserVisit[]>("/visits/pending").then(r => r.data);

export const getPlaceVisits = (placeId: string) =>
  api.get<UserVisit[]>(`/visits/place/${placeId}`).then(r => r.data);

// ---- Ratings ----

export interface PlaceRatingInfo {
  avg_score: number | null;
  count: number;
  user_score: number | null;
}

export const getPlaceRating = (placeId: string) =>
  api.get<PlaceRatingInfo>(`/ratings/place/${placeId}`).then((r) => r.data);

export const ratePlace = (placeId: string, score: number) =>
  api.post("/ratings", { place_id: placeId, score }).then((r) => r.data);

// ---- Menu ----

export interface MenuItem {
  id: string;
  name: string;
  price_ils: number | null;
  description: string | null;
  category: string | null;
  source: string | null;
}

export const getPlaceMenu = (slug: string) =>
  api.get<MenuItem[]>(`/places/${slug}/menu`).then((r) => r.data);

// ---- Smart Search ----

export interface ParsedQuery {
  dish: string | null;
  cuisine: string | null;
  price_min_ils: number | null;
  price_max_ils: number | null;
  city: string | null;
  party_size?: number | null;
  open_at_day?: number | null;
  open_at_hour?: number | null;
}

export interface SmartSearchResult {
  exact: Place[];
  similar: Place[];
  parsed: ParsedQuery;
}

export const smartSearchPlaces = (q: string, city?: string) =>
  api.get<SmartSearchResult>("/places/smart", { params: { q, city: city || undefined } }).then((r) => r.data);

// ---- Saved Places ----

export interface SavedPlaceEntry extends Place {
  saved_id: string;
  list_type: string;
}

export const getSavedPlaces = (list_type?: string) =>
  api.get<SavedPlaceEntry[]>("/saved/places", { params: list_type ? { list_type } : {} }).then((r) => r.data);

export const savePlace = (place_id: string, list_type: string = "wishlist") =>
  api.post("/saved", { place_id, list_type }).then((r) => r.data);

export const unsavePlace = (place_id: string, list_type?: string) =>
  api.delete(`/saved/${place_id}`, { params: list_type ? { list_type } : {} }).then((r) => r.data);

export const getSavedIds = () =>
  api.get<{ id: string; place_id: string; list_type: string }[]>("/saved").then((r) => r.data);

// ---- Availability ----

export interface AvailabilityResult {
  slots: string[];
  source: string;
  venue_url: string | null;
}

export const getAvailability = (slug: string, partySize = 2, date?: string) =>
  api.get<AvailabilityResult>(`/places/${slug}/availability`, {
    params: { party_size: partySize, ...(date ? { date } : {}) },
  }).then((r) => r.data);
