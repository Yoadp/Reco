export interface Subcategory {
  id: string;
  label: string;
}

export interface Category {
  id: string;
  label: string;
  emoji: string;
  gradient: string;
  textColor: string;
  subcategories: Subcategory[];
}

export const CATEGORIES: Category[] = [
  {
    id: "middle-eastern",
    label: "מזרח תיכוני",
    emoji: "🥙",
    gradient: "from-amber-100 to-orange-200",
    textColor: "text-amber-800",
    subcategories: [
      { id: "hummus",      label: "חומוס" },
      { id: "falafel",     label: "פלאפל" },
      { id: "shawarma",    label: "שווארמה" },
      { id: "sabich",      label: "סביח" },
      { id: "lebanese",    label: "לבנוני" },
      { id: "moroccan",    label: "מרוקאי" },
    ],
  },
  {
    id: "israeli",
    label: "ישראלי",
    emoji: "🇮🇱",
    gradient: "from-blue-100 to-sky-200",
    textColor: "text-blue-800",
    subcategories: [
      { id: "israeli",     label: "ישראלי" },
      { id: "gourmet",     label: "גורמה" },
      { id: "breakfast",   label: "ארוחת בוקר" },
      { id: "bistro",      label: "ביסטרו" },
      { id: "street-food", label: "אוכל רחוב" },
    ],
  },
  {
    id: "meat",
    label: "בשר וגריל",
    emoji: "🥩",
    gradient: "from-red-100 to-rose-200",
    textColor: "text-red-800",
    subcategories: [
      { id: "steak",       label: "סטייק" },
      { id: "grill",       label: "גריל" },
      { id: "burger",      label: "המבורגר" },
      { id: "argentinian", label: "ארגנטינאי" },
      { id: "south-american", label: "דרום אמריקאי" },
    ],
  },
  {
    id: "japanese",
    label: "יפני",
    emoji: "🍣",
    gradient: "from-rose-100 to-red-200",
    textColor: "text-rose-800",
    subcategories: [
      { id: "sushi",       label: "סושי" },
      { id: "japanese",    label: "יפני" },
      { id: "ramen",       label: "ראמן" },
      { id: "sashimi",     label: "סשימי" },
      { id: "tempura",     label: "טמפורה" },
    ],
  },
  {
    id: "asian",
    label: "אסייתי",
    emoji: "🍜",
    gradient: "from-violet-100 to-purple-200",
    textColor: "text-violet-800",
    subcategories: [
      { id: "asian",       label: "אסייתי" },
      { id: "chinese",     label: "סיני" },
      { id: "thai",        label: "תאילנדי" },
      { id: "asian-fusion",label: "פיוז'ן אסייתי" },
      { id: "vietnamese",  label: "וייטנאמי" },
    ],
  },
  {
    id: "italian",
    label: "איטלקי",
    emoji: "🍕",
    gradient: "from-emerald-100 to-green-200",
    textColor: "text-emerald-800",
    subcategories: [
      { id: "pizza",       label: "פיצה" },
      { id: "pasta",       label: "פסטה" },
      { id: "italian",     label: "איטלקי" },
      { id: "risotto",     label: "ריזוטו" },
      { id: "tiramisu",    label: "טירמיסו" },
    ],
  },
  {
    id: "european",
    label: "אירופאי",
    emoji: "🥐",
    gradient: "from-yellow-100 to-amber-100",
    textColor: "text-yellow-800",
    subcategories: [
      { id: "french",      label: "צרפתי" },
      { id: "greek",       label: "יווני" },
      { id: "european",    label: "אירופאי" },
      { id: "bistro-eu",   label: "ביסטרו" },
    ],
  },
  {
    id: "mediterranean",
    label: "ים תיכוני",
    emoji: "🐟",
    gradient: "from-sky-100 to-cyan-200",
    textColor: "text-sky-800",
    subcategories: [
      { id: "mediterranean", label: "ים תיכוני" },
      { id: "seafood",     label: "פירות ים" },
      { id: "fish",        label: "דגים" },
      { id: "calamari",    label: "קלמארי" },
    ],
  },
  {
    id: "bar",
    label: "בר ומשקאות",
    emoji: "🍺",
    gradient: "from-orange-100 to-amber-200",
    textColor: "text-orange-800",
    subcategories: [
      { id: "bar",         label: "בר" },
      { id: "pub",         label: "פאב" },
      { id: "cocktails",   label: "קוקטיילים" },
      { id: "wine",        label: "יין" },
      { id: "whiskey",     label: "וויסקי" },
    ],
  },
  {
    id: "cafe",
    label: "קפה ובוקר",
    emoji: "☕",
    gradient: "from-stone-100 to-amber-100",
    textColor: "text-stone-700",
    subcategories: [
      { id: "coffee",      label: "קפה" },
      { id: "breakfast-cafe", label: "ארוחת בוקר" },
      { id: "brunch",      label: "ברנץ׳" },
      { id: "pastry",      label: "מאפים" },
      { id: "shakshuka",   label: "שקשוקה" },
    ],
  },
  {
    id: "mexican",
    label: "מקסיקני",
    emoji: "🌮",
    gradient: "from-orange-100 to-amber-200",
    textColor: "text-orange-800",
    subcategories: [
      { id: "taco",        label: "טאקו" },
      { id: "burrito",     label: "בוריטו" },
      { id: "nachos",      label: "נאצ׳וס" },
      { id: "quesadilla",  label: "קסדייה" },
    ],
  },
  {
    id: "fast-food",
    label: "מזון מהיר",
    emoji: "🍔",
    gradient: "from-yellow-100 to-amber-200",
    textColor: "text-amber-800",
    subcategories: [
      { id: "hamburger",   label: "המבורגר" },
      { id: "fast-food",   label: "מזון מהיר" },
      { id: "pizza-ff",    label: "פיצה" },
      { id: "falafel-ff",  label: "פלאפל" },
    ],
  },
];

