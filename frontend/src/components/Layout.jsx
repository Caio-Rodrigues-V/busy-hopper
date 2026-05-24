import React, { useState, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { companyAPI } from "../services/api";
import { 
  LayoutDashboard, 
  Network, 
  KanbanSquare, 
  CheckSquare, 
  Settings, 
  Building2, 
  LogOut, 
  Plus,
  Loader2,
  Megaphone
} from "lucide-react";

export default function Layout({ children }) {
  const [companies, setCompanies] = useState([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState("");
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newCompanyName, setNewCompanyName] = useState("");
  const [newCompanyMission, setNewCompanyMission] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    fetchCompanies();
  }, []);

  const fetchCompanies = async () => {
    try {
      const res = await companyAPI.list();
      setCompanies(res.data);
      if (res.data.length > 0) {
        const storedId = localStorage.getItem("companyId");
        const found = res.data.find(c => c.id.toString() === storedId);
        const defaultId = found ? found.id.toString() : res.data[0].id.toString();
        
        setSelectedCompanyId(defaultId);
        localStorage.setItem("companyId", defaultId);
        if (!storedId) {
          window.location.reload();
        }
      } else {
        // Trigger create company onboarding
        setShowCreateModal(true);
      }
    } catch (err) {
      console.error("Failed to load companies list:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCompanyChange = (e) => {
    const val = e.target.value;
    setSelectedCompanyId(val);
    localStorage.setItem("companyId", val);
    // Reload state on dashboard
    window.location.reload();
  };

  const handleCreateCompany = async (e) => {
    e.preventDefault();
    if (!newCompanyName || !newCompanyMission) return;
    setSubmitting(true);
    try {
      const res = await companyAPI.create(newCompanyName, newCompanyMission);
      const newId = res.data.id.toString();
      localStorage.setItem("companyId", newId);
      setSelectedCompanyId(newId);
      setCompanies([...companies, res.data]);
      setShowCreateModal(false);
      setNewCompanyName("");
      setNewCompanyMission("");
      window.location.reload();
    } catch (err) {
      console.error("Failed to create company:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("companyId");
    navigate("/login");
  };

  const menuItems = [
    { name: "Dashboard", path: "/", icon: LayoutDashboard },
    { name: "Org Chart", path: "/org", icon: Network },
    { name: "Task Board", path: "/tasks", icon: KanbanSquare },
    { name: "Approvals", path: "/approvals", icon: CheckSquare },
    { name: "Meta Ads", path: "/meta", icon: Megaphone },
    { name: "Settings", path: "/settings", icon: Settings },
  ];

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-bg flex flex-col items-center justify-center text-white gap-3">
        <Loader2 size={36} className="animate-spin text-brand-primary" />
        <span className="text-sm text-dark-muted font-medium">Booting Board Interface...</span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-dark-bg text-dark-text flex">
      {/* Sidebar */}
      <aside className="w-64 bg-dark-card border-r border-dark-border flex flex-col justify-between shrink-0">
        <div>
          {/* Logo */}
          <div className="h-16 border-b border-dark-border px-6 flex items-center gap-3">
            <div className="w-8 h-8 bg-brand-primary/15 rounded-lg border border-brand-primary/40 flex items-center justify-center text-brand-primary font-bold">
              A
            </div>
            <span className="font-bold text-white text-lg tracking-tight">Antigravity</span>
          </div>

          {/* Company Selector */}
          <div className="p-4 border-b border-dark-border">
            <label className="block text-[10px] font-bold uppercase tracking-wider text-dark-muted mb-2">
              Active Enterprise
            </label>
            <div className="flex gap-2">
              <select
                value={selectedCompanyId}
                onChange={handleCompanyChange}
                className="w-full bg-dark-bg border border-dark-border rounded-xl px-3 py-2 text-sm text-white outline-none focus:border-brand-primary"
              >
                {companies.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              <button 
                onClick={() => setShowCreateModal(true)}
                className="bg-brand-primary/10 hover:bg-brand-primary/20 text-brand-primary border border-brand-primary/30 p-2.5 rounded-xl transition-colors"
                title="Create Company"
              >
                <Plus size={16} />
              </button>
            </div>
          </div>

          {/* Nav Menu */}
          <nav className="p-4 space-y-1">
            {menuItems.map(item => {
              const Icon = item.icon;
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-colors ${
                    isActive 
                      ? "bg-brand-primary/10 text-brand-primary border border-brand-primary/20" 
                      : "text-dark-muted hover:text-white hover:bg-dark-border/35"
                  }`}
                >
                  <Icon size={18} />
                  <span>{item.name}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Footer info & logout */}
        <div className="p-4 border-t border-dark-border">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-brand-danger hover:bg-brand-danger/10 transition-colors border border-transparent hover:border-brand-danger/20"
          >
            <LogOut size={18} />
            <span>Logout session</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="h-16 border-b border-dark-border px-8 flex items-center justify-between bg-dark-card/50 backdrop-blur-md sticky top-0 z-20">
          <div className="flex items-center gap-2 text-xs text-dark-muted font-medium">
            <Building2 size={14} />
            <span>Control Plane</span>
            <span>/</span>
            <span className="text-white font-semibold">
              {companies.find(c => c.id.toString() === selectedCompanyId)?.name || "New Company"}
            </span>
          </div>
          <div className="text-xs text-dark-muted bg-dark-bg border border-dark-border px-3 py-1.5 rounded-lg">
            Status: <span className="text-brand-secondary font-bold">Online</span>
          </div>
        </header>

        {/* Main View Grid */}
        <main className="flex-1 p-8 overflow-y-auto">
          {children}
        </main>
      </div>

      {/* Company Creation Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-lg glass-panel rounded-2xl p-8 relative shadow-2xl">
            <h2 className="text-2xl font-bold text-white mb-2 flex items-center gap-3">
              <Building2 className="text-brand-primary" />
              <span>Launch Enterprise</span>
            </h2>
            <p className="text-dark-muted text-sm mb-6">Create a new company tenancy and define its primary business goals.</p>
            
            <form onSubmit={handleCreateCompany} className="space-y-5">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Company Name
                </label>
                <input
                  type="text"
                  required
                  value={newCompanyName}
                  onChange={(e) => setNewCompanyName(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors"
                  placeholder="e.g. Acme Tech Solutions"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Mission / Goal Statement
                </label>
                <textarea
                  required
                  rows={4}
                  value={newCompanyMission}
                  onChange={(e) => setNewCompanyMission(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors resize-none"
                  placeholder="e.g. Develop and maintain high-quality backend APIs in Python, ensuring 99.9% uptime and comprehensive documentation."
                />
              </div>

              <div className="flex gap-3 justify-end pt-3">
                {companies.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    className="border border-dark-border hover:bg-dark-border/20 text-white font-semibold rounded-xl px-6 py-2.5 text-sm transition-colors"
                  >
                    Cancel
                  </button>
                )}
                <button
                  type="submit"
                  disabled={submitting}
                  className="bg-brand-primary hover:bg-brand-primary/90 text-white font-semibold rounded-xl px-6 py-2.5 text-sm transition-colors shadow-lg shadow-brand-primary/20 flex items-center gap-2"
                >
                  {submitting && <Loader2 size={16} className="animate-spin" />}
                  <span>Establish Enterprise</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
