export * from "./repository";
export * from "./issue";
export * from "./pull_request";
export * from "./dashboard";
export * from "./report";
export * from "./release";

// Search
export type SearchType = "hybrid" | "semantic" | "keyword";

export interface SearchParams {
  q?: string;
  search_type?: SearchType;
  repository_id?: number;
}

// Generic API error shape
export interface ApiError {
  detail: string;
}
