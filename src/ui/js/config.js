/**
 * Application API Configuration for SIP Discovery Engine
 * 
 * In local development or when using Vercel rewrites,
 * window.API_BASE_URL defaults to "" (same-origin relative requests).
 * 
 * If connecting directly to a remote backend (e.g. Render) without reverse proxy,
 * set window.API_BASE_URL = "https://your-service.onrender.com".
 */
window.API_BASE_URL = window.API_BASE_URL || "";

function getApiUrl(path) {
  const base = (window.API_BASE_URL || "").replace(/\/+$/, "");
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${cleanPath}`;
}
