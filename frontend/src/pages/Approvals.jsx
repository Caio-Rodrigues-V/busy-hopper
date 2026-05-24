import React, { useState, useEffect } from "react";
import { approvalAPI } from "../services/api";
import { 
  CheckSquare, 
  Check, 
  X, 
  Clock, 
  User, 
  Terminal,
  DollarSign,
  AlertTriangle,
  Loader2
} from "lucide-react";

export default function Approvals() {
  const [approvals, setApprovals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actingId, setActingId] = useState(null);

  useEffect(() => {
    fetchApprovals();
  }, []);

  const fetchApprovals = async () => {
    try {
      const res = await approvalAPI.list();
      setApprovals(res.data);
    } catch (err) {
      console.error(err);
      setError("Failed to load approvals queue.");
    } finally {
      setLoading(false);
    }
  };

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
      alert("Failed to submit decision to engine.");
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
        <span>Loading approvals queue...</span>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Board Governance Gateways</h1>
        <p className="text-dark-muted text-sm">
          Human-in-the-loop validation queue. Approve or deny sensitive agent command actions or cost expenditures before executions resume.
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
            <span>Awaiting Board Decision ({pendingApprovals.length})</span>
          </h3>

          {pendingApprovals.length > 0 ? (
            pendingApprovals.map(approval => (
              <div key={approval.id} className="glass-panel rounded-2xl p-6 space-y-4 border border-dark-border">
                <div className="flex justify-between items-start">
                  <div className="space-y-1">
                    <span className="text-[10px] font-bold uppercase bg-brand-accent/15 text-brand-accent border border-brand-accent/25 px-2 py-0.5 rounded-md">
                      Action: {approval.action_type}
                    </span>
                    <h4 className="text-white font-bold text-base mt-2">Request #{approval.id}</h4>
                  </div>
                  
                  <div className="flex gap-2">
                    <button
                      disabled={actingId === approval.id}
                      onClick={() => handleDecision(approval.id, "rejected")}
                      className="bg-brand-danger/15 hover:bg-brand-danger/25 text-brand-danger border border-brand-danger/30 px-4 py-2 rounded-xl text-xs font-semibold transition-colors flex items-center gap-1.5"
                    >
                      <X size={14} />
                      <span>Reject</span>
                    </button>
                    <button
                      disabled={actingId === approval.id}
                      onClick={() => handleDecision(approval.id, "approved")}
                      className="bg-brand-secondary/15 hover:bg-brand-secondary/25 text-brand-secondary border border-brand-secondary/30 px-4 py-2 rounded-xl text-xs font-semibold transition-colors flex items-center gap-1.5"
                    >
                      <Check size={14} />
                      <span>Approve</span>
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  <span className="text-[10px] uppercase font-bold text-dark-muted flex items-center gap-1.5">
                    <Terminal size={12} />
                    <span>Command Parameters / Context payload</span>
                  </span>
                  <pre className="bg-dark-bg/60 border border-dark-border rounded-xl p-4 text-xs font-mono text-white/80 overflow-x-auto max-h-48">
                    {JSON.stringify(approval.payload, null, 2)}
                  </pre>
                </div>

                <div className="text-[10px] text-dark-muted flex gap-4">
                  <span>Task ID: #{approval.payload?.task_id || "N/A"}</span>
                  <span>•</span>
                  <span>Agent ID: #{approval.payload?.agent_id || "N/A"}</span>
                  <span>•</span>
                  <span>Requested: {new Date(approval.created_at).toLocaleString()}</span>
                </div>
              </div>
            ))
          ) : (
            <div className="py-20 text-center glass-panel rounded-2xl text-dark-muted italic">
              <CheckSquare size={36} className="mx-auto mb-3 text-dark-border" />
              <span>No pending approvals. Agents have clear clearance.</span>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <h3 className="text-sm font-bold uppercase tracking-wider text-white mb-4">
            <span>Governance Ledger</span>
          </h3>

          <div className="glass-panel rounded-2xl p-6 space-y-4 max-h-[500px] overflow-y-auto">
            {pastApprovals.length > 0 ? (
              <div className="space-y-4">
                {pastApprovals.map(approval => (
                  <div key={approval.id} className="p-4 bg-dark-bg/40 border border-dark-border/40 rounded-xl text-xs space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-white">Request #{approval.id}</span>
                      <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wide ${
                        approval.status === "approved" ? "bg-brand-secondary/10 text-brand-secondary" : "bg-brand-danger/10 text-brand-danger"
                      }`}>
                        {approval.status}
                      </span>
                    </div>
                    
                    <div className="text-dark-muted font-mono text-[10px]">
                      <strong>Action:</strong> {approval.action_type}
                    </div>

                    <div className="text-[10px] text-dark-muted border-t border-dark-border/20 pt-2 flex justify-between">
                      <span>By: user_{approval.decided_by || "System"}</span>
                      <span>{new Date(approval.decided_at || approval.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-10 text-xs text-dark-muted italic">
                No past board decisions logged.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
