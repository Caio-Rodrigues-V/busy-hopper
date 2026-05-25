import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { authAPI } from "../services/api";
import { ShieldAlert, ShieldCheck } from "lucide-react";

export default function Register() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleRegister = async (e) => {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await authAPI.register(email, password);
      setSuccess(true);
      setTimeout(() => {
        navigate("/login");
      }, 2000);
    } catch (err) {
      setError(err.response?.data?.detail || "Registration failed. Try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-dark-bg flex items-center justify-center p-4">
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-brand-accent/10 rounded-full blur-3xl pointer-events-none animate-pulse-slow"></div>

      <div className="w-full max-w-md glass-panel rounded-2xl p-8 relative overflow-hidden shadow-2xl">
        <div className="text-center mb-8 relative z-10">
          <div className="inline-flex p-3 bg-brand-accent/10 rounded-full text-brand-accent mb-3">
            <ShieldCheck size={32} />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-white">Create Account</h1>
          <p className="text-dark-muted text-sm mt-1">Register board details to establish a company</p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-brand-danger/10 border border-brand-danger/30 rounded-xl flex items-center gap-3 text-brand-danger text-sm relative z-10">
            <ShieldAlert size={20} className="shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="mb-6 p-4 bg-brand-secondary/10 border border-brand-secondary/30 rounded-xl flex items-center gap-3 text-brand-secondary text-sm relative z-10">
            <ShieldCheck size={20} className="shrink-0" />
            <span>Registration successful! Redirecting to login...</span>
          </div>
        )}

        <form onSubmit={handleRegister} className="space-y-5 relative z-10">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
              Email Address
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-dark-bg/60 border border-dark-border focus:border-brand-accent rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors"
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
              className="w-full bg-dark-bg/60 border border-dark-border focus:border-brand-accent rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors"
              placeholder="••••••••••••"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
              Confirm Password
            </label>
            <input
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full bg-dark-bg/60 border border-dark-border focus:border-brand-accent rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors"
              placeholder="••••••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={loading || success}
            className="w-full bg-brand-accent hover:bg-brand-accent/95 text-white font-semibold rounded-xl py-3 text-sm outline-none transition-colors shadow-lg shadow-brand-accent/20 flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {loading ? "Registering..." : "Create Board Account"}
          </button>
        </form>

        <div className="text-center mt-6 text-sm text-dark-muted relative z-10">
          <span>Already registered? </span>
          <Link to="/login" className="text-brand-accent hover:underline font-medium">
            Login here
          </Link>
        </div>
      </div>
    </div>
  );
}
