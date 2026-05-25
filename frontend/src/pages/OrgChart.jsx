import { useState, useEffect, useRef } from "react";
import { agentAPI } from "../services/api";
import { 
  Network, 
  User, 
  ArrowDown, 
  Plus,
  Loader2,
  AlertTriangle,
  Trash2,
  Layers,
  FileText,
  FileCode,
  FileImage,
  Download,
  Eye
} from "lucide-react";

export default function OrgChart() {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [openClawText, setOpenClawText] = useState("");
  const [importBossId, setImportBossId] = useState("");
  const [importing, setImporting] = useState(false);

  // Form states for adding a new agent
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [rolePrompt, setRolePrompt] = useState("");
  const [bossAgentId, setBossAgentId] = useState("");
  const [adapterType] = useState("claude");
  const [model, setModel] = useState("claude-3-5-sonnet-20241022");
  const [customModel, setCustomModel] = useState("");
  const [temperature] = useState(0.0);
  const [monthlyBudget, setMonthlyBudget] = useState(50.0);
  const [selectedTools, setSelectedTools] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  // Inspected agent details modal states
  const [inspectedAgent, setInspectedAgent] = useState(null);
  const [artifacts, setArtifacts] = useState([]);
  const [loadingArtifacts, setLoadingArtifacts] = useState(false);
  const [activeAgentTab, setActiveAgentTab] = useState("prompts"); // "prompts" | "artifacts"
  const [selectedArtifact, setSelectedArtifact] = useState(null);
  const [selectedArtifactContent, setSelectedArtifactContent] = useState("");
  const [selectedArtifactBlobUrl, setSelectedArtifactBlobUrl] = useState("");
  const [loadingArtifactContent, setLoadingArtifactContent] = useState(false);

  const fetchAgentArtifacts = async (agentId) => {
    setLoadingArtifacts(true);
    try {
      const res = await agentAPI.getArtifacts(agentId);
      setArtifacts(res.data);
    } catch (err) {
      console.error("Failed to load agent artifacts:", err);
    } finally {
      setLoadingArtifacts(false);
    }
  };

  useEffect(() => {
    if (inspectedAgent) {
      fetchAgentArtifacts(inspectedAgent.id);
      setSelectedArtifact(null);
      setSelectedArtifactContent("");
      if (selectedArtifactBlobUrl) {
        URL.revokeObjectURL(selectedArtifactBlobUrl);
        setSelectedArtifactBlobUrl("");
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inspectedAgent]);

  useEffect(() => {
    return () => {
      if (selectedArtifactBlobUrl) {
        URL.revokeObjectURL(selectedArtifactBlobUrl);
      }
    };
  }, [selectedArtifactBlobUrl]);

  const handleSelectArtifact = async (artifact) => {
    setSelectedArtifact(artifact);
    setLoadingArtifactContent(true);
    setSelectedArtifactContent("");
    if (selectedArtifactBlobUrl) {
      URL.revokeObjectURL(selectedArtifactBlobUrl);
      setSelectedArtifactBlobUrl("");
    }
    
    try {
      if (artifact.type === "image") {
        const res = await agentAPI.getArtifactContent(inspectedAgent.id, artifact.filename, "blob");
        const blob = new Blob([res.data], { type: "image/svg+xml" });
        const url = URL.createObjectURL(blob);
        setSelectedArtifactBlobUrl(url);
      } else {
        const res = await agentAPI.getArtifactContent(inspectedAgent.id, artifact.filename, "text");
        if (typeof res.data === "object") {
          setSelectedArtifactContent(JSON.stringify(res.data, null, 2));
        } else {
          setSelectedArtifactContent(res.data);
        }
      }
    } catch (err) {
      console.error("Failed to load artifact content:", err);
      setSelectedArtifactContent("Error loading file content.");
    } finally {
      setLoadingArtifactContent(false);
    }
  };

  const handleDownloadArtifact = async (artifact) => {
    try {
      const res = await agentAPI.getArtifactContent(inspectedAgent.id, artifact.filename, "blob");
      const blob = new Blob([res.data], { type: res.headers["content-type"] || "application/octet-stream" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", artifact.filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Failed to download artifact:", err);
      alert("Failed to download file.");
    }
  };

  const socketRef = useRef(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    fetchAgents();
    connectWebSocket();

    return () => {
      isMountedRef.current = false;
      if (socketRef.current) {
        socketRef.current.onclose = null;
        socketRef.current.close();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connectWebSocket = () => {
    const companyId = localStorage.getItem("companyId");
    if (!companyId || !isMountedRef.current) return;

    const token = localStorage.getItem("token");
    const rawBackendUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
    const backendUrl = (rawBackendUrl.startsWith("http://") && !rawBackendUrl.includes("localhost") && !rawBackendUrl.includes("127.0.0.1"))
      ? rawBackendUrl.replace("http://", "https://")
      : rawBackendUrl;
    const wsProtocol = backendUrl.startsWith("https") ? "wss" : "ws";
    const wsHost = backendUrl.replace(/^https?:\/\//, "").replace(/\/$/, "");
    const wsUrl = `${wsProtocol}://${wsHost}/api/v1/ws/${companyId}${token ? `?token=${encodeURIComponent(token)}` : ""}`;
    
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onmessage = (event) => {
      if (!isMountedRef.current) return;
      try {
        const data = JSON.parse(event.data);
        if (data.type === "org_updated") {
          fetchAgents();
        }
      } catch (err) {
        console.error("Failed to parse WebSocket message in OrgChart:", err);
      }
    };

    ws.onclose = () => {
      if (!isMountedRef.current) return;
      setTimeout(() => {
        if (isMountedRef.current) connectWebSocket();
      }, 5000);
    };
  };

  const fetchAgents = async () => {
    try {
      const res = await agentAPI.list();
      setAgents(res.data);
    } catch (err) {
      console.error(err);
      setError("Failed to load organization chart.");
    } finally {
      setLoading(false);
    }
  };

  const handleImportOpenClaw = async (e) => {
    e.preventDefault();
    if (!openClawText.trim()) {
      alert("Please paste the OpenClaw configuration JSON.");
      return;
    }

    setImporting(true);
    try {
      // Strip comments
      let cleanJsonText = openClawText
        .replace(/\/\*[\s\S]*?\*\/|([^\\:]|^)\/\/.*$/gm, '$1')
        .trim();
      
      const configObj = JSON.parse(cleanJsonText);
      const res = await agentAPI.importOpenClaw({
        openclaw_config: configObj,
        boss_agent_id: importBossId || null
      });

      alert(`Agent '${res.data.name}' imported successfully!`);
      setShowImportModal(false);
      setOpenClawText("");
      setImportBossId("");
      fetchAgents();
    } catch (err) {
      console.error(err);
      alert("Failed to parse or import OpenClaw agent configuration. Ensure it is valid JSON.");
    } finally {
      setImporting(false);
    }
  };

  const handleToolToggle = (toolName) => {
    if (selectedTools.includes(toolName)) {
      setSelectedTools(selectedTools.filter(t => t !== toolName));
    } else {
      setSelectedTools([...selectedTools, toolName]);
    }
  };

  const handleCreateAgent = async (e) => {
    e.preventDefault();
    if (!name || !title || !rolePrompt) return;
    setSubmitting(true);
    try {
      const payload = {
        name,
        title,
        role_prompt: rolePrompt,
        boss_agent_id: bossAgentId ? parseInt(bossAgentId) : null,
        adapter_type: adapterType,
        model: model === "custom_input" ? customModel : model,
        temperature: parseFloat(temperature),
        monthly_budget_usd: parseFloat(monthlyBudget),
        tools: selectedTools,
        status: "active"
      };
      const res = await agentAPI.create(payload);
      setAgents([...agents, res.data]);
      setShowCreateModal(false);
      // Reset form
      setName("");
      setTitle("");
      setRolePrompt("");
      setBossAgentId("");
      setCustomModel("");
      setMonthlyBudget(50.0);
      setSelectedTools([]);
    } catch (err) {
      console.error(err);
      alert(err.response?.data?.detail || "Failed to create agent.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteAgent = async (id) => {
    if (!confirm("Are you sure you want to fire this agent? Any subordinates reporting to them will report directly to the CEO/None.")) return;
    try {
      await agentAPI.delete(id);
      setAgents(prev => prev.filter(a => a.id !== id));
    } catch (err) {
      console.error(err);
      alert("Failed to terminate agent.");
    }
  };

  // Find root agents (agents without a boss)
  const rootAgents = agents.filter(a => !a.boss_agent_id);

  // Recursive component to render tree nodes
  const OrgTreeNode = ({ agent }) => {
    const subordinates = agents.filter(a => a.boss_agent_id === agent.id);
    
    return (
      <div className="flex flex-col items-center">
        {/* Agent Card */}
        <div className="glass-card rounded-2xl p-5 w-80 text-left border border-dark-border/60 relative">
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-brand-primary/10 border border-brand-primary/30 rounded-xl flex items-center justify-center text-brand-primary shadow-inner">
                <User size={20} />
              </div>
              <div>
                <h4 className="font-bold text-white text-base tracking-tight">{agent.name}</h4>
                <p className="text-xs text-dark-muted font-medium">{agent.title}</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider flex items-center gap-1 ${
                agent.status === 'active' ? 'bg-brand-primary/15 text-brand-primary border border-brand-primary/20' : 'bg-brand-danger/15 text-brand-danger border border-brand-danger/20'
              }`}>
                {agent.status === 'active' && <span className="w-1 h-1 bg-brand-primary rounded-full animate-pulse-dot" />}
                {agent.status}
              </span>
              <button
                onClick={() => setInspectedAgent(agent)}
                className="text-brand-primary hover:bg-brand-primary/10 p-1.5 rounded-lg transition-all border border-transparent hover:border-brand-primary/25"
                title="Inspect Agent Work"
              >
                <Layers size={13} />
              </button>
              <button
                onClick={() => handleDeleteAgent(agent.id)}
                className="text-brand-danger hover:bg-brand-danger/10 p-1.5 rounded-lg transition-all border border-transparent hover:border-brand-danger/25"
                title="Fire Agent"
              >
                <Trash2 size={13} />
              </button>
            </div>
          </div>

          <div className="space-y-2 border-t border-dark-border/40 pt-3 text-xs text-dark-muted">
            <div className="flex justify-between">
              <span>Model:</span>
              <span className="font-mono text-white text-[11px] bg-dark-bg px-2 py-0.5 rounded border border-dark-border/60">{agent.model}</span>
            </div>
            <div className="flex justify-between">
              <span>Monthly Budget:</span>
              <span className="font-semibold text-white">${agent.monthly_budget_usd.toFixed(2)}</span>
            </div>
            <div>
              <span className="block mb-1.5 font-semibold text-white/80">Permissions / Tools:</span>
              <div className="flex flex-wrap gap-1">
                {agent.tools.length > 0 ? (
                  agent.tools.map(tool => (
                    <span key={tool} className="bg-dark-border/30 border border-dark-border/60 px-1.5 py-0.5 rounded text-[9px] text-white font-mono">
                      {tool}
                    </span>
                  ))
                ) : (
                  <span className="text-[10px] italic">No tools assigned</span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Connector lines and subordinates */}
        {subordinates.length > 0 && (
          <div className="flex flex-col items-center mt-6 w-full">
            {/* Downward line with premium glow gradient */}
            <div className="w-[2px] h-8 org-line mb-4 relative flex items-center justify-center">
              <ArrowDown size={14} className="text-brand-primary shrink-0 translate-y-2.5 drop-shadow-[0_0_5px_rgba(255,85,0,0.5)]" />
            </div>
            
            {/* Children grid */}
            <div className="flex flex-wrap justify-center gap-12 relative">
              {subordinates.map(sub => (
                <OrgTreeNode key={sub.id} agent={sub} />
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="h-96 flex flex-col items-center justify-center gap-3 text-dark-muted">
        <Loader2 size={32} className="animate-spin text-brand-primary" />
        <span>Charting organization lines...</span>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Corporate Hierarchy Chart</h1>
          <p className="text-dark-muted text-sm">
            Visual tree mapping reporting structure, individual agent prompts, temperatures, cost caps, and granular system tools.
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowImportModal(true)}
            className="bg-dark-bg/60 border border-dark-border hover:border-brand-primary text-white font-semibold rounded-xl px-5 py-3 text-sm transition-all flex items-center gap-2"
          >
            <span>Import OpenClaw</span>
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="bg-brand-primary hover:bg-brand-primary/95 text-white font-semibold rounded-xl px-5 py-3 text-sm transition-colors shadow-lg shadow-brand-primary/20 flex items-center gap-2"
          >
            <Plus size={16} />
            <span>Hire New Agent</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-6 bg-brand-danger/10 border border-brand-danger/20 rounded-2xl text-brand-danger flex items-center gap-3">
          <AlertTriangle />
          <span>{error}</span>
        </div>
      )}

      {/* Org Chart Tree Container */}
      <div className="glass-panel rounded-2xl p-8 overflow-x-auto min-h-[500px] flex justify-center items-start">
        {rootAgents.length > 0 ? (
          <div className="flex flex-wrap justify-center gap-16 w-full">
            {rootAgents.map(agent => (
              <OrgTreeNode key={agent.id} agent={agent} />
            ))}
          </div>
        ) : (
          <div className="text-center py-20 text-dark-muted max-w-sm">
            <Network size={48} className="mx-auto mb-4 text-dark-border" />
            <h3 className="font-bold text-white text-lg">Empty Org Chart</h3>
            <p className="text-sm mt-1">Hire your first agent to kick off operations.</p>
          </div>
        )}
      </div>

      {/* Hire Agent Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="w-full max-w-2xl glass-panel rounded-2xl p-8 relative shadow-2xl my-8">
            <h2 className="text-2xl font-bold text-white mb-2 flex items-center gap-3">
              <Plus className="text-brand-primary" />
              <span>Hire Enterprise Agent</span>
            </h2>
            <p className="text-dark-muted text-sm mb-6">Create a new agent workspace node, configuring prompts, budgets, and reporting hierarchy.</p>
            
            <form onSubmit={handleCreateAgent} className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                    Agent Name
                  </label>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors"
                    placeholder="Sophia"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                    Title / Role
                  </label>
                  <input
                    type="text"
                    required
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors"
                    placeholder="Chief Executive Officer"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  System / Role Prompt
                </label>
                <textarea
                  required
                  rows={4}
                  value={rolePrompt}
                  onChange={(e) => setRolePrompt(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors resize-none"
                  placeholder="Define the agent instructions, boundary conditions, and decision criteria..."
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                    Reports to (Boss)
                  </label>
                  <select
                    value={bossAgentId}
                    onChange={(e) => setBossAgentId(e.target.value)}
                    className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none"
                  >
                    <option value="">None (Top Level Node)</option>
                    {agents.map(a => (
                      <option key={a.id} value={a.id}>{a.name} ({a.title})</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                    Model
                  </label>
                  <select
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none mb-2"
                  >
                    <option value="claude-3-5-sonnet-20241022">Claude 3.5 Sonnet</option>
                    <option value="claude-3-opus-20240229">Claude 3 Opus</option>
                    <option value="claude-3-haiku-20240307">Claude 3 Haiku</option>
                    <option value="gpt-4o">GPT-4o (OpenAI)</option>
                    <option value="gpt-4o-mini">GPT-4o mini (OpenAI)</option>
                    <option value="gemini-1.5-pro">Gemini 1.5 Pro (Google)</option>
                    <option value="gemini-1.5-flash">Gemini 1.5 Flash (Google)</option>
                    <option value="bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0">Bedrock Claude 3.5 Sonnet</option>
                    <option value="bedrock/anthropic.claude-3-haiku-20240307-v1:0">Bedrock Claude 3 Haiku</option>
                    <option value="custom_input">Custom Model...</option>
                  </select>
                  {model === "custom_input" && (
                    <input
                      type="text"
                      required
                      value={customModel}
                      onChange={(e) => setCustomModel(e.target.value)}
                      className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-2.5 text-white text-xs outline-none placeholder-dark-muted"
                      placeholder="e.g. openrouter/google/gemini-2.5-pro"
                    />
                  )}
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                    Monthly Budget (USD)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={monthlyBudget}
                    onChange={(e) => setMonthlyBudget(e.target.value)}
                    className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-3">
                  Granular Tool Access (Least Privilege)
                </label>
                <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                  {[
                    { name: "delegate_task", label: "Delegate Task" },
                    { name: "request_approval", label: "Request Approval" },
                    { name: "web_search", label: "Web Search" },
                    { name: "read_write_file", label: "Read/Write File" },
                    { name: "run_bash_command", label: "Run Bash" },
                    { name: "publish_meta_campaign", label: "Meta Ads" },
                    { name: "generate_image_asset", label: "Image Gen" },
                    { name: "hire_agent", label: "Hire Agent" }
                  ].map(tool => {
                    const isChecked = selectedTools.includes(tool.name);
                    return (
                      <button
                        type="button"
                        key={tool.name}
                        onClick={() => handleToolToggle(tool.name)}
                        className={`px-3 py-2 rounded-xl border text-xs font-medium transition-all text-center ${
                          isChecked
                            ? "bg-brand-primary/10 border-brand-primary text-brand-primary"
                            : "bg-dark-bg border-dark-border text-dark-muted hover:text-white"
                        }`}
                      >
                        {tool.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex gap-3 justify-end pt-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="border border-dark-border hover:bg-dark-border/20 text-white font-semibold rounded-xl px-6 py-2.5 text-sm transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="bg-brand-primary hover:bg-brand-primary/90 text-white font-semibold rounded-xl px-6 py-2.5 text-sm transition-colors shadow-lg shadow-brand-primary/20 flex items-center gap-2"
                >
                  {submitting && <Loader2 size={16} className="animate-spin" />}
                  <span>Hire Agent</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Inspected Agent Workspace & Artifacts Modal */}
      {inspectedAgent && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-5xl bg-dark-card border border-dark-border/80 rounded-3xl overflow-hidden shadow-2xl flex flex-col h-[80vh] max-h-[750px] animate-slide-in">
            
            {/* Modal Header */}
            <div className="p-6 border-b border-dark-border/40 flex justify-between items-center bg-dark-card/50 shrink-0">
              <div className="flex items-center gap-3">
                <div className="p-3 bg-brand-primary/10 border border-brand-primary/30 rounded-2xl text-brand-primary">
                  <User size={24} />
                </div>
                <div>
                  <div className="flex items-center gap-2.5">
                    <h2 className="text-xl font-bold text-white leading-tight">{inspectedAgent.name}</h2>
                    <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider ${
                      inspectedAgent.status === 'active' ? 'bg-brand-secondary/10 text-brand-secondary' : 'bg-brand-danger/10 text-brand-danger'
                    }`}>
                      {inspectedAgent.status}
                    </span>
                  </div>
                  <p className="text-xs text-dark-muted font-medium mt-0.5">{inspectedAgent.title}</p>
                </div>
              </div>
              <button
                onClick={() => setInspectedAgent(null)}
                className="text-dark-muted hover:text-white border border-dark-border hover:bg-dark-border/40 px-3.5 py-2 rounded-xl text-xs font-semibold transition-colors"
              >
                Fechar Painel
              </button>
            </div>

            {/* Modal Tabs */}
            <div className="flex border-b border-dark-border/40 bg-dark-bg/20 px-6 shrink-0 gap-6">
              <button
                onClick={() => setActiveAgentTab("prompts")}
                className={`py-3.5 text-xs font-bold uppercase tracking-wider border-b-2 transition-all outline-none ${
                  activeAgentTab === "prompts"
                    ? "border-brand-primary text-white"
                    : "border-transparent text-dark-muted hover:text-white"
                }`}
              >
                Instruções & Prompts
              </button>
              <button
                onClick={() => setActiveAgentTab("artifacts")}
                className={`py-3.5 text-xs font-bold uppercase tracking-wider border-b-2 transition-all outline-none flex items-center gap-2 ${
                  activeAgentTab === "artifacts"
                    ? "border-brand-primary text-white"
                    : "border-transparent text-dark-muted hover:text-white"
                }`}
              >
                <span>Criativos & Arquivos Gerados</span>
                <span className="bg-dark-border text-white text-[9px] px-2 py-0.5 rounded-full font-mono font-bold">
                  {artifacts.length}
                </span>
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-hidden p-6 flex flex-col">
              {activeAgentTab === "prompts" ? (
                <div className="space-y-5 overflow-y-auto flex-1 pr-1">
                  <div className="glass-panel p-5 rounded-2xl space-y-4">
                    <div>
                      <label className="block text-[10px] font-bold uppercase tracking-wider text-dark-muted mb-2">
                        Instruções de Comportamento (System Prompt)
                      </label>
                      <div className="bg-dark-bg/60 border border-dark-border rounded-xl p-4 text-xs text-white/90 font-mono whitespace-pre-wrap leading-relaxed max-h-[350px] overflow-y-auto">
                        {inspectedAgent.role_prompt}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-3 border-t border-dark-border/40 text-xs text-dark-muted font-medium">
                      <div>
                        <span className="block text-[10px] uppercase text-dark-muted mb-0.5">Modelo LLM</span>
                        <span className="text-white font-bold">{inspectedAgent.model}</span>
                      </div>
                      <div>
                        <span className="block text-[10px] uppercase text-dark-muted mb-0.5">Temperatura</span>
                        <span className="text-white font-bold">{inspectedAgent.temperature}</span>
                      </div>
                      <div>
                        <span className="block text-[10px] uppercase text-dark-muted mb-0.5">Orçamento Mensal</span>
                        <span className="text-white font-bold">${inspectedAgent.monthly_budget_usd.toFixed(2)} USD</span>
                      </div>
                      <div>
                        <span className="block text-[10px] uppercase text-dark-muted mb-0.5">Tipo do Adaptador</span>
                        <span className="text-white font-bold capitalize">{inspectedAgent.adapter_type}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                /* Artifacts Tab split layout */
                <div className="flex flex-1 overflow-hidden gap-6">
                  
                  {/* Left Column: Artifacts list */}
                  <div className="w-1/3 border-r border-dark-border/30 pr-4 overflow-y-auto space-y-2.5">
                    {loadingArtifacts ? (
                      <div className="py-12 flex justify-center text-dark-muted">
                        <Loader2 className="animate-spin text-brand-primary" />
                      </div>
                    ) : artifacts.length > 0 ? (
                      artifacts.map((art, idx) => {
                        const isSelected = selectedArtifact?.filename === art.filename;
                        return (
                          <div
                            key={idx}
                            onClick={() => handleSelectArtifact(art)}
                            className={`p-3.5 rounded-xl border text-left cursor-pointer transition-all ${
                              isSelected
                                ? "bg-brand-primary/10 border-brand-primary"
                                : "bg-dark-bg/60 border-dark-border/40 hover:border-dark-border"
                            }`}
                          >
                            <div className="flex items-center gap-3 mb-2">
                              <div className={`p-2 rounded-lg ${
                                isSelected ? "bg-brand-primary/20 text-brand-primary" : "bg-dark-border/40 text-dark-muted"
                              }`}>
                                {art.type === "image" ? <FileImage size={15} /> : art.type === "document" ? <FileText size={15} /> : <FileCode size={15} />}
                              </div>
                              <div className="min-w-0 flex-1">
                                <h4 className="font-bold text-white text-xs truncate" title={art.filename}>{art.filename}</h4>
                                <span className="text-[9px] text-dark-muted font-mono">{(art.size_bytes / 1024).toFixed(1)} KB</span>
                              </div>
                            </div>
                            <div className="text-[9px] text-dark-muted font-medium flex justify-between font-mono">
                              <span>Modificado:</span>
                              <span>{new Date(art.created_at).toLocaleString()}</span>
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      <div className="py-20 flex flex-col items-center justify-center text-center text-xs text-dark-muted gap-2 italic border border-dashed border-dark-border/20 rounded-2xl h-full">
                        <FileText size={20} />
                        <span>Nenhum criativo ou copy gerado ainda.</span>
                      </div>
                    )}
                  </div>

                  {/* Right Column: File Preview Panel */}
                  <div className="w-2/3 flex flex-col bg-dark-bg/40 border border-dark-border/40 rounded-2xl overflow-hidden p-5 relative">
                    {loadingArtifactContent ? (
                      <div className="absolute inset-0 flex items-center justify-center bg-dark-card/45 backdrop-blur-xs z-10 text-dark-muted">
                        <Loader2 className="animate-spin text-brand-primary mb-2" size={24} />
                      </div>
                    ) : null}

                    {selectedArtifact ? (
                      <div className="flex-1 flex flex-col justify-between overflow-hidden">
                        
                        {/* Preview Header */}
                        <div className="flex justify-between items-start gap-4 pb-3 border-b border-dark-border/30 mb-4 shrink-0">
                          <div className="min-w-0">
                            <h4 className="font-bold text-white text-sm truncate">{selectedArtifact.filename}</h4>
                            {selectedArtifact.prompt && (
                              <p className="text-[10px] text-dark-muted italic mt-0.5 line-clamp-1">Prompt: "{selectedArtifact.prompt}"</p>
                            )}
                          </div>
                          <button
                            onClick={() => handleDownloadArtifact(selectedArtifact)}
                            className="bg-brand-primary/10 hover:bg-brand-primary/20 text-brand-primary border border-brand-primary/30 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors flex items-center gap-1.5 shrink-0"
                          >
                            <Download size={13} />
                            <span>Download</span>
                          </button>
                        </div>

                        {/* Preview Display */}
                        <div className="flex-1 overflow-y-auto">
                          {selectedArtifact.type === "image" ? (
                            <div className="border border-dark-border/40 rounded-xl overflow-hidden bg-dark-bg/60 p-4 flex items-center justify-center min-h-[300px] max-h-[350px]">
                              {selectedArtifactBlobUrl ? (
                                <img
                                  src={selectedArtifactBlobUrl}
                                  alt={selectedArtifact.filename}
                                  className="max-w-full max-h-full object-contain shadow-lg"
                                />
                              ) : (
                                <span className="text-xs text-dark-muted">Carregando imagem...</span>
                              )}
                            </div>
                          ) : (
                            /* Text Copy Reader */
                            <textarea
                              readOnly
                              value={selectedArtifactContent}
                              className="w-full h-[320px] bg-dark-bg/60 border border-dark-border/50 rounded-xl p-4 text-xs text-white/90 font-mono resize-none leading-relaxed outline-none"
                            />
                          )}
                        </div>

                      </div>
                    ) : (
                      <div className="flex-1 flex flex-col items-center justify-center text-center text-xs text-dark-muted gap-2 italic">
                        <Eye size={24} className="text-dark-border" />
                        <span>Selecione um arquivo da galeria para visualizar a copy ou o criativo gerado.</span>
                      </div>
                    )}
                  </div>

                </div>
              )}
            </div>

          </div>
        </div>
      )}

      {/* Import OpenClaw Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="w-full max-w-2xl glass-panel rounded-2xl p-8 relative shadow-2xl my-8 border border-brand-primary/20">
            <h2 className="text-2xl font-bold text-white mb-2 flex items-center gap-3">
              <span>Import OpenClaw Agent</span>
            </h2>
            <p className="text-dark-muted text-sm mb-6">Paste your <code>openclaw.json</code> config file content below to register your agent in the organization.</p>
            
            <form onSubmit={handleImportOpenClaw} className="space-y-5">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Reporting Manager (Boss Agent)
                </label>
                <select
                  value={importBossId}
                  onChange={(e) => setImportBossId(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-3 py-3 text-white text-sm outline-none"
                >
                  <option value="">No Reporting Manager (Root/CEO)</option>
                  {agents.map(a => (
                    <option key={a.id} value={a.id}>{a.name} ({a.title})</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  openclaw.json Configuration Content
                </label>
                <textarea
                  required
                  rows={10}
                  value={openClawText}
                  onChange={(e) => setOpenClawText(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none font-mono"
                  placeholder={`{\n  "gateway": {\n    "name": "Traffic Specialist",\n    "model": "gpt-4o-mini",\n    "system_prompt": "Manage Meta ad accounts...",\n    "allowed_tools": ["shell", "web"]\n  }\n}`}
                />
              </div>

              <div className="flex justify-end gap-3.5 pt-4 border-t border-dark-border/40">
                <button
                  type="button"
                  onClick={() => {
                    setShowImportModal(false);
                    setOpenClawText("");
                    setImportBossId("");
                  }}
                  className="px-5 py-3 rounded-xl border border-dark-border hover:bg-dark-bg text-dark-muted hover:text-white font-semibold text-sm transition-all"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={importing}
                  className="px-6 py-3 rounded-xl bg-brand-primary hover:bg-brand-primary/95 text-white font-bold text-sm shadow-lg shadow-brand-primary/10 transition-colors flex items-center gap-2"
                >
                  {importing ? <Loader2 size={16} className="animate-spin" /> : null}
                  <span>Import Agent</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
