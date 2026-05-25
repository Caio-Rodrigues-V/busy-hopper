import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { authAPI } from "../services/api";
import { ShieldAlert, ShieldCheck } from "lucide-react";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await authAPI.login(email, password);
      localStorage.setItem("token", res.data.access_token);
      
      // Auto redirect to dashboard
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.detail || "Authentication failed. Check your credentials.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-dark-bg flex items-center justify-center p-4">
      {/* Background ambient light */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-brand-primary/10 rounded-full blur-3xl pointer-events-none animate-pulse-slow"></div>

      <div className="w-full max-w-md glass-panel rounded-2xl p-8 relative overflow-hidden shadow-2xl">
        <div className="text-center mb-8 relative z-10">
          <div className="inline-flex p-3 bg-brand-primary/10 rounded-full text-brand-primary mb-3">
            <ShieldCheck size={32} className="animate-pulse" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-white">Antigravity</h1>
          <p className="text-dark-muted text-sm mt-1">Autonomous AI Agent Orchestrator Control Plane</p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-brand-danger/10 border border-brand-danger/30 rounded-xl flex items-center gap-3 text-brand-danger text-sm relative z-10">
            <ShieldAlert size={20} className="shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleLogin} className="space-y-5 relative z-10">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
              Email Address
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-dark-bg/60 border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors"
              placeholder="name@autonomous.corp"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-dark-bg/60 border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors"
              placeholder="••••••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-brand-primary hover:bg-brand-primary/95 text-white font-semibold rounded-xl py-3 text-sm outline-none transition-colors shadow-lg shadow-brand-primary/20 flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {loading ? "Establishing session..." : "Login to Control Plane"}
          </button>
        </form>

        <div className="text-center mt-6 text-sm text-dark-muted relative z-10">
          <span>New company? </span>
          <Link to="/register" className="text-brand-primary hover:underline font-medium">
            Register Board Account
          </Link>
        </div>
      </div>
    </div>
  );
}
