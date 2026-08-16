"use client";

import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { useRouter, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import type { User } from "@supabase/supabase-js";

export default function Nav() {
  const router = useRouter();
  const pathname = usePathname();
  const supabase = createClient();
  const [user, setUser] = useState<User | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      setUser(data.user);
      setLoaded(true);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });

    return () => {
      listener.subscription.unsubscribe();
    };
  }, [supabase]);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.push("/auth/login");
    router.refresh();
  };

  const isOnSignUp = pathname?.startsWith("/auth/sign-up");

  return (
    <nav className="sticky top-0 z-50 flex items-center justify-between px-10 py-6 bg-card/80 backdrop-blur-md border-b border-border">
      <Link
        href={user ? "/people" : "/auth/login"}
        className="text-3xl font-bold tracking-tight text-primary"
      >
        CareOS
      </Link>
      {loaded && (
        <div className="flex items-center gap-3">
          {user ? (
            <>
              <Link
                href="/people"
                className="px-4 py-2 rounded-full text-sm font-medium text-foreground hover:bg-accent transition-colors"
              >
                People
              </Link>
              <button onClick={handleLogout} className="careos-button-secondary text-sm">
                Log out
              </button>
            </>
          ) : isOnSignUp ? (
            <Link href="/auth/login" className="careos-button text-sm">
              Log in
            </Link>
          ) : (
            <Link href="/auth/sign-up" className="careos-button text-sm">
              Sign up
            </Link>
          )}
        </div>
      )}
    </nav>
  );
}