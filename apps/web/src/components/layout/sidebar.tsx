"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  GitPullRequest,
  CircleDot,
  BookOpen,
  Settings,
  BrainCircuit,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/dashboard/issues", label: "Issues", icon: CircleDot },
  { href: "/dashboard/pull-requests", label: "Pull Requests", icon: GitPullRequest },
  { href: "/dashboard/memory", label: "Project Memory", icon: BrainCircuit },
  { href: "/dashboard/docs", label: "Documentation", icon: BookOpen },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-60 flex-col border-r bg-sidebar px-3 py-4">
      <div className="mb-6 flex items-center gap-2 px-2">
        <BrainCircuit className="h-6 w-6 text-primary" />
        <span className="text-lg font-bold">Maintainer OS</span>
      </div>
      <nav className="flex flex-col gap-1">
        {navItems.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              pathname === href || (href !== "/dashboard" && pathname.startsWith(href))
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
