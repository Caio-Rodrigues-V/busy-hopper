import { useState, useEffect } from "react";
import { credentialAPI, companyAPI, auditAPI } from "../services/api";
import { 
  Trash2, 
  KeyRound, 
  FileText,
  DollarSign,
  TrendingUp,
  Percent,
  Loader2,
  AlertTriangle
} from "lucide-react";

export default function Settings() {
  const [credentials, setCredentials] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Company settings states
  const [company, setCompany] = useState(null);
  const [budget, setBudget] = useState(0);
  const [markup, setMarkup] = useState(0);
  const [updatingCompany, setUpdatingCompany] = useState(false);

  // New credential states
  const [provider, setProvider] = useState("anthropic");
  const [apiKey, setApiKey] = useState("");
  const [submittingKey, setSubmittingKey] = useState(false);
  const [awsAccessKeyId, setAwsAccessKeyId] = useState("");
  const [awsSecretAccessKey, setAwsSecretAccessKey] = useState("");
  const [awsRegion, setAwsRegion] = useState("us-east-1");
  const [testingKey, setTestingKey] = useState(false);

  async function fetchSettingsData() {
    const companyId = localStorage.getItem("companyId");
    try {
      const [credRes, auditRes, companyRes] = await Promise.all([
        credentialAPI.list(),
        auditAPI.listLogs(),
        companyAPI.get(companyId)
      ]);
      setCredentials(credRes.data);
      setAuditLogs(auditRes.data);
      setCompany(companyRes.data);
      setBudget(companyRes.data.monthly_budget_usd);
      setMarkup(companyRes.data.markup_pct);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchSettingsData();
  }, []);

  const handleUpdateCompanySettings = async (e) => {
    e.preventDefault();
    setUpdatingCompany(true);
    try {
      const res = await companyAPI.update(company.id, {
        monthly_budget_usd: parseFloat(budget),
        markup_pct: parseFloat(markup)
      });
      setCompany(res.data);
      alert("Configurações da empresa atualizadas com sucesso!");
    } catch (err) {
      console.error(err);
      alert("Falha ao atualizar parâmetros da empresa.");
    } finally {
      setUpdatingCompany(false);
    }
  };

  const handleTestConnection = async () => {
    let finalKey = apiKey;
    if (provider === "aws_bedrock") {
      if (!awsAccessKeyId || !awsSecretAccessKey) {
        alert("Por favor, preencha o AWS Access Key ID e o AWS Secret Access Key.");
        return;
      }
      finalKey = JSON.stringify({
        aws_access_key_id: awsAccessKeyId,
        aws_secret_access_key: awsSecretAccessKey,
        aws_region: awsRegion
      });
    } else {
      if (!apiKey) {
        alert("Por favor, preencha a chave de API (API Key).");
        return;
      }
    }

    setTestingKey(true);
    try {
      const res = await credentialAPI.validate(provider, finalKey);
      if (res.data.valid) {
        alert("Validação com SUCESSO: As credenciais da API são válidas e a conexão foi estabelecida!");
      } else {
        alert(`Falha na validação: ${res.data.error}`);
      }
    } catch (err) {
      console.error(err);
      alert(err.response?.data?.detail || "Falha na validação devido a erro de conexão.");
    } finally {
      setTestingKey(false);
    }
  };

  const handleAddCredential = async (e) => {
    e.preventDefault();
    
    let finalKey = apiKey;
    if (provider === "aws_bedrock") {
      if (!awsAccessKeyId || !awsSecretAccessKey) {
        alert("Credenciais AWS são obrigatórias para o Bedrock.");
        return;
      }
      finalKey = JSON.stringify({
        aws_access_key_id: awsAccessKeyId,
        aws_secret_access_key: awsSecretAccessKey,
        aws_region: awsRegion
      });
    } else {
      if (!apiKey) return;
    }

    setSubmittingKey(true);
    try {
      const res = await credentialAPI.create(provider, finalKey);
      setCredentials(prev => {
        const filtered = prev.filter(c => c.provider !== provider);
        return [...filtered, res.data];
      });
      setApiKey("");
      setAwsAccessKeyId("");
      setAwsSecretAccessKey("");
      alert("Credenciais do provedor de LLM configuradas com sucesso!");
    } catch (err) {
      console.error(err);
      alert("Falha ao salvar as credenciais.");
    } finally {
      setSubmittingKey(false);
    }
  };

  const handleDeleteCredential = async (id) => {
    if (!confirm("Tem certeza de que deseja remover estas credenciais?")) return;
    try {
      await credentialAPI.delete(id);
      setCredentials(credentials.filter(c => c.id !== id));
    } catch (err) {
      console.error(err);
      alert("Falha ao excluir as credenciais.");
    }
  };

  if (loading) {
    return (
      <div className="h-96 flex flex-col items-center justify-center gap-3 text-dark-muted">
        <Loader2 size={32} className="animate-spin text-brand-primary" />
        <span>Carregando configurações da empresa...</span>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Configurações da Empresa</h1>
        <p className="text-dark-muted text-sm">
          Ajuste o orçamento mensal de gastos, defina margens de markup, configure credenciais criptografadas de LLM e inspecione a trilha de auditoria.
        </p>
      </div>

      {/* Grid splits */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        
        {/* Left column: configurations */}
        <div className="space-y-8">
          
          {/* Company params */}
          <div className="glass-panel rounded-2xl p-6 space-y-6">
            <h3 className="text-sm font-bold uppercase tracking-wider text-white flex items-center gap-2">
              <TrendingUp className="text-brand-primary" size={16} />
              <span>Parâmetros de Orçamento e Margem de Preço (Markup)</span>
            </h3>

            <form onSubmit={handleUpdateCompanySettings} className="space-y-5">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Limite de Orçamento Mensal da Empresa (USD)
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-dark-muted">
                    <DollarSign size={16} />
                  </div>
                  <input
                    type="number"
                    step="1"
                    required
                    value={budget}
                    onChange={(e) => setBudget(e.target.value)}
                    className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl pl-9 pr-4 py-3 text-white text-sm outline-none transition-colors"
                  />
                </div>
                <p className="text-[10px] text-dark-muted mt-1.5">Se a empresa atingir esse limite de custo, todas as execuções ativas serão interrompidas automaticamente.</p>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Porcentagem de Margem de Markup (%)
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-dark-muted">
                    <Percent size={16} />
                  </div>
                  <input
                    type="number"
                    step="0.1"
                    required
                    value={markup}
                    onChange={(e) => setMarkup(e.target.value)}
                    className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl pl-9 pr-4 py-3 text-white text-sm outline-none transition-colors"
                  />
                </div>
                <p className="text-[10px] text-dark-muted mt-1.5">Determina os preços de faturamento dos clientes (custo real + porcentagem de markup).</p>
              </div>

              <button
                type="submit"
                disabled={updatingCompany}
                className="w-full bg-brand-primary hover:bg-brand-primary/95 text-white font-semibold rounded-xl py-3 text-sm transition-colors flex items-center justify-center gap-2"
              >
                {updatingCompany && <Loader2 size={16} className="animate-spin" />}
                <span>Salvar Parâmetros</span>
              </button>
            </form>
          </div>

          {/* Credentials manager */}
          <div className="glass-panel rounded-2xl p-6 space-y-6">
            <h3 className="text-sm font-bold uppercase tracking-wider text-white flex items-center gap-2">
              <KeyRound className="text-brand-accent" size={16} />
              <span>Credenciais de API dos Provedores</span>
            </h3>

            {/* Existing credentials */}
            {credentials.length > 0 ? (
              <div className="space-y-2.5">
                {credentials.map(c => (
                  <div key={c.id} className="flex justify-between items-center bg-dark-bg/60 border border-dark-border rounded-xl p-3.5">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-brand-accent/10 border border-brand-accent/30 rounded-lg text-brand-accent">
                        <KeyRound size={16} />
                      </div>
                      <div>
                        <div className="font-bold text-white text-sm capitalize">Chave de API {c.provider}</div>
                        <div className="text-[10px] text-dark-muted font-mono">Sufixo: ************{c.last4}</div>
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeleteCredential(c.id)}
                      className="text-brand-danger hover:bg-brand-danger/10 p-2 rounded-lg border border-transparent hover:border-brand-danger/20 transition-all"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-4 bg-brand-danger/10 border border-brand-danger/20 rounded-xl text-brand-danger text-xs flex items-center gap-2.5">
                <AlertTriangle size={18} />
                <span>Nenhuma chave de API salva. Preencha o formulário abaixo para autorizar.</span>
              </div>
            )}

            {/* Add credentials form */}
            <form onSubmit={handleAddCredential} className="space-y-4 pt-3 border-t border-dark-border/40">
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                    Provedor de LLM
                  </label>
                  <select
                    value={provider}
                    onChange={(e) => setProvider(e.target.value)}
                    className="w-full bg-dark-bg border border-dark-border focus:border-brand-accent rounded-xl px-3 py-3 text-white text-sm outline-none"
                  >
                    <option value="anthropic">Anthropic (Claude)</option>
                    <option value="openai">OpenAI (GPT)</option>
                    <option value="gemini">Google (Gemini)</option>
                    <option value="meta_ads">Meta Ads (Facebook/Instagram)</option>
                    <option value="openrouter">OpenRouter</option>
                    <option value="cohere">Cohere</option>
                    <option value="aws_bedrock">AWS Bedrock</option>
                    <option value="custom">Gateway de API Personalizado</option>
                  </select>
                </div>

                {provider === "aws_bedrock" ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                          AWS Access Key ID
                        </label>
                        <input
                          type="text"
                          required
                          value={awsAccessKeyId}
                          onChange={(e) => setAwsAccessKeyId(e.target.value)}
                          className="w-full bg-dark-bg border border-dark-border focus:border-brand-accent rounded-xl px-4 py-3 text-white text-sm outline-none placeholder-dark-muted"
                          placeholder="AKIAIOSFODNN7EXAMPLE"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                          AWS Secret Access Key
                        </label>
                        <input
                          type="password"
                          required
                          value={awsSecretAccessKey}
                          onChange={(e) => setAwsSecretAccessKey(e.target.value)}
                          className="w-full bg-dark-bg border border-dark-border focus:border-brand-accent rounded-xl px-4 py-3 text-white text-sm outline-none placeholder-dark-muted"
                          placeholder="••••••••••••••••••••••••••••••••••••••••"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                        Região AWS
                      </label>
                      <select
                        value={awsRegion}
                        onChange={(e) => setAwsRegion(e.target.value)}
                        className="w-full bg-dark-bg border border-dark-border focus:border-brand-accent rounded-xl px-4 py-3 text-white text-sm outline-none"
                      >
                        <option value="us-east-1">us-east-1 (N. Virginia)</option>
                        <option value="us-west-2">us-west-2 (Oregon)</option>
                        <option value="eu-central-1">eu-central-1 (Frankfurt)</option>
                        <option value="ap-southeast-1">ap-southeast-1 (Singapore)</option>
                      </select>
                    </div>
                  </div>
                ) : (
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                      Chave de API (Criptografada via Fernet)
                    </label>
                    <input
                      type="password"
                      required
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      className="w-full bg-dark-bg border border-dark-border focus:border-brand-accent rounded-xl px-4 py-3 text-white text-sm outline-none placeholder-dark-muted"
                      placeholder={provider === "openai" ? "sk-proj-..." : provider === "gemini" ? "AIzaSy..." : "sk-..."}
                    />
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleTestConnection}
                  disabled={testingKey}
                  className="w-full bg-dark-bg border border-dark-border hover:bg-dark-border/40 text-dark-muted hover:text-white font-semibold rounded-xl py-3 text-sm transition-colors flex items-center justify-center gap-2"
                >
                  {testingKey && <Loader2 size={16} className="animate-spin" />}
                  <span>Testar Conexão</span>
                </button>
                <button
                  type="submit"
                  disabled={submittingKey}
                  className="w-full bg-brand-accent hover:bg-brand-accent/90 text-white font-semibold rounded-xl py-3 text-sm transition-colors flex items-center justify-center gap-2"
                >
                  {submittingKey && <Loader2 size={16} className="animate-spin" />}
                  <span>Salvar Credenciais</span>
                </button>
              </div>
            </form>
          </div>

        </div>

        {/* Right column: Audit log ledger (Append-only logs) */}
        <div className="glass-panel rounded-2xl p-6 flex flex-col min-h-[500px]">
          <h3 className="text-sm font-bold uppercase tracking-wider text-white mb-6 flex items-center gap-2 shrink-0">
            <FileText className="text-brand-secondary" size={16} />
            <span>Log de Auditoria Imutável de Governança</span>
          </h3>

          <div className="flex-1 overflow-y-auto space-y-3.5 max-h-[600px] pr-1">
            {auditLogs.length > 0 ? (
              auditLogs.map((log) => (
                <div key={log.id} className="p-3 bg-dark-bg/60 border border-dark-border/40 rounded-xl space-y-1.5 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-white text-[11px] uppercase tracking-wider text-brand-secondary">
                      {log.action}
                    </span>
                    <span className="text-[10px] text-dark-muted">
                      {new Date(log.created_at).toLocaleString()}
                    </span>
                  </div>
                  
                  <div className="text-dark-text leading-relaxed font-medium">
                    Autor: <span className="font-mono text-brand-accent">{log.actor}</span>
                  </div>
                  
                  {log.payload && (
                    <pre className="bg-dark-bg/85 rounded-lg p-2.5 text-[9px] font-mono text-dark-muted overflow-x-auto">
                      {JSON.stringify(log.payload, null, 2)}
                    </pre>
                  )}
                </div>
              ))
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-dark-muted italic">
                Nenhum evento registrado nos logs de auditoria da empresa.
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
