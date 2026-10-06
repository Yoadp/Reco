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
  hours: Record<string, string> | null;
  sources?: DataSource[];
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
}

// ---- API helpers ----

export const searchPlaces = (params: {
  q?: string;
  city?: string;
  cuisine?: string;
  price_range?: number;
  nlp?: boolean;
  limit?: number;
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
