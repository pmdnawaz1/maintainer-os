export type BumpType = "major" | "minor" | "patch" | "auto";

export interface ReleaseChangeEntry {
  number: number;
  title: string;
  author: string;
  url: string;
}

export interface ReleaseChangelog {
  version: string;
  previous_version: string | null;
  generated_at: string;
  total_prs: number;
  changes: {
    breaking: ReleaseChangeEntry[];
    features: ReleaseChangeEntry[];
    fixes: ReleaseChangeEntry[];
    docs: ReleaseChangeEntry[];
    other: ReleaseChangeEntry[];
  };
}

export interface Release {
  id: number;
  repository: string;
  version: string;
  previous_version: string | null;
  bump_type: Exclude<BumpType, "auto">;
  changelog: ReleaseChangelog;
  markdown: string;
  release_url: string | null;
  github_release_id: number | null;
  created_at: string;
}
