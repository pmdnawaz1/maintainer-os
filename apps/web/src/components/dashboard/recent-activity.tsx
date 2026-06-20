"use client";

import { useRecentActivity } from "@/lib/use-api-hooks";

export function RecentActivity() {
  const { data: activity, isLoading } = useRecentActivity();

  return (
    <div className="rounded-lg border bg-card shadow-sm">
      <div className="border-b px-6 py-4">
        <h2 className="text-lg font-semibold">Recent Activity</h2>
        <p className="text-sm text-muted-foreground">
          Latest actions taken by your AI co-maintainer
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
          Loading…
        </div>
      ) : !activity?.length ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
          No activity yet — connect a GitHub repository to get started.
        </div>
      ) : (
        <ul className="divide-y">
          {activity.map((item) => (
            <li
              key={`${item.type}-${item.id}`}
              className="flex items-center gap-3 px-6 py-3"
            >
              <span className="shrink-0 text-xs bg-muted px-2 py-0.5 rounded-full capitalize">
                {item.type.replace("_", " ")}
              </span>
              <span className="flex-1 text-sm font-medium truncate">{item.title}</span>
              <span className="shrink-0 text-xs text-muted-foreground">{item.repo}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
