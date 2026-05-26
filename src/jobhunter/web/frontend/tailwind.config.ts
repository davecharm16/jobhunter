import type { Config } from "tailwindcss";
import { tokens } from "./src/design-tokens";

const typography = tokens.typography as Record<
  string,
  { fontSize: string; lineHeight: string; fontWeight: string; letterSpacing?: string }
>;

const fontSize: Record<string, [string, Record<string, string>]> = {};
const fontFamily: Record<string, string[]> = {};
for (const [name, scale] of Object.entries(typography)) {
  const meta: Record<string, string> = {
    lineHeight: scale.lineHeight,
    fontWeight: scale.fontWeight,
  };
  if (scale.letterSpacing) meta.letterSpacing = scale.letterSpacing;
  fontSize[name] = [scale.fontSize, meta];
  fontFamily[name] = ["Inter", "system-ui", "sans-serif"];
}
// Story 8.3: IBM Plex font families for UI chrome and monospace
fontFamily["ui"] = ["IBM Plex Sans", "sans-serif"];
fontFamily["mono"] = ["IBM Plex Mono", "monospace"];

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: tokens.colors as Record<string, string>,
      borderRadius: tokens.rounded as Record<string, string>,
      spacing: tokens.spacing as Record<string, string>,
      fontSize,
      fontFamily,
    },
  },
} satisfies Config;
