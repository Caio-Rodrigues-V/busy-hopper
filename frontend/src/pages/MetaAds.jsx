import React, { useState, useEffect } from "react";
import { metaAPI } from "../services/api";
import {
  Megaphone,
  Settings,
  ShieldCheck,
  DollarSign,
  Activity,
  CheckCircle2,
  Loader2,
  AlertTriangle,
  Sparkles,
  Eye,
  EyeOff,
  Layers,
  FileCode,
  Calendar,
  Send,
  Plus
} from "lucide-react";

export default function MetaAds() {
  // Config states
  const [config, setConfig] = useState({
    access_token: "",
    ad_account_id: "",
    page_id: "",
    pixel_id: ""
  });
  const [isConfigured, setIsConfigured] = useState(false);
  const [last4, setLast4] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);

  // Campaign Form states
  const [campaign, setCampaign] = useState({
    campaign_name: "",
    objective: "CONVERSIONS",
    daily_budget_usd: 25.0
  });
  const [deployingCampaign, setDeployingCampaign] = useState(false);

  // Lists & General states
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("console"); // "console" | "campaigns"
  
  // Deploy success modal state
  const [successDetails, setSuccessDetails] = useState(null);

  useEffect(() => {
    fetchMetaData();
  }, []);

  const fetchMetaData = async () => {
    try {
      const [configRes, campaignsRes] = await Promise.all([
        metaAPI.getConfig(),
        metaAPI.listCampaigns()
      ]);
      
      if (configRes.data.configured) {
        setIsConfigured(true);
        setLast4(configRes.data.last4 || "");
        setConfig({
          access_token: "••••••••••••••••••••" + (configRes.data.last4 || ""),
          ad_account_id: configRes.data.ad_account_id || "",
          page_id: configRes.data.page_id || "",
          pixel_id: configRes.data.pixel_id || ""
        });
      }
      setCampaigns(campaignsRes.data);
    } catch (err) {
      console.error("Failed to load Meta integration data:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveConfig = async (e) => {
    e.preventDefault();
    if (!config.access_token || !config.ad_account_id) {
      alert("Access Token and Ad Account ID are required.");
      return;
    }
    
    setSavingConfig(true);
    try {
      // If user hasn't edited the token (still showing dots), we send a dummy or ignore token update,
      // but to keep it simple, if token starts with bullet points, we might warn them.
      let tokenToSend = config.access_token;
      if (tokenToSend.startsWith("••••")) {
        // If it's unchanged, just preserve the token by not sending bullet points.
        // For simplicity, we assume they enter a new token if configuring.
        if (isConfigured) {
          alert("Please enter a new access token if you are modifying settings, or write your token.");
          setSavingConfig(false);
          return;
        }
      }

      await metaAPI.saveConfig(config);
      alert("Meta integration configuration saved successfully!");
      setIsConfigured(true);
      fetchMetaData();
    } catch (err) {
      console.error(err);
      alert("Failed to save Meta Ads configurations.");
    } finally {
      setSavingConfig(false);
    }
  };

  const handleDeployCampaign = async (e) => {
    e.preventDefault();
    if (!isConfigured) {
      alert("Please configure your Meta Integration before deploying campaigns.");
      return;
    }
    if (!campaign.campaign_name || campaign.daily_budget_usd <= 0) {
      alert("Invalid campaign parameters.");
      return;
    }

    setDeployingCampaign(true);
    try {
      const res = await metaAPI.deployCampaign(campaign);
      setSuccessDetails(res.data.details);
      setCampaign({
        campaign_name: "",
        objective: "CONVERSIONS",
        daily_budget_usd: 25.0
      });
      // Refresh list
      const campaignsRes = await metaAPI.listCampaigns();
      setCampaigns(campaignsRes.data);
    } catch (err) {
      console.error(err);
      alert(err.response?.data?.detail || "Failed to deploy campaign simulation.");
    } finally {
      setDeployingCampaign(false);
    }
  };

  if (loading) {
    return (
      <div className="h-96 flex flex-col items-center justify-center gap-3 text-dark-muted">
        <Loader2 size={32} className="animate-spin text-brand-primary" />
        <span>Loading Meta Integration console...</span>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2 flex items-center gap-3">
            <Megaphone className="text-brand-primary" size={32} />
            <span>Meta Ads Orchestrator</span>
          </h1>
          <p className="text-dark-muted text-sm max-w-2xl">
            Configure integration tokens, set up ad account targets, and deploy paid traffic campaigns (Facebook & Instagram ads) either manually or via autonomous agents.
          </p>
        </div>

        {/* Status Indicator */}
        <div className={`px-4 py-2 rounded-2xl border flex items-center gap-2.5 text-xs font-semibold self-start md:self-center ${
          isConfigured
            ? "bg-brand-secondary/10 border-brand-secondary/30 text-brand-secondary"
            : "bg-brand-danger/10 border-brand-danger/30 text-brand-danger"
        }`}>
          <span className={`w-2.5 h-2.5 rounded-full ${isConfigured ? "bg-brand-secondary animate-pulse" : "bg-brand-danger"}`} />
          <span>{isConfigured ? "Meta Integration Active" : "Meta Config Pending"}</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-dark-border/40 gap-6">
        <button
          onClick={() => setActiveTab("console")}
          className={`pb-3.5 text-sm font-semibold tracking-wide border-b-2 transition-all outline-none ${
            activeTab === "console"
              ? "border-brand-primary text-white"
              : "border-transparent text-dark-muted hover:text-white"
          }`}
        >
          Control Console
        </button>
        <button
          onClick={() => setActiveTab("campaigns")}
          className={`pb-3.5 text-sm font-semibold tracking-wide border-b-2 transition-all outline-none flex items-center gap-2 ${
            activeTab === "campaigns"
              ? "border-brand-primary text-white"
              : "border-transparent text-dark-muted hover:text-white"
          }`}
        >
          <span>Deployed Campaigns</span>
          <span className="bg-dark-border text-white text-[10px] px-2 py-0.5 rounded-full font-mono">
            {campaigns.length}
          </span>
        </button>
      </div>

      {activeTab === "console" ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          
          {/* Form 1: Meta Configuration */}
          <div className="glass-panel rounded-2xl p-6 space-y-6">
            <div className="flex items-center gap-2 pb-4 border-b border-dark-border/40">
              <Settings className="text-brand-primary" size={18} />
              <h3 className="text-sm font-bold uppercase tracking-wider text-white">Meta API Connection Settings</h3>
            </div>

            <form onSubmit={handleSaveConfig} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Meta System User Access Token
                </label>
                <div className="relative">
                  <input
                    type={showToken ? "text" : "password"}
                    required
                    value={config.access_token}
                    onChange={(e) => setConfig({ ...config, access_token: e.target.value })}
                    className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl pl-4 pr-11 py-3 text-white text-sm outline-none transition-colors font-mono"
                    placeholder={isConfigured ? "••••••••••••••••" : "EAAGb..."}
                  />
                  <button
                    type="button"
                    onClick={() => setShowToken(!showToken)}
                    className="absolute right-3.5 inset-y-0 text-dark-muted hover:text-white transition-colors"
                  >
                    {showToken ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                <p className="text-[10px] text-dark-muted mt-1.5">Facebook Graph API token representing a system user with Ads Management scopes.</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                    Meta Ad Account ID
                  </label>
                  <input
                    type="text"
                    required
                    value={config.ad_account_id}
                    onChange={(e) => setConfig({ ...config, ad_account_id: e.target.value })}
                    className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors font-mono"
                    placeholder="e.g. 1029384756"
                  />
                  <p className="text-[9px] text-dark-muted mt-1">Specify numeric account ID (excluding act_ prefix).</p>
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                    Target Page ID (Optional)
                  </label>
                  <input
                    type="text"
                    value={config.page_id}
                    onChange={(e) => setConfig({ ...config, page_id: e.target.value })}
                    className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors font-mono"
                    placeholder="e.g. 9876543210"
                  />
                  <p className="text-[9px] text-dark-muted mt-1">Default Facebook Page used for feed ads.</p>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Meta Pixel ID (Optional)
                </label>
                <input
                  type="text"
                  value={config.pixel_id}
                  onChange={(e) => setConfig({ ...config, pixel_id: e.target.value })}
                  className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors font-mono"
                  placeholder="e.g. 5432109876"
                />
                <p className="text-[10px] text-dark-muted mt-1.5">Facebook Pixel or Dataset ID used to track conversion events.</p>
              </div>

              <button
                type="submit"
                disabled={savingConfig}
                className="w-full bg-brand-primary hover:bg-brand-primary/95 text-white font-semibold rounded-xl py-3 text-sm transition-colors flex items-center justify-center gap-2 shadow-lg shadow-brand-primary/10 mt-2"
              >
                {savingConfig ? <Loader2 size={16} className="animate-spin" /> : <ShieldCheck size={16} />}
                <span>Configure Meta Connection</span>
              </button>
            </form>
          </div>

          {/* Form 2: Direct Campaign Deployer */}
          <div className="glass-panel rounded-2xl p-6 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-4 border-b border-dark-border/40 mb-6">
                <div className="flex items-center gap-2">
                  <Sparkles className="text-brand-accent" size={18} />
                  <h3 className="text-sm font-bold uppercase tracking-wider text-white">Manual Campaign Deployer</h3>
                </div>
                {isConfigured && (
                  <span className="text-[10px] bg-brand-accent/15 border border-brand-accent/30 text-brand-accent px-2 py-0.5 rounded-full font-bold uppercase">
                    Ready
                  </span>
                )}
              </div>

              {!isConfigured ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center p-6 bg-dark-bg/40 border border-dark-border/40 rounded-xl min-h-[250px]">
                  <AlertTriangle className="text-brand-secondary mb-3" size={32} />
                  <h4 className="text-white font-bold text-sm mb-1.5">Meta Integration Required</h4>
                  <p className="text-xs text-dark-muted max-w-xs">
                    Please configure and save your Meta API Access Token and Ad Account ID in the left settings pane to unlock deployment capabilities.
                  </p>
                </div>
              ) : (
                <form onSubmit={handleDeployCampaign} className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                      Campaign Name
                    </label>
                    <input
                      type="text"
                      required
                      value={campaign.campaign_name}
                      onChange={(e) => setCampaign({ ...campaign, campaign_name: e.target.value })}
                      className="w-full bg-dark-bg border border-dark-border focus:border-brand-accent rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors"
                      placeholder="e.g. Black Friday Traffic Burst"
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                        Campaign Objective
                      </label>
                      <select
                        value={campaign.objective}
                        onChange={(e) => setCampaign({ ...campaign, objective: e.target.value })}
                        className="w-full bg-dark-bg border border-dark-border focus:border-brand-accent rounded-xl px-3 py-3 text-white text-sm outline-none"
                      >
                        <option value="CONVERSIONS">CONVERSIONS (Sales)</option>
                        <option value="LEAD_GENERATION">LEAD GENERATION</option>
                        <option value="TRAFFIC">TRAFFIC (Clicks)</option>
                        <option value="REACH">REACH (Impressions)</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                        Daily Budget (USD)
                      </label>
                      <div className="relative">
                        <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-dark-muted">
                          <DollarSign size={16} />
                        </div>
                        <input
                          type="number"
                          step="1"
                          required
                          value={campaign.daily_budget_usd}
                          onChange={(e) => setCampaign({ ...campaign, daily_budget_usd: parseFloat(e.target.value) })}
                          className="w-full bg-dark-bg border border-dark-border focus:border-brand-accent rounded-xl pl-9 pr-4 py-3 text-white text-sm outline-none transition-colors"
                        />
                      </div>
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={deployingCampaign}
                    className="w-full bg-brand-accent hover:bg-brand-accent/95 text-dark-bg font-bold rounded-xl py-3 text-sm transition-colors flex items-center justify-center gap-2 shadow-lg shadow-brand-accent/15 mt-4"
                  >
                    {deployingCampaign ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                    <span>Deploy Simulated Campaign</span>
                  </button>
                </form>
              )}
            </div>

            <div className="p-4 bg-dark-bg/60 border border-dark-border/40 rounded-xl text-[10px] text-dark-muted space-y-1.5 leading-relaxed mt-6">
              <div className="font-bold text-white uppercase text-[9px] tracking-wider mb-1">Simulated Mode Guidelines:</div>
              <p>• Clicking deploy simulates standard Facebook Graph Ads endpoints posting.</p>
              <p>• Outputs a simulated unique Campaign ID representing active delivery.</p>
              <p>• Saves a tracking payload JSON in the server's company workspace filesystem.</p>
            </div>
          </div>

        </div>
      ) : (
        /* Campaigns Ledger */
        <div className="glass-panel rounded-2xl p-6">
          <div className="flex justify-between items-center pb-4 border-b border-dark-border/40 mb-6">
            <h3 className="text-sm font-bold uppercase tracking-wider text-white flex items-center gap-2">
              <Layers className="text-brand-secondary" size={16} />
              <span>Active Campaigns Dashboard</span>
            </h3>
            <button
              onClick={() => setActiveTab("console")}
              className="text-xs text-brand-primary hover:underline font-semibold flex items-center gap-1"
            >
              <Plus size={14} />
              <span>Create New</span>
            </button>
          </div>

          {campaigns.length > 0 ? (
            <div className="space-y-6">
              {/* Overview Metrics Dashboard */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-dark-bg/40 rounded-2xl p-4 flex items-center justify-between border border-dark-border/40">
                  <div>
                    <p className="text-[10px] uppercase font-bold text-dark-muted tracking-wider">Total Active Budget</p>
                    <h4 className="text-xl font-bold text-white mt-1">
                      ${campaigns.reduce((acc, c) => acc + (c.daily_budget_usd || 0), 0).toFixed(2)}/day
                    </h4>
                  </div>
                  <div className="p-3 bg-brand-primary/10 text-brand-primary rounded-xl">
                    <DollarSign size={20} />
                  </div>
                </div>
                
                <div className="bg-dark-bg/40 rounded-2xl p-4 flex items-center justify-between border border-dark-border/40">
                  <div>
                    <p className="text-[10px] uppercase font-bold text-dark-muted tracking-wider">Total Spend (Real)</p>
                    <h4 className="text-xl font-bold text-brand-secondary mt-1">
                      ${campaigns.reduce((acc, c) => acc + (c.total_spent || 0), 0).toFixed(2)}
                    </h4>
                  </div>
                  <div className="p-3 bg-brand-secondary/10 text-brand-secondary rounded-xl">
                    <Activity size={20} />
                  </div>
                </div>

                <div className="bg-dark-bg/40 rounded-2xl p-4 flex items-center justify-between border border-dark-border/40">
                  <div>
                    <p className="text-[10px] uppercase font-bold text-dark-muted tracking-wider">Average CTR</p>
                    <h4 className="text-xl font-bold text-white mt-1">
                      {(campaigns.reduce((acc, c) => acc + (c.ctr || 0), 0) / campaigns.length).toFixed(2)}%
                    </h4>
                  </div>
                  <div className="p-3 bg-brand-accent/10 text-brand-accent rounded-xl">
                    <Eye size={20} />
                  </div>
                </div>

                <div className="bg-dark-bg/40 rounded-2xl p-4 flex items-center justify-between border border-dark-border/40">
                  <div>
                    <p className="text-[10px] uppercase font-bold text-dark-muted tracking-wider">Total Conversions</p>
                    <h4 className="text-xl font-bold text-white mt-1">
                      {campaigns.reduce((acc, c) => acc + (c.conversions || 0), 0)}
                    </h4>
                  </div>
                  <div className="p-3 bg-brand-secondary/15 text-brand-secondary rounded-xl">
                    <CheckCircle2 size={20} />
                  </div>
                </div>
              </div>

              {/* Campaigns Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {campaigns.map((c, i) => {
                  const isAgent = c.mode === "AGENT_DEPLOY";
                  return (
                    <div key={i} className="bg-dark-bg/65 border border-dark-border/60 hover:border-dark-muted/80 rounded-2xl p-5 space-y-4 transition-all">
                      <div className="flex justify-between items-start gap-2">
                        <div>
                          <h4 className="font-bold text-white text-base leading-tight mb-1 flex items-center gap-2">
                            <Megaphone size={16} className="text-brand-secondary shrink-0" />
                            <span>{c.campaign_name}</span>
                          </h4>
                          <span className={`inline-block text-[9px] uppercase tracking-wide px-2.5 py-0.5 rounded-full font-bold font-mono ${
                            c.objective === "CONVERSIONS" || c.objective === "OUTCOMES" ? "bg-brand-secondary/15 text-brand-secondary" :
                            c.objective === "LEAD_GENERATION" ? "bg-brand-accent/15 text-brand-accent" :
                            "bg-brand-primary/15 text-brand-primary"
                          }`}>
                            {c.objective}
                          </span>
                        </div>

                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-lg border uppercase tracking-wider flex items-center gap-1.5 ${
                          isAgent
                            ? "bg-brand-primary/10 border-brand-primary/30 text-brand-primary"
                            : "bg-brand-accent/15 border-brand-accent/30 text-brand-accent"
                        }`}>
                          <span>{isAgent ? "🤖 Agent" : "👤 Manual"}</span>
                        </span>
                      </div>

                      <div className="grid grid-cols-3 gap-2.5 bg-dark-bg/40 p-3 rounded-xl border border-dark-border/30 text-xs">
                        <div>
                          <div className="text-[10px] text-dark-muted font-semibold uppercase tracking-wider mb-0.5">Budget</div>
                          <div className="font-bold text-white flex items-center">
                            <DollarSign size={13} className="shrink-0 text-brand-primary" />
                            <span>{c.daily_budget_usd}/day</span>
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] text-dark-muted font-semibold uppercase tracking-wider mb-0.5">Total Spent</div>
                          <div className="font-bold text-brand-secondary flex items-center">
                            <DollarSign size={13} className="shrink-0" />
                            <span>{c.total_spent?.toFixed(2) || "0.00"}</span>
                          </div>
                        </div>
                        <div>
                          <div className="text-[10px] text-dark-muted font-semibold uppercase tracking-wider mb-0.5">Health</div>
                          <span className={`inline-block text-[9px] uppercase tracking-wide px-2 py-0.5 rounded font-bold ${
                            c.health === "Excellent" ? "bg-brand-secondary/15 text-brand-secondary border border-brand-secondary/30" :
                            c.health === "Stable" ? "bg-brand-accent/15 text-brand-accent border border-brand-accent/30" :
                            c.health === "Underperforming" ? "bg-brand-danger/10 text-brand-danger border border-brand-danger/30" :
                            "bg-dark-border text-dark-muted"
                          }`}>
                            {c.health || "Active"}
                          </span>
                        </div>
                      </div>

                      <div className="grid grid-cols-4 gap-2 text-center text-[10px] bg-dark-bg/20 p-2.5 rounded-xl border border-dark-border/20">
                        <div>
                          <div className="text-dark-muted mb-0.5">Impressions</div>
                          <div className="font-bold text-white">{c.impressions?.toLocaleString() || 0}</div>
                        </div>
                        <div>
                          <div className="text-dark-muted mb-0.5">Clicks</div>
                          <div className="font-bold text-white">{c.clicks?.toLocaleString() || 0}</div>
                        </div>
                        <div>
                          <div className="text-dark-muted mb-0.5">CTR</div>
                          <div className="font-bold text-white">{(c.ctr || 0).toFixed(2)}%</div>
                        </div>
                        <div>
                          <div className="text-dark-muted mb-0.5">ROAS</div>
                          <div className="font-bold text-brand-secondary">{(c.roas || 0).toFixed(2)}x</div>
                        </div>
                      </div>

                      <div className="text-[10px] space-y-1.5 pt-2 border-t border-dark-border/40 text-dark-muted font-medium">
                        <div className="flex justify-between items-center font-mono">
                          <span>Status:</span>
                          <span className={`font-bold flex items-center gap-1.5 ${c.status === "ACTIVE" ? "text-brand-secondary" : "text-dark-muted"}`}>
                            {c.status === "ACTIVE" && <span className="w-1.5 h-1.5 bg-brand-secondary rounded-full animate-ping" />}
                            {c.status}
                          </span>
                        </div>
                        <div className="flex justify-between items-center font-mono">
                          <span>Conversions (Leads):</span>
                          <span className="text-white font-bold">{c.conversions || 0}</span>
                        </div>
                        <div className="flex justify-between items-center font-mono">
                          <span>FB Campaign ID:</span>
                          <span className="text-white bg-dark-bg px-2 py-0.5 rounded border border-dark-border/60">{c.facebook_campaign_id}</span>
                        </div>
                        <div className="flex justify-between items-center font-mono">
                          <span className="flex items-center gap-1">
                            <Calendar size={11} />
                            <span>Deployed At:</span>
                          </span>
                          <span className="text-white">
                            {new Date(c.deployed_at).toLocaleString()}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="h-48 border border-dashed border-dark-border/60 rounded-2xl flex flex-col items-center justify-center text-xs text-dark-muted gap-2 italic">
              <Megaphone size={24} className="text-dark-muted" />
              <span>No active Meta campaigns found. Ensure your Meta integration settings are configured.</span>
            </div>
          )}
        </div>
      )}

      {/* Deploy Success Modal */}
      {successDetails && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-lg glass-panel rounded-3xl p-8 relative shadow-2xl border border-brand-secondary/30">
            <div className="flex items-center gap-3.5 mb-5">
              <div className="p-3 bg-brand-secondary/15 border border-brand-secondary/30 rounded-2xl text-brand-secondary">
                <CheckCircle2 size={24} />
              </div>
              <div>
                <h3 className="text-xl font-bold text-white">Campaign Simulated Successfully!</h3>
                <p className="text-xs text-brand-secondary font-semibold">Simulated Meta Graph API Response</p>
              </div>
            </div>

            <div className="space-y-4 bg-dark-bg/60 border border-dark-border/40 rounded-2xl p-5 text-xs text-dark-muted font-medium">
              <div className="flex justify-between py-1.5 border-b border-dark-border/30">
                <span>Campaign Name:</span>
                <span className="text-white font-bold">{successDetails.campaign_name}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-dark-border/30">
                <span>Objective:</span>
                <span className="text-white font-mono bg-brand-secondary/10 text-brand-secondary px-2 py-0.5 rounded font-bold uppercase">{successDetails.objective}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-dark-border/30">
                <span>Daily Ad Budget:</span>
                <span className="text-white font-bold">${successDetails.daily_budget_usd} USD</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-dark-border/30">
                <span>Facebook Campaign ID:</span>
                <span className="text-brand-accent font-mono font-bold">{successDetails.facebook_campaign_id}</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-dark-border/30">
                <span>Ad Account ID:</span>
                <span className="text-white font-mono">act_{successDetails.ad_account_id}</span>
              </div>
              <div className="flex justify-between py-1.5">
                <span>Trace Workspace Path:</span>
                <span className="text-white truncate font-mono max-w-[200px]" title={`workspace/company_X/manual_meta_campaign_...`}>
                  {successDetails.facebook_campaign_id.split("/")[1] ? `manual_meta_campaign_${successDetails.facebook_campaign_id.split("/")[1].split("_")[1]}.json` : "campaign.json"}
                </span>
              </div>
            </div>

            <button
              onClick={() => setSuccessDetails(null)}
              className="w-full bg-brand-secondary hover:bg-brand-secondary/90 text-white font-bold rounded-2xl py-3 text-sm transition-colors mt-6 shadow-lg shadow-brand-secondary/10"
            >
              Acknowledge Deployment
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
