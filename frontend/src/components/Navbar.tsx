import { Link, useNavigate } from "react-router-dom";
import { LogOut, Settings, ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/store/authStore";

export function Navbar() {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur">
      <div className="mx-auto flex h-12 max-w-screen-xl items-center justify-between px-4">
        {/* Logo */}
        <Link to="/dashboard" className="flex items-center gap-3">
          <div className="flex h-6 w-6 shrink-0 items-center justify-center bg-primary font-display text-[10px] font-bold leading-none text-primary-foreground">
            CG
          </div>
          <span className="hidden font-display text-sm font-bold uppercase tracking-[0.18em] text-foreground sm:block">
            Clanker Gauntlet
          </span>
        </Link>

        {/* Nav links */}
        <nav className="hidden items-center gap-6 md:flex">
          <Link
            to="/dashboard"
            className="font-display text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground transition-colors hover:text-foreground"
          >
            Dashboard
          </Link>
        </nav>

        {/* User menu */}
        {user ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-8 gap-1.5 px-2.5 font-display text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
              >
                <span className="max-w-28 truncate">{user.display_name}</span>
                <ChevronDown className="h-3 w-3 opacity-50" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48 rounded-sm border-border bg-popover">
              <DropdownMenuLabel className="py-2 font-normal">
                <p className="font-display text-[10px] uppercase tracking-wider text-muted-foreground">
                  {user.email}
                </p>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link to="/account" className="cursor-pointer text-xs">
                  <Settings className="mr-2 h-3.5 w-3.5" />
                  Account settings
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={handleLogout}
                className="cursor-pointer text-xs text-destructive focus:text-destructive"
              >
                <LogOut className="mr-2 h-3.5 w-3.5" />
                Log out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <Button
            asChild
            size="sm"
            className="h-7 rounded-sm px-3 font-display text-xs font-bold uppercase tracking-[0.12em]"
          >
            <Link to="/login">Sign in</Link>
          </Button>
        )}
      </div>
    </header>
  );
}
