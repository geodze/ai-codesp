/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output для минимального Docker-образа на Railway
  output: 'standalone',
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
}

export default nextConfig
