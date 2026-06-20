"use client";

import { useQuery } from "@tanstack/react-query";
import type {
  ActivityItem,
  DashboardStats,
  Issue,
  PullRequest,
  Release,
  Repository,
  SearchParams,
  WeeklyReport,
} from "@maintainer-os/types";
import { api } from "./api-client";

export function useIssues(params?: SearchParams) {
  const qs = new URLSearchParams();
  if (params?.repository_id != null) qs.set("repository_id", String(params.repository_id));
  if (params?.q) qs.set("q", params.q);
  if (params?.search_type) qs.set("search_type", params.search_type);
  const query = qs.toString();

  return useQuery<Issue[]>({
    queryKey: ["issues", params],
    queryFn: () => api.get<Issue[]>(`/api/v1/issues/${query ? `?${query}` : ""}`),
  });
}

export function usePullRequests(params?: SearchParams) {
  const qs = new URLSearchParams();
  if (params?.repository_id != null) qs.set("repository_id", String(params.repository_id));
  if (params?.q) qs.set("q", params.q);
  if (params?.search_type) qs.set("search_type", params.search_type);
  const query = qs.toString();

  return useQuery<PullRequest[]>({
    queryKey: ["pull-requests", params],
    queryFn: () => api.get<PullRequest[]>(`/api/v1/pull-requests/${query ? `?${query}` : ""}`),
  });
}

export function useRepositories() {
  return useQuery<Repository[]>({
    queryKey: ["repositories"],
    queryFn: () => api.get<Repository[]>("/api/v1/repositories/"),
  });
}

export function useDashboardStats() {
  return useQuery<DashboardStats>({
    queryKey: ["dashboard", "stats"],
    queryFn: () => api.get<DashboardStats>("/api/v1/dashboard/stats"),
    refetchInterval: 30_000,
  });
}

export function useRecentActivity(limit = 20) {
  return useQuery<ActivityItem[]>({
    queryKey: ["dashboard", "activity", limit],
    queryFn: () => api.get<ActivityItem[]>(`/api/v1/dashboard/activity?limit=${limit}`),
    refetchInterval: 30_000,
  });
}

export function useWeeklyReports(repo?: string, limit = 10) {
  const qs = new URLSearchParams();
  if (repo) qs.set("repo", repo);
  qs.set("limit", String(limit));

  return useQuery<WeeklyReport[]>({
    queryKey: ["reports", "weekly", repo, limit],
    queryFn: () => api.get<WeeklyReport[]>(`/api/v1/reports/weekly?${qs.toString()}`),
  });
}

export function useReleases(repo?: string, limit = 10) {
  const qs = new URLSearchParams();
  if (repo) qs.set("repo", repo);
  qs.set("limit", String(limit));

  return useQuery<Release[]>({
    queryKey: ["releases", repo, limit],
    queryFn: () => api.get<Release[]>(`/api/v1/releases/?${qs.toString()}`),
  });
}
