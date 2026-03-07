export function getApiBaseUrl(origin?: string): string {
  const fromEnv = process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL;
  if (fromEnv) {
    return fromEnv;
  }

  if (origin) {
    return origin;
  }

  return "http://127.0.0.1:8000";
}

export function makeApiUrl(path: string, origin?: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getApiBaseUrl(origin)}${normalizedPath}`;
}

export function getRequestOriginFromHeaders(input: Headers): string | undefined {
  const host = input.get("x-forwarded-host") || input.get("host");
  if (!host) {
    return undefined;
  }

  const proto = input.get("x-forwarded-proto") || (host.includes("localhost") ? "http" : "https");
  return `${proto}://${host}`;
}
