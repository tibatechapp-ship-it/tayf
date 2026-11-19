/** Studio job presets: built-in catalog plus user recipes in localStorage.
 *
 * No backend fields, no migrations: a preset only fills the five values that
 * `createJob` already accepts. No voice/TTS field exists because Tayf has no
 * audio stage yet.
 */

import { ASPECTS, STYLES, type Copy } from "./i18n/dictionary";

export interface Preset {
  id: string;
  name: string;
  nameKey?: keyof Copy;
  prompt: string;
  numScenes: number;
  aspect: string;
  style: string;
  requireApprovals: boolean;
  builtin: boolean;
}

export interface PresetValues {
  prompt: string;
  numScenes: number;
  aspect: string;
  style: string;
  requireApprovals: boolean;
}

export const MAX_CUSTOM_PRESETS = 12;
export const MAX_PRESET_NAME_LENGTH = 60;

const STORAGE_KEY = "tayf.presets";
const MIN_PROMPT_LENGTH = 3;
const MAX_PROMPT_LENGTH = 2000;
const STYLE_VALUES: readonly string[] = STYLES;
const ASPECT_VALUES: readonly string[] = ASPECTS;

export const BUILTIN_PRESETS: readonly Preset[] = [
  {
    id: "builtin-cinematic-arabic",
    name: "Cinematic Arabic",
    nameKey: "presetCinematicArabic",
    prompt:
      "لقطة سينمائية عربية بطيئة لمدينة قديمة عند الفجر، إضاءة دافئة، حركة كاميرا ناعمة، عمق مجال واضح.",
    numScenes: 4,
    aspect: "16:9",
    style: "cinematic",
    requireApprovals: false,
    builtin: true,
  },
  {
    id: "builtin-vertical-reel",
    name: "Vertical reel",
    nameKey: "presetVerticalReel",
    prompt:
      "فيديو عمودي قصير لمنتج عربي، لقطة مقربة ثم لقطة واسعة، إيقاع سريع، تباين عالٍ.",
    numScenes: 3,
    aspect: "9:16",
    style: "cinematic",
    requireApprovals: false,
    builtin: true,
  },
  {
    id: "builtin-review-first",
    name: "Review first",
    nameKey: "presetReviewFirst",
    prompt:
      "مشهد عربي واقعي يُراجع نصه ولوحته القصصية قبل اعتماد أي مرحلة تالية.",
    numScenes: 4,
    aspect: "16:9",
    style: "photorealistic",
    requireApprovals: true,
    builtin: true,
  },
  {
    id: "builtin-anime-story",
    name: "Anime story",
    nameKey: "presetAnimeStory",
    prompt:
      "قصة أنمي عربية قصيرة عن طفل يكتشف مدينة تحت المطر، ألوان زاهية، تعبير وجه واضح.",
    numScenes: 5,
    aspect: "16:9",
    style: "anime",
    requireApprovals: false,
    builtin: true,
  },
  {
    id: "builtin-noir-short",
    name: "Noir short",
    nameKey: "presetNoirShort",
    prompt:
      "لقطة نوار عربية قصيرة في زقاق ليلي، ظلال قوية، أبيض وأسود، إيقاع هادئ.",
    numScenes: 3,
    aspect: "1:1",
    style: "noir",
    requireApprovals: false,
    builtin: true,
  },
];

function isPreset(value: unknown): value is Preset {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "string" &&
    candidate.id.length > 0 &&
    candidate.id.length <= 80 &&
    typeof candidate.name === "string" &&
    candidate.name.trim().length > 0 &&
    candidate.name.length <= MAX_PRESET_NAME_LENGTH &&
    typeof candidate.prompt === "string" &&
    candidate.prompt.trim().length >= MIN_PROMPT_LENGTH &&
    candidate.prompt.length <= MAX_PROMPT_LENGTH &&
    typeof candidate.numScenes === "number" &&
    Number.isInteger(candidate.numScenes) &&
    candidate.numScenes >= 2 &&
    candidate.numScenes <= 24 &&
    typeof candidate.aspect === "string" &&
    ASPECT_VALUES.includes(candidate.aspect) &&
    typeof candidate.style === "string" &&
    STYLE_VALUES.includes(candidate.style) &&
    typeof candidate.requireApprovals === "boolean" &&
    candidate.builtin === false
  );
}

/** Corrupt or oversized localStorage data is ignored, never thrown at the UI. */
export function loadCustomPresets(): Preset[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const seen = new Set<string>();
    const result: Preset[] = [];
    for (const entry of parsed) {
      if (!isPreset(entry) || seen.has(entry.id)) continue;
      seen.add(entry.id);
      result.push(entry);
      if (result.length >= MAX_CUSTOM_PRESETS) break;
    }
    return result;
  } catch {
    return [];
  }
}

/** Stores only the portable fields; a caller catches quota/availability errors. */
export function saveCustomPresets(presets: readonly Preset[]): void {
  const portable = presets
    .filter((preset) => !preset.builtin)
    .slice(0, MAX_CUSTOM_PRESETS)
    .map((preset) => ({
      id: preset.id,
      name: preset.name,
      prompt: preset.prompt,
      numScenes: preset.numScenes,
      aspect: preset.aspect,
      style: preset.style,
      requireApprovals: preset.requireApprovals,
      builtin: false as const,
    }));
  localStorage.setItem(STORAGE_KEY, JSON.stringify(portable));
}

export function makeCustomPreset(name: string, values: PresetValues): Preset {
  return {
    id: `custom-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    name: name.trim(),
    prompt: values.prompt.trim(),
    numScenes: values.numScenes,
    aspect: values.aspect,
    style: values.style,
    requireApprovals: values.requireApprovals,
    builtin: false,
  };
}
