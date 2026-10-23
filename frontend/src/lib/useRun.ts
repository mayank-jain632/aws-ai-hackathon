import { useQuery } from "@tanstack/react-query";
import type { RunRequest, RunResponse } from "../types";
import fixture from "../../../data/fixtures/run_2023-01-01.json";

export const UNIVERSE = [
  "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "JPM", "XOM", "UNH", "PG", "CAT",
];

export type RunResult = { data: RunResponse; origin: "api" | "fixture" };

async function fetchRun(req: RunRequest): Promise<RunResult> {
  try {
    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error(`run ${res.status}`);
    return { data: (await res.json()) as RunResponse, origin: "api" };
  } catch {
    // API not up yet: fall back to the committed fixture so the UI still works.
    return { data: { ...(fixture as RunResponse), cutoff: req.cutoff }, origin: "fixture" };
  }
}

export function useRun(cutoff: string) {
  const req: RunRequest = { universe: UNIVERSE, cutoff, baseline: "equal_weight" };
  return useQuery({
    queryKey: ["run", cutoff],
    queryFn: () => fetchRun(req),
    placeholderData: (prev) => prev,
  });
}
