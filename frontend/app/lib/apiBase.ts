export function getApiBaseUrl(): string {
  const fromEnv = process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL;
  if (fromEnv) {
    return fromEnv;
  }

  const vercelUrl = process.env.VERCEL_URL;
  if (vercelUrl) {
    return `https://${vercelUrl}`;
  }

  return "http://127.0.0.1:8000";
}

export function makeApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getApiBaseUrl()}${normalizedPath}`;
}
