import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface SessionUser {
  subject: string;
  role: string;
  tenant_id: string;
  repo_scope: string[];
}

interface SessionState {
  user: SessionUser | null;
  activeRepo: string;
  adminToken: string;
  userRole: string | null;
  setUser: (user: SessionUser | null) => void;
  setActiveRepo: (repo: string) => void;
  setAdminToken: (token: string) => void;
  setUserRole: (role: string | null) => void;
  logout: () => void;
  authHeaders: () => Record<string, string>;
}

export const useSession = create<SessionState>()(
  persist(
    (set, get) => ({
      user: null,
      activeRepo: "",
      adminToken: "",
      userRole: null,

      setUser: (user) => set({ user }),
      setActiveRepo: (repo) => set({ activeRepo: repo }),
      setAdminToken: (token) => set({ adminToken: token }),
      setUserRole: (role) => set({ userRole: role }),
      logout: () => set({ user: null, adminToken: "", userRole: null }),

      authHeaders: (): Record<string, string> => {
        const { user, adminToken, activeRepo } = get();
        const headers: Record<string, string> = {};
        
        if (adminToken) {
          headers["X-Admin-Token"] = adminToken;
        } else if (user) {
          headers["X-Auth-Subject"] = user.subject;
          headers["X-Auth-Role"] = user.role;
          headers["X-Auth-Tenant-Id"] = user.tenant_id;
          headers["X-Auth-Repo-Scope"] = user.repo_scope.join(",");
        }
        
        // Always include X-Repo-Scope header with activeRepo if set
        if (activeRepo) {
          headers["X-Repo-Scope"] = activeRepo;
        }
        
        return headers;
      },
    }),
    { name: "ka-chow-session" }
  )
);
