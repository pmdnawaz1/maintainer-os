export function RecentActivity() {
  return (
    <div className="rounded-lg border bg-card shadow-sm">
      <div className="border-b px-6 py-4">
        <h2 className="text-lg font-semibold">Recent Activity</h2>
        <p className="text-sm text-muted-foreground">
          Latest actions taken by your AI co-maintainer
        </p>
      </div>
      <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
        No activity yet — connect a GitHub repository to get started.
      </div>
    </div>
  );
}
