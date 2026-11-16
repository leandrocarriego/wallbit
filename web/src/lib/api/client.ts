import type { components } from "./schema";

export type Schemas = components["schemas"];
export type S<K extends keyof Schemas> = Schemas[K];

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

type Options = {
  method?: "GET" | "POST" | "PUT";
  body?: unknown;
  actor?: string;
  headers?: Record<string, string>;
};

/** Typed fetch against the API. `actor` goes in X-Actor so every action is audited. */
export async function api<T>(path: string, { method = "GET", body, actor, headers }: Options = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(actor ? { "X-Actor": actor } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as { code?: string; detail?: string };
    throw new ApiError(response.status, problem.code ?? "error", problem.detail ?? "Algo salió mal. Probá de nuevo.");
  }
  return (await response.json()) as T;
}

export const ACCOUNTANT = "accountant-demo";
export const userActor = (clientId: string) => `client:${clientId}`;