export function getCategoryById(id: string): Category | undefined {
  return CATEGORIES.find((c) => c.id === id);
}

export const CUISINE_TO_GRADIENT: Record<string, string> = {
  // Israeli / Middle Eastern
  "ישראלי":          "from-blue-100 to-sky-200",
  "גורמה":           "from-blue-100 to-sky-200",
  "ביסטרו":          "from-yellow-100 to-amber-100",
  "אוכל רחוב":       "from-orange-100 to-amber-200",
  "ארוחת בוקר":      "from-stone-100 to-amber-100",
  "מזרח תיכוני":     "from-amber-100 to-orange-200",
  "חומוס":           "from-amber-100 to-orange-200",
  "פלאפל":           "from-amber-100 to-orange-200",
  "שווארמה":         "from-amber-100 to-orange-200",
  "לבנוני":          "from-amber-100 to-orange-200",
  "מרוקאי":          "from-amber-100 to-orange-200",
  // Meat
  "בשר":             "from-red-100 to-rose-200",
  "גריל":            "from-red-100 to-rose-200",
  "סטייק":           "from-red-100 to-rose-200",
  "המבורגר":         "from-red-100 to-rose-200",
  "ארגנטינאי":       "from-red-100 to-rose-200",
  "דרום אמריקאי":    "from-red-100 to-rose-200",
  // Japanese
  "יפני":            "from-rose-100 to-red-200",
  "סושי":            "from-rose-100 to-red-200",
  // Asian
  "אסייתי":          "from-violet-100 to-purple-200",
  "סיני":            "from-violet-100 to-purple-200",
  "תאילנדי":         "from-violet-100 to-purple-200",
  "פיוז'ן אסייתי":   "from-violet-100 to-purple-200",
  // Italian
  "איטלקי":          "from-emerald-100 to-green-200",
  "פיצה":            "from-emerald-100 to-green-200",
  "פסטה":            "from-emerald-100 to-green-200",
  // European
  "צרפתי":           "from-yellow-100 to-amber-100",
  "יווני":           "from-yellow-100 to-amber-100",
  "אירופאי":         "from-yellow-100 to-amber-100",
  // Mediterranean / seafood
  "ים תיכוני":       "from-sky-100 to-cyan-200",
  "פירות ים":        "from-sky-100 to-cyan-200",
  // Bar / drinks
  "בר":              "from-orange-100 to-amber-200",
  "פאב":             "from-orange-100 to-amber-200",
  "קוקטיילים":       "from-orange-100 to-amber-200",
  "יין":             "from-purple-100 to-violet-200",
  // Cafe
  "קפה":             "from-stone-100 to-amber-100",
  "מאפים":           "from-stone-100 to-amber-100",
  // Fast food
  "מזון מהיר":       "from-yellow-100 to-amber-200",
  // Mexican
  "מקסיקני":         "from-orange-100 to-amber-200",
};

export function getPlaceGradient(cuisine: string[] | null): string {
  if (!cuisine || cuisine.length === 0) return "from-indigo-100 to-purple-100";
  for (const c of cuisine) {
    const g = CUISINE_TO_GRADIENT[c];
    if (g) return g;
  }
  return "from-indigo-100 to-purple-100";
}

export function getPlaceEmoji(cuisine: string[] | null): string {
  const map: Record<string, string> = {
    // Israeli / Middle Eastern
    "ישראלי": "🇮🇱", "גורמה": "⭐", "ביסטרו": "🥐", "ארוחת בוקר": "🍳",
    "מזרח תיכוני": "🥙", "חומוס": "🥙", "פלאפל": "🧆", "שווארמה": "🌯",
    "לבנוני": "🥙", "מרוקאי": "🥘", "אוכל רחוב": "🌯",
    // Meat / grill
    "בשר": "🥩", "גריל": "🔥", "סטייק": "🥩", "המבורגר": "🍔",
    "ארגנטינאי": "🥩", "דרום אמריקאי": "🥩",
    // Japanese
    "יפני": "🍣", "סושי": "🍣", "ראמן": "🍜", "סשימי": "🐟",
    // Asian
    "אסייתי": "🍜", "סיני": "🥡", "תאילנדי": "🍛", "פיוז'ן אסייתי": "🍱",
    // Italian
    "איטלקי": "🍝", "פיצה": "🍕", "פסטה": "🍝",
    // European
    "צרפתי": "🥐", "יווני": "🫒", "אירופאי": "🥐",
    // Mediterranean / seafood
    "ים תיכוני": "🐟", "פירות ים": "🦞",
    // Bar / drinks
    "בר": "🍺", "פאב": "🍺", "קוקטיילים": "🍹", "יין": "🍷",
    // Cafe
    "קפה": "☕", "מאפים": "🥐",
    // Fast food
    "מזון מהיר": "🍟",
    // Mexican
    "מקסיקני": "🌮", "טאקו": "🌮",
  };
  if (!cuisine || cuisine.length === 0) return "🍽️";
  for (const c of cuisine) {
    if (map[c]) return map[c];
  }
  return "🍽️";
}
