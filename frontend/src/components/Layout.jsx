import { useState, useEffect } from "react";
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
  Megaphone,
  X,
  Menu
} from "lucide-react";

export default function Layout({ children }) {
  const [companies, setCompanies] = useState([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState("");
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newCompanyName, setNewCompanyName] = useState("");
  const [newCompanyMission, setNewCompanyMission] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();

  async function fetchCompanies() {
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
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchCompanies();
  }, []);

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
    { name: "Painel Geral", path: "/", icon: LayoutDashboard },
    { name: "Organograma", path: "/org", icon: Network },
    { name: "Fila de Tarefas", path: "/tasks", icon: KanbanSquare },
    { name: "Aprovações", path: "/approvals", icon: CheckSquare },
    { name: "Gestor de Tráfego", path: "/meta", icon: Megaphone },
    { name: "Configurações", path: "/settings", icon: Settings },
  ];

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-bg flex flex-col items-center justify-center text-white gap-3">
        <Loader2 size={36} className="animate-spin text-brand-primary" />
        <span className="text-sm text-dark-muted font-medium">Iniciando a Interface...</span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-dark-bg text-dark-text flex relative overflow-hidden">
      {/* Ambient Glows */}
      <div className="glow-spot w-[500px] h-[500px] bg-brand-primary/5 top-[-150px] right-[-150px] animate-pulse-slow"></div>
      <div className="glow-spot w-[600px] h-[600px] bg-brand-primary/5 -bottom-[200px] -left-[200px] animate-pulse-slow" style={{ animationDelay: '2s' }}></div>

      {/* Backdrop for Mobile Menu */}
      {isMobileMenuOpen && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-xs z-40 lg:hidden transition-opacity duration-300"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`fixed inset-y-0 left-0 w-64 bg-dark-card/95 lg:bg-dark-card/65 backdrop-blur-md border-r border-dark-border/40 flex flex-col justify-between shrink-0 z-50 transform lg:translate-x-0 lg:static transition-transform duration-300 ${
        isMobileMenuOpen ? "translate-x-0" : "-translate-x-full"
      }`}>
        <div>
          {/* Logo */}
          <div className="h-16 border-b border-dark-border/40 px-6 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-brand-primary/15 rounded-lg border border-brand-primary/40 flex items-center justify-center text-brand-primary font-bold shadow-lg shadow-brand-primary/10">
                A
              </div>
              <span className="font-bold text-white text-lg tracking-tight">Antigravity</span>
            </div>
            {/* Close Mobile Sidebar button */}
            <button 
              className="lg:hidden text-dark-muted hover:text-white p-1"
              onClick={() => setIsMobileMenuOpen(false)}
            >
              <X size={20} />
            </button>
          </div>

          {/* Company Selector */}
          <div className="p-4 border-b border-dark-border/40">
            <label className="block text-[10px] font-bold uppercase tracking-wider text-dark-muted mb-2">
              Empresa Ativa
            </label>
            <div className="flex gap-2">
              <select
                value={selectedCompanyId}
                onChange={handleCompanyChange}
                className="w-full bg-dark-bg border border-dark-border/60 rounded-xl px-3 py-2 text-sm text-white outline-none focus:border-brand-primary transition-colors"
              >
                {companies.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              <button 
                onClick={() => setShowCreateModal(true)}
                className="bg-brand-primary/10 hover:bg-brand-primary/20 text-brand-primary border border-brand-primary/30 p-2.5 rounded-xl transition-all shadow-md hover:shadow-brand-primary/5"
                title="Criar Empresa"
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
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-350 ${
                    isActive 
                      ? "bg-brand-primary/15 text-brand-primary border border-brand-primary/30 glow-orange" 
                      : "text-dark-muted hover:text-white hover:bg-dark-border/30 border border-transparent"
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
        <div className="p-4 border-t border-dark-border/40">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-brand-danger hover:bg-brand-danger/10 transition-colors border border-transparent hover:border-brand-danger/20"
          >
            <LogOut size={18} />
            <span>Sair da sessão</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 relative z-10 overflow-hidden">
        {/* Header */}
        <header className="h-16 border-b border-dark-border/40 px-4 sm:px-8 flex items-center justify-between bg-dark-card/40 backdrop-blur-md sticky top-0 z-20">
          <div className="flex items-center gap-3 min-w-0">
            {/* Hamburger menu for mobile */}
            <button 
              className="lg:hidden text-dark-muted hover:text-white p-1 hover:bg-dark-border/30 rounded-lg transition-colors"
              onClick={() => setIsMobileMenuOpen(true)}
              title="Abrir Menu"
            >
              <Menu size={20} />
            </button>
            <div className="flex items-center gap-2 text-xs text-dark-muted font-medium truncate">
              <Building2 size={14} className="shrink-0" />
              <span className="hidden sm:inline">Painel de Controle</span>
              <span className="hidden sm:inline">/</span>
              <span className="text-white font-semibold truncate">
                {companies.find(c => c.id.toString() === selectedCompanyId)?.name || "Nova Empresa"}
              </span>
            </div>
          </div>
          <div className="text-xs text-dark-muted bg-dark-bg border border-dark-border/60 px-3 py-1.5 rounded-lg flex items-center gap-2 shrink-0">
            <span className="w-1.5 h-1.5 bg-brand-primary rounded-full animate-pulse-dot"></span>
            Status: <span className="text-brand-secondary font-semibold">Online</span>
          </div>
        </header>

        {/* Main View Grid */}
        <main className="flex-1 p-4 sm:p-8 overflow-y-auto">
          {children}
        </main>
      </div>

      {/* Company Creation Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-lg glass-panel rounded-2xl p-6 sm:p-8 relative shadow-2xl">
            {/* Close Button */}
            <button
              onClick={() => setShowCreateModal(false)}
              className="absolute top-4 right-4 text-dark-muted hover:text-white transition-colors"
              title="Fechar"
            >
              <X size={20} />
            </button>

            <h2 className="text-xl sm:text-2xl font-bold text-white mb-2 flex items-center gap-3">
              <Building2 className="text-brand-primary" />
              <span>Criar Nova Empresa</span>
            </h2>
            <p className="text-dark-muted text-sm mb-6">Crie uma nova empresa e defina seus objetivos de negócio principais.</p>
            
            <form onSubmit={handleCreateCompany} className="space-y-5">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Nome da Empresa
                </label>
                <input
                  type="text"
                  required
                  value={newCompanyName}
                  onChange={(e) => setNewCompanyName(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors"
                  placeholder="ex: Soluções de Tecnologia Acme"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Missão / Declaração de Objetivos
                </label>
                <textarea
                  required
                  rows={4}
                  value={newCompanyMission}
                  onChange={(e) => setNewCompanyMission(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors resize-none"
                  placeholder="ex: Desenvolver e manter APIs de backend de alta qualidade em Python, garantindo 99.9% de uptime e documentação completa."
                />
              </div>

              <div className="flex gap-3 justify-end pt-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="border border-dark-border hover:bg-dark-border/20 text-white font-semibold rounded-xl px-6 py-2.5 text-sm transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="bg-brand-primary hover:bg-brand-primary/90 text-white font-semibold rounded-xl px-6 py-2.5 text-sm transition-colors shadow-lg shadow-brand-primary/20 flex items-center gap-2"
                >
                  {submitting && <Loader2 size={16} className="animate-spin" />}
                  <span>Estabelecer Empresa</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
