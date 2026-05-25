import { useState, useEffect } from "react";
import { approvalAPI } from "../services/api";
import { 
  CheckSquare, 
  Check, 
  X, 
  Clock, 
  Terminal,
  AlertTriangle,
  Loader2
} from "lucide-react";

export default function Approvals() {
  const [approvals, setApprovals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actingId, setActingId] = useState(null);

  async function fetchApprovals() {
    try {
      const res = await approvalAPI.list();
      setApprovals(res.data);
    } catch (err) {
      console.error(err);
      setError("Falha ao carregar fila de aprovações.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchApprovals();
  }, []);

  const handleDecision = async (id, decision) => {
    setActingId(id);
    try {
      await approvalAPI.decide(id, decision);
      setApprovals(prev => 
        prev.map(app => 
          app.id === id 
            ? { ...app, status: decision === "approved" ? "approved" : "rejected" } 
            : app
        )
      );
    } catch (err) {
      console.error(err);
      const serverMsg = err.response?.data?.detail || "Falha ao enviar decisão para o motor.";
      alert(serverMsg);
    } finally {
      setActingId(null);
    }
  };

  const pendingApprovals = approvals.filter(a => a.status === "pending");
  const pastApprovals = approvals.filter(a => a.status !== "pending");

  if (loading) {
    return (
      <div className="h-96 flex flex-col items-center justify-center gap-3 text-dark-muted">
        <Loader2 size={32} className="animate-spin text-brand-primary" />
        <span>Carregando fila de aprovações...</span>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Title */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Portais de Governança e Aprovações</h1>
        <p className="text-dark-muted text-sm">
          Fila de validação humana (Human-in-the-loop). Aprovando ou negando ações sensíveis ou gastos de agentes antes que as execuções continuem.
        </p>
      </div>

      {error && (
        <div className="p-6 bg-brand-danger/10 border border-brand-danger/20 rounded-2xl text-brand-danger flex items-center gap-3">
          <AlertTriangle />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2 space-y-4">
          <h3 className="text-sm font-bold uppercase tracking-wider text-white mb-4 flex items-center gap-2">
            <Clock className="text-brand-accent animate-pulse" size={16} />
            <span>Aguardando Decisão da Diretoria ({pendingApprovals.length})</span>
          </h3>

          {pendingApprovals.length > 0 ? (
            pendingApprovals.map(approval => (
              <div key={approval.id} className="glass-panel rounded-2xl p-6 space-y-4 border border-dark-border">
                <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
                  <div className="space-y-1">
                    <span className="text-[10px] font-bold uppercase bg-brand-accent/15 text-brand-accent border border-brand-accent/25 px-2 py-0.5 rounded-md">
                      Ação: {approval.action_type}
                    </span>
                    <h4 className="text-white font-bold text-base mt-2">Solicitação #{approval.id}</h4>
                  </div>
                  
                  <div className="flex gap-2 shrink-0">
                    <button
                      disabled={actingId === approval.id}
                      onClick={() => handleDecision(approval.id, "rejected")}
                      className="bg-brand-danger/15 hover:bg-brand-danger/25 text-brand-danger border border-brand-danger/30 px-4 py-2 rounded-xl text-xs font-semibold transition-colors flex items-center gap-1.5"
                    >
                      <X size={14} />
                      <span>Recusar</span>
                    </button>
                    <button
                      disabled={actingId === approval.id}
                      onClick={() => handleDecision(approval.id, "approved")}
                      className="bg-brand-secondary/15 hover:bg-brand-secondary/25 text-brand-secondary border border-brand-secondary/30 px-4 py-2 rounded-xl text-xs font-semibold transition-colors flex items-center gap-1.5"
                    >
                      <Check size={14} />
                      <span>Aprovar</span>
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  <span className="text-[10px] uppercase font-bold text-dark-muted flex items-center gap-1.5">
                    <Terminal size={12} />
                    <span>Parâmetros do Comando / Contexto da Requisição</span>
                  </span>
                  <pre className="bg-dark-bg/60 border border-dark-border rounded-xl p-4 text-xs font-mono text-white/80 overflow-x-auto max-h-48">
                    {JSON.stringify(approval.payload, null, 2)}
                  </pre>
                </div>

                <div className="text-[10px] text-dark-muted flex flex-wrap gap-4">
                  <span>ID Tarefa: #{approval.payload?.task_id || "N/A"}</span>
                  <span>•</span>
                  <span>ID Agente: #{approval.payload?.agent_id || "N/A"}</span>
                  <span>•</span>
                  <span>Solicitado em: {new Date(approval.created_at).toLocaleString()}</span>
                </div>
              </div>
            ))
          ) : (
            <div className="py-20 text-center glass-panel rounded-2xl text-dark-muted italic">
              <CheckSquare size={36} className="mx-auto mb-3 text-dark-border" />
              <span>Nenhuma aprovação pendente. Agentes têm autorização livre.</span>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <h3 className="text-sm font-bold uppercase tracking-wider text-white mb-4">
            <span>Histórico de Governança</span>
          </h3>

          <div className="glass-panel rounded-2xl p-6 space-y-4 max-h-[500px] overflow-y-auto">
            {pastApprovals.length > 0 ? (
              <div className="space-y-4">
                {pastApprovals.map(approval => (
                  <div key={approval.id} className="p-4 bg-dark-bg/40 border border-dark-border/40 rounded-xl text-xs space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-white">Solicitação #{approval.id}</span>
                      <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wide ${
                        approval.status === "approved" ? "bg-brand-secondary/10 text-brand-secondary" : "bg-brand-danger/10 text-brand-danger"
                      }`}>
                        {approval.status === "approved" ? "Aprovado" : "Recusado"}
                      </span>
                    </div>
                    
                    <div className="text-dark-muted font-mono text-[10px]">
                      <strong>Ação:</strong> {approval.action_type}
                    </div>

                    <div className="text-[10px] text-dark-muted border-t border-dark-border/20 pt-2 flex justify-between">
                      <span>Por: {approval.decided_by || "Sistema"}</span>
                      <span>{new Date(approval.decided_at || approval.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-10 text-xs text-dark-muted italic">
                Nenhuma decisão anterior registrada.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
