"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/store/session";

export default function Root() {
  const router = useRouter();
  const { user, adminToken } = useSession();
  useEffect(() => {
    if (user || adminToken) router.replace("/health");
    else router.replace("/login");
  }, [user, adminToken, router]);
  return null;
}
