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
      { id: "hummus", label: "חומוס" },
      { id: "falafel", label: "פלאפל" },
      { id: "shawarma", label: "שווארמה" },
      { id: "sabich", label: "סביח" },
      { id: "kubeh", label: "קובה" },
    ],
  },
  {
    id: "japanese",
    label: "יפני",
    emoji: "🍣",
    gradient: "from-rose-100 to-red-200",
    textColor: "text-rose-800",
    subcategories: [
      { id: "sushi", label: "סושי" },
      { id: "ramen", label: "ראמן" },
      { id: "sashimi", label: "סשימי" },
      { id: "tempura", label: "טמפורה" },
      { id: "udon", label: "אודון" },
    ],
  },
  {
    id: "italian",
    label: "איטלקי",
    emoji: "🍕",
    gradient: "from-emerald-100 to-green-200",
    textColor: "text-emerald-800",
    subcategories: [
      { id: "pizza", label: "פיצה" },
      { id: "pasta", label: "פסטה" },
      { id: "risotto", label: "ריזוטו" },
      { id: "lasagna", label: "לזניה" },
      { id: "tiramisu", label: "טירמיסו" },
    ],
  },
  {
    id: "burger",
    label: "המבורגר",
    emoji: "🍔",
    gradient: "from-yellow-100 to-amber-200",
    textColor: "text-amber-800",
    subcategories: [
      { id: "classic-burger", label: "קלאסי" },
      { id: "smoky-burger", label: "סמוקי" },
      { id: "vegan-burger", label: "טבעוני" },
      { id: "smash-burger", label: "סמאש" },
      { id: "chicken-burger", label: "עוף" },
    ],
  },
  {
    id: "mexican",
    label: "מקסיקני",
    emoji: "🌮",
    gradient: "from-orange-100 to-amber-200",
    textColor: "text-orange-800",
    subcategories: [
      { id: "taco", label: "טאקו" },
      { id: "burrito", label: "בוריטו" },
      { id: "nachos", label: "נאצ׳וס" },
      { id: "quesadilla", label: "קסדייה" },
      { id: "guacamole", label: "גוואקמולה" },
    ],
  },
  {
    id: "asian",
    label: "אסייתי",
    emoji: "🍜",
    gradient: "from-violet-100 to-purple-200",
    textColor: "text-violet-800",
    subcategories: [
      { id: "thai", label: "תאילנדי" },
      { id: "vietnamese", label: "וייטנאמי" },
      { id: "pad-thai", label: "פאד תאי" },
      { id: "dim-sum", label: "דים סאם" },
      { id: "fusion", label: "פיוז׳ן" },
    ],
  },
  {
    id: "seafood",
    label: "ים תיכוני",
    emoji: "🐟",
    gradient: "from-sky-100 to-cyan-200",
    textColor: "text-sky-800",
    subcategories: [
      { id: "fish", label: "דגים" },
      { id: "seafood", label: "פירות ים" },
      { id: "chips", label: "צ׳יפס" },
      { id: "calamari", label: "קלמארי" },
    ],
  },
  {
    id: "cafe",
    label: "קפה ובוקר",
    emoji: "☕",
    gradient: "from-stone-100 to-amber-100",
    textColor: "text-stone-700",
    subcategories: [
      { id: "breakfast", label: "ארוחת בוקר" },
      { id: "brunch", label: "ברנץ׳" },
      { id: "coffee", label: "קפה" },
      { id: "pastry", label: "מאפים" },
      { id: "shakshuka", label: "שקשוקה" },
    ],
  },
];

export function getCategoryById(id: string): Category | undefined {
  return CATEGORIES.find((c) => c.id === id);
}

export const CUISINE_TO_GRADIENT: Record<string, string> = {
  "מזרח תיכוני": "from-amber-100 to-orange-200",
  "חומוס": "from-amber-100 to-orange-200",
  "ישראלי": "from-sky-100 to-blue-200",
  "אוכל רחוב": "from-orange-100 to-amber-200",
  "יפני": "from-rose-100 to-red-200",
  "ברזילאי": "from-yellow-100 to-green-100",
  "פיוז׳ן אסייתי": "from-violet-100 to-purple-200",
  "איטלקי": "from-emerald-100 to-green-200",
  "פיצה": "from-emerald-100 to-green-200",
  "ים תיכוני": "from-sky-100 to-cyan-200",
  "פירות ים": "from-sky-100 to-cyan-200",
};

export function getPlaceGradient(cuisine: string[] | null): string {
  if (!cuisine || cuisine.length === 0) return "from-indigo-100 to-purple-100";
  return CUISINE_TO_GRADIENT[cuisine[0]] ?? "from-indigo-100 to-purple-100";
}

export function getPlaceEmoji(cuisine: string[] | null): string {
  const map: Record<string, string> = {
    "מזרח תיכוני": "🥙", "חומוס": "🥙", "ישראלי": "🇮🇱", "אוכל רחוב": "🌯",
    "יפני": "🍣", "ברזילאי": "🥩", "פיוז׳ן אסייתי": "🍜",
    "איטלקי": "🍝", "פיצה": "🍕",
    "ים תיכוני": "🐟", "פירות ים": "🦞",
  };
  if (!cuisine || cuisine.length === 0) return "🍽️";
  return map[cuisine[0]] ?? "🍽️";
}
