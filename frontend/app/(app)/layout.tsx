"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { useSession } from "@/store/session";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, adminToken } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (!user && !adminToken) {
      router.replace("/login");
    }
  }, [user, adminToken, router]);

  if (!user && !adminToken) return null;

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#09090b]">
      <Sidebar />
      <main className="flex-1 overflow-hidden flex flex-col min-w-0">
        {children}
      </main>
      <CommandPalette />
    </div>
  );
}
