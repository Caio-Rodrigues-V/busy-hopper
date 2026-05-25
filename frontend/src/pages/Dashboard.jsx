import React, { useState, useEffect } from "react";
import { dashboardAPI } from "../services/api";
import { 
  DollarSign, 
  Percent, 
  Activity, 
  CheckCircle,
  TrendingUp,
  Gauge,
  Loader2,
  Heart,
  AlertTriangle
} from "lucide-react";
import { 
  LineChart, 
  Line, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  Legend, 
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell
} from "recharts";

export default function Dashboard() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchMetrics();
    // Poll metrics every 10 seconds for real-time cost transparency
    const timer = setInterval(fetchMetrics, 10000);
    return () => clearInterval(timer);
  }, []);

  const fetchMetrics = async () => {
    const companyId = localStorage.getItem("companyId");
    if (!companyId) {
      setLoading(false);
      return;
    }
    try {
      const res = await dashboardAPI.getMetrics();
      setMetrics(res.data);
      setError("");
    } catch (err) {
      console.error(err);
      setError("Failed to retrieve dashboard metrics.");
    } finally {
      setLoading(false);
    }
  };

  if (!localStorage.getItem("companyId")) {
    return (
      <div className="h-96 flex flex-col items-center justify-center gap-3 text-dark-muted p-6 border border-dashed border-dark-border rounded-2xl bg-dark-card/20">
        <Loader2 size={32} className="animate-spin text-brand-primary" />
        <span className="text-center font-medium">Waiting for enterprise selection or onboarding...</span>
        <p className="text-xs text-dark-muted text-center max-w-sm">
          Please select or establish a company in the sidebar to load the corporate analytics control plane.
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="h-96 flex flex-col items-center justify-center gap-3 text-dark-muted">
        <Loader2 size={32} className="animate-spin text-brand-primary" />
        <span>Aggregating ledger data...</span>
      </div>
    );
  }

  if (error || !metrics) {
    return (
      <div className="p-6 bg-brand-danger/10 border border-brand-danger/20 rounded-2xl text-brand-danger flex items-center gap-3">
        <AlertTriangle />
        <span>{error || "No metrics data available."}</span>
      </div>
    );
  }

  const { kpis, cost_over_time, agent_metrics } = metrics;

  // Colors for donut chart (strictly Orange and Black/Dark Gray)
  const PIE_COLORS = ["#FF5500", "#1D1D24"];

  // Helper for agent status badges
  const getStatusBadge = (status) => {
    switch (status) {
      case "active":
        return <span className="bg-brand-primary/15 text-brand-primary border border-brand-primary/20 px-2 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider">Active</span>;
      case "paused":
        return <span className="bg-brand-accent/15 text-brand-accent border border-brand-accent/20 px-2 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider">Paused</span>;
      case "exhausted":
        return <span className="bg-brand-danger/15 text-brand-danger border border-brand-danger/20 px-2 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider">Exhausted</span>;
      default:
        return <span className="bg-dark-muted/20 text-dark-muted px-2 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider">{status}</span>;
    }
  };

  // Helper for Health classifications (strictly Orange/Black spectrum)
  const getHealthBadge = (health) => {
    switch (health) {
      case "green":
        return <span className="flex items-center gap-1.5 text-brand-primary font-semibold text-sm"><Heart size={14} fill="#FF5500" stroke="#FF5500" /> Healthy</span>;
      case "yellow":
        return <span className="flex items-center gap-1.5 text-brand-accent font-semibold text-sm"><AlertTriangle size={14} fill="#FF9F40" stroke="#FF9F40" /> Warning</span>;
      case "red":
        return <span className="flex items-center gap-1.5 text-brand-danger font-semibold text-sm"><AlertTriangle size={14} fill="#FF3300" stroke="#FF3300" /> Critical</span>;
      default:
        return <span>{health}</span>;
    }
  };

  return (
    <div className="space-y-8">
      {/* Overview stats header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Corporate Health & Analytics</h1>
        <p className="text-dark-muted text-sm max-w-3xl">
          Real-time metrics auditing active agent tasks, cumulative execution expenditures, markup invoicing comparisons, and API limits.
        </p>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-5">
        {/* Real Cost Card */}
        <div className="glass-card rounded-2xl p-6 relative overflow-hidden">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-semibold text-dark-muted uppercase tracking-wider">Gastos da API (Custo Real)</span>
            <div className="p-2 bg-brand-primary/10 rounded-lg text-brand-primary">
              <DollarSign size={18} />
            </div>
          </div>
          <div className="text-2xl font-bold text-white">${kpis.monthly_cost.toFixed(2)}</div>
          <p className="text-[10px] text-dark-muted mt-2">Custo real consumido da API Anthropic</p>
        </div>

        {/* Markup Cost Card */}
        <div className="glass-card rounded-2xl p-6 relative overflow-hidden">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-semibold text-dark-muted uppercase tracking-wider">Faturamento (Com Markup)</span>
            <div className="p-2 bg-brand-accent/10 rounded-lg text-brand-accent">
              <TrendingUp size={18} />
            </div>
          </div>
          <div className="text-2xl font-bold text-white">${kpis.markup_cost.toFixed(2)}</div>
          <p className="text-[10px] text-dark-muted mt-2">Preço final com margem de {metrics.markup_pct}%</p>
        </div>

        {/* Budget Card */}
        <div className="glass-card rounded-2xl p-6 relative overflow-hidden">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-semibold text-dark-muted uppercase tracking-wider">Budget Spent</span>
            <div className="p-2 bg-brand-primary/10 rounded-lg text-brand-primary">
              <Percent size={18} />
            </div>
          </div>
          <div className="text-2xl font-bold text-white">{kpis.budget_pct}%</div>
          <div className="w-full bg-dark-border h-1.5 rounded-full mt-2 overflow-hidden">
            <div 
              className={`h-full rounded-full ${kpis.budget_pct > 90 ? 'bg-brand-danger' : kpis.budget_pct > 60 ? 'bg-brand-accent' : 'bg-brand-primary'}`}
              style={{ width: `${Math.min(kpis.budget_pct, 100)}%` }}
            />
          </div>
          <p className="text-[10px] text-dark-muted mt-2">Limit: ${metrics.monthly_budget} / month</p>
        </div>

        {/* Runs Today Card */}
        <div className="glass-card rounded-2xl p-6 relative overflow-hidden">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-semibold text-dark-muted uppercase tracking-wider">Runs Today</span>
            <div className="p-2 bg-brand-accent/10 rounded-lg text-brand-accent">
              <Activity size={18} />
            </div>
          </div>
          <div className="text-2xl font-bold text-white">{kpis.runs_today}</div>
          <p className="text-[10px] text-dark-muted mt-2">Active loops in past 24 hours</p>
        </div>

        {/* Success Rate Card */}
        <div className="glass-card rounded-2xl p-6 relative overflow-hidden">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-semibold text-dark-muted uppercase tracking-wider">Success Rate</span>
            <div className="p-2 bg-brand-secondary/10 rounded-lg text-brand-secondary">
              <CheckCircle size={18} />
            </div>
          </div>
          <div className="text-2xl font-bold text-white">{kpis.success_rate}%</div>
          <p className="text-[10px] text-dark-muted mt-2">Percentage of successful task runs</p>
        </div>
      </div>

      {/* Main Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Cost Over Time (Line Chart) */}
        <div className="glass-panel rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider mb-6">Evolução dos Gastos da API (USD)</h3>
          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={cost_over_time}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1D1D24" />
                <XAxis dataKey="date" stroke="#9CA3AF" tick={{ fontSize: 10 }} />
                <YAxis stroke="#9CA3AF" tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ backgroundColor: "#0E0E12", borderColor: "#1D1D24" }} />
                <Legend />
                <Line type="monotone" dataKey="cost" name="Custo Real API" stroke="#FF5500" strokeWidth={2} activeDot={{ r: 6 }} />
                <Line type="monotone" dataKey="markup_cost" name="Preço Final (Markup)" stroke="#FF9F40" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Agent Cost/Tokens (Bar Chart) */}
        <div className="glass-panel rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider mb-6">Gastos por IA (Detalhamento por Agente)</h3>
          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={agent_metrics}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1D1D24" />
                <XAxis dataKey="name" stroke="#9CA3AF" tick={{ fontSize: 10 }} />
                <YAxis stroke="#9CA3AF" tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ backgroundColor: "#0E0E12", borderColor: "#1D1D24" }} />
                <Legend />
                <Bar dataKey="cost" name="Custo Real API ($)" fill="#FF5500" radius={[4, 4, 0, 0]} />
                <Bar dataKey="markup_cost" name="Preço com Markup ($)" fill="#FF7A00" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Latency averages (Bar Chart) */}
        <div className="glass-panel rounded-2xl p-6">
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider mb-6">Average Model Response Latency (ms)</h3>
          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={agent_metrics}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1D1D24" />
                <XAxis dataKey="name" stroke="#9CA3AF" tick={{ fontSize: 10 }} />
                <YAxis stroke="#9CA3AF" tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ backgroundColor: "#0E0E12", borderColor: "#1D1D24" }} />
                <Bar dataKey="latency" name="Latency (ms)" fill="#FF9F40" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Success / Failure Donut representation */}
        <div className="glass-panel rounded-2xl p-6 flex flex-col justify-between">
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider mb-4">Cumulative Task Outcomes</h3>
          <div className="flex-1 flex items-center justify-center">
            <div className="h-60 w-60">
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie
                    data={[
                      { name: "Success Runs", value: agent_metrics.reduce((acc, curr) => acc + curr.success, 0) },
                      { name: "Failed Runs", value: agent_metrics.reduce((acc, curr) => acc + curr.failed, 0) }
                    ]}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    <Cell fill="#FF5500" />
                    <Cell fill="#1D1D24" />
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: "#0E0E12", borderColor: "#1D1D24" }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="space-y-2 text-sm text-dark-muted font-medium ml-4">
              <div className="flex items-center gap-2">
                <div className="w-3.5 h-3.5 bg-brand-primary rounded-full" />
                <span>Success: {agent_metrics.reduce((acc, curr) => acc + curr.success, 0)} runs</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3.5 h-3.5 bg-dark-border rounded-full" />
                <span>Failed: {agent_metrics.reduce((acc, curr) => acc + curr.failed, 0)} runs</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Agent Health Grid Table */}
      <div className="glass-panel rounded-2xl p-6">
        <h3 className="text-sm font-semibold text-white uppercase tracking-wider mb-6 flex items-center gap-2">
          <Gauge className="text-brand-primary" />
          <span>Status e Saúde Operacional dos Agentes</span>
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-sm">
            <thead>
              <tr className="border-b border-dark-border text-xs text-dark-muted font-semibold uppercase tracking-wider">
                <th className="pb-3">Agente</th>
                <th className="pb-3">Cargo</th>
                <th className="pb-3">Saúde</th>
                <th className="pb-3">Estado</th>
                <th className="pb-3 text-right">Gastos no Mês (API)</th>
                <th className="pb-3 text-right">Limite de Orçamento</th>
                <th className="pb-3 text-right">Latência Média</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-dark-border/40 text-dark-text">
              {agent_metrics.map((agent) => (
                <tr key={agent.agent_id} className="hover:bg-dark-border/10 transition-colors">
                  <td className="py-4 font-semibold text-white">{agent.name}</td>
                  <td className="py-4 text-dark-muted">{agent.title}</td>
                  <td className="py-4">{getHealthBadge(agent.health)}</td>
                  <td className="py-4">{getStatusBadge(agent.status)}</td>
                  <td className="py-4 text-right font-medium text-white">${agent.cost.toFixed(2)}</td>
                  <td className="py-4 text-right text-dark-muted">${agent.monthly_budget.toFixed(2)}</td>
                  <td className="py-4 text-right font-medium text-white">{agent.latency.toFixed(0)}ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
