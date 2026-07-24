import type { MetadataRoute } from "next";

const SITE = process.env.NEXT_PUBLIC_SITE_URL || "https://athena-swarm.github.io/athena";

const PATHS = [
  "",
  "/docs",
  "/docs/getting-started",
  "/docs/architecture",
  "/docs/self-evolution",
  "/docs/cli",
  "/docs/api",
  "/docs/configuration",
  "/docs/security",
];

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return PATHS.map((p) => ({
    url: `${SITE}${p}/`,
    lastModified: now,
    changeFrequency: "weekly",
    priority: p === "" ? 1 : 0.7,
  }));
}
