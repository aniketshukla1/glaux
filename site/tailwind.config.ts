import type { Config } from "tailwindcss";

// Brand tokens shared with the Athena app: rgb triplets in CSS vars so opacity
// modifiers (bg-accent/10) work everywhere.
const rgb = (v: string) => `rgb(var(${v}) / <alpha-value>)`;

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx,md,mdx}",
    "./mdx-components.tsx",
  ],
  theme: {
    extend: {
      colors: {
        bg: rgb("--bg"),
        surface: rgb("--surface"),
        fg: rgb("--fg"),
        muted: rgb("--muted"),
        faint: rgb("--faint"),
        line: rgb("--line"),
        accent: rgb("--accent"),
        accent2: rgb("--accent2"),
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      maxWidth: { content: "1180px" },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: { "fade-up": "fade-up .6s ease both" },
      typography: () => ({
        invert: {
          css: {
            "--tw-prose-body": "rgb(var(--muted))",
            "--tw-prose-headings": "rgb(var(--fg))",
            "--tw-prose-bold": "rgb(var(--fg))",
            "--tw-prose-links": "rgb(var(--accent))",
            "--tw-prose-code": "rgb(var(--accent))",
            "--tw-prose-quotes": "rgb(var(--muted))",
            "--tw-prose-bullets": "rgb(var(--faint))",
            "--tw-prose-hr": "rgb(var(--line) / 0.12)",
            "--tw-prose-th-borders": "rgb(var(--line) / 0.2)",
            "--tw-prose-td-borders": "rgb(var(--line) / 0.1)",
          },
        },
      }),
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
