// basePath lets a GitHub Pages *project* site (served under /glaux) work.
// Default is root, which is what Vercel / Netlify / a custom domain want.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export", // static site: deploys to Vercel, Netlify, or GitHub Pages
  basePath,
  images: { unoptimized: true }, // required for a static export
  trailingSlash: true,
};

export default nextConfig;
