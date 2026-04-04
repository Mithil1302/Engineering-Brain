"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Shield, ChevronRight, Key, Loader2 } from "lucide-react";
import { useSession } from "@/store/session";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function LoginPage() {
  const router = useRouter();
  const { setUser, setAdminToken, setActiveRepo } = useSession();
  
  const [step, setStep] = useState<1 | 2>(1);
  const [pat, setPat] = useState("");
  const [repos, setRepos] = useState<string[]>([]);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("developer");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const ROLES = ["platform-admin", "security-admin", "platform-lead", "architect", "developer", "sre"];

  async function verifyGithubToken(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (!pat.trim()) throw new Error("GitHub Token is required");

      // Fetch user
      const userRes = await fetch("https://api.github.com/user", {
        headers: { Authorization: `Bearer ${pat}` }
      });
      if (!userRes.ok) throw new Error("Invalid GitHub Token");
      const userData = await userRes.json();
      setUsername(userData.login);

      // Fetch repos
      const repoRes = await fetch("https://api.github.com/user/repos?per_page=100&sort=updated", {
        headers: { Authorization: `Bearer ${pat}` }
      });
      if (!repoRes.ok) throw new Error("Failed to fetch repositories");
      const repoData: Array<{ full_name: string }> = await repoRes.json();
      
      const repoNames = repoData.map(r => r.full_name);
      setRepos(repoNames);
      if (repoNames.length > 0) setSelectedRepo(repoNames[0]);
      
      setStep(2);
    } catch (err: any) {
      setError(err.message || "Failed to verify token");
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedRepo) {
      setError("Please select a repository");
      return;
    }

    // Since the system needs a backend policy token, we will seamlessly pass the PAT as the admin token 
    // for local development, or just a dummy token if the backend relies on GITHUB_TOKEN directly.
    setAdminToken(pat);
    
    // Set user claims
    setUser({
      subject: username,
      role: role,
      tenant_id: "default",
      repo_scope: [selectedRepo, "*"],
    });
    
    setActiveRepo(selectedRepo);
    router.replace("/health");
  }

  return (
    <div className="min-h-screen bg-[#09090b] flex items-center justify-center p-4 selection:bg-indigo-500/30">
      <div className="w-full max-w-sm">
        {/* Header */}
        <div className="mb-8 flex flex-col items-center">
          <div className="w-12 h-12 border border-slate-800 bg-[#0c0c0e] rounded-xl flex items-center justify-center mb-4">
            <Shield className="w-6 h-6 text-slate-100" />
          </div>
          <h1 className="text-xl font-semibold text-slate-100">KA-CHOW</h1>
          <p className="text-sm text-slate-500 mt-1">Autonomous Engineering Brain</p>
        </div>

        {/* Card */}
        <div className="bg-[#0c0c0e] border border-slate-800 rounded-xl p-6 shadow-sm">
          {step === 1 ? (
            <form onSubmit={verifyGithubToken} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5 flex items-center gap-2">
                  <Key className="w-4 h-4" /> Personal Access Token
                </label>
                <Input
                  type="password"
                  value={pat}
                  onChange={e => setPat(e.target.value)}
                  placeholder="ghp_xxxxxxxxxxxx"
                  className="bg-[#09090b] border-slate-800 focus-visible:ring-1 focus-visible:ring-slate-500"
                />
                <p className="text-[11px] text-slate-500 mt-2">
                  Requires <code className="text-slate-400">repo</code> scope to fetch your repositories.
                </p>
              </div>

              {error && (
                <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-md px-3 py-2">
                  {error}
                </div>
              )}

              <Button 
                type="submit" 
                className="w-full bg-slate-100 text-slate-900 hover:bg-slate-200" 
                disabled={loading || !pat}
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                Continue <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            </form>
          ) : (
            <form onSubmit={handleLogin} className="space-y-4">
              <div className="flex items-center justify-between pb-4 border-b border-slate-800">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center text-xs font-semibold text-slate-300 uppercase">
                    {username.slice(0, 2)}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-200">{username}</p>
                    <p className="text-xs text-slate-500">Authenticated via GitHub</p>
                  </div>
                </div>
                <button type="button" onClick={() => setStep(1)} className="text-xs text-slate-500 hover:text-slate-300 underline">
                  Change
                </button>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Select Repository</label>
                <select
                  value={selectedRepo}
                  onChange={e => setSelectedRepo(e.target.value)}
                  aria-label="Select repository"
                  className="w-full rounded-md bg-[#09090b] border border-slate-800 text-sm text-slate-200 px-3 py-2 focus:outline-none focus:ring-1 focus:ring-slate-500 appearance-none"
                >
                  {repos.map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">Assign Role</label>
                <select
                  value={role}
                  onChange={e => setRole(e.target.value)}
                  aria-label="Assign role"
                  className="w-full rounded-md bg-[#09090b] border border-slate-800 text-sm text-slate-200 px-3 py-2 focus:outline-none focus:ring-1 focus:ring-slate-500 appearance-none capitalize"
                >
                  {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>

              {error && (
                <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-md px-3 py-2">
                  {error}
                </div>
              )}

              <Button type="submit" className="w-full bg-slate-100 text-slate-900 hover:bg-slate-200" disabled={loading}>
                Enter Dashboard
              </Button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
