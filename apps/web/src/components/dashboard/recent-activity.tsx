"use client";

import { AlertCircle } from "lucide-react";
import { useRecentActivity } from "@/lib/use-api-hooks";
import { Skeleton } from "@/components/ui/skeleton";

function ActivitySkeleton() {
  return (
    <ul className="divide-y">
      {Array.from({ length: 5 }).map((_, i) => (
        <li key={i} className="flex items-center gap-3 px-6 py-3">
          <Skeleton className="h-5 w-16 rounded-full shrink-0" />
          <Skeleton className="h-4 flex-1" />
          <Skeleton className="h-4 w-20 shrink-0" />
        </li>
      ))}
    </ul>
  );
}

export function RecentActivity() {
  const { data: activity, isLoading, isError } = useRecentActivity();

  return (
    <div className="rounded-lg border bg-card shadow-sm">
      <div className="border-b px-6 py-4">
        <h2 className="text-lg font-semibold">Recent Activity</h2>
        <p className="text-sm text-muted-foreground">
          Latest actions taken by your AI co-maintainer
        </p>
      </div>

      {isLoading ? (
        <ActivitySkeleton />
      ) : isError ? (
        <div className="flex items-center gap-2 px-6 py-12 text-destructive text-sm">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load activity. Retrying automatically.
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
