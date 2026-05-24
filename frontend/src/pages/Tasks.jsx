import React, { useState, useEffect, useRef } from "react";
import { taskAPI, agentAPI } from "../services/api";
import { 
  KanbanSquare, 
  Plus, 
  Clock, 
  Play, 
  CheckCircle, 
  XCircle, 
  User, 
  ChevronRight, 
  Database,
  Cpu,
  Coins,
  AlertTriangle,
  Loader2,
  Paperclip
} from "lucide-react";

export default function Tasks() {
  const [tasks, setTasks] = useState([]);
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  
  // Create task states
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Selected task details panel states
  const [selectedTask, setSelectedTask] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loadingRuns, setLoadingRuns] = useState(false);

  const socketRef = useRef(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    fetchInitialData();
    connectWebSocket();

    return () => {
      isMountedRef.current = false;
      if (socketRef.current) {
        socketRef.current.onclose = null; // Clear to prevent reconnect loops
        socketRef.current.close();
      }
    };
  }, []);

  // Fetch runs when selected task changes
  useEffect(() => {
    if (selectedTask) {
      fetchRuns(selectedTask.id);
    }
  }, [selectedTask]);

  const fetchInitialData = async () => {
    try {
      const [tasksRes, agentsRes] = await Promise.all([
        taskAPI.list(),
        agentAPI.list()
      ]);
      setTasks(tasksRes.data);
      setAgents(agentsRes.data);
    } catch (err) {
      console.error(err);
      setError("Failed to fetch tasks/agents data.");
    } finally {
      setLoading(false);
    }
  };

  const fetchRuns = async (taskId) => {
    setLoadingRuns(true);
    try {
      const res = await taskAPI.getRuns(taskId);
      setRuns(res.data);
    } catch (err) {
      console.error("Failed to load task runs:", err);
    } finally {
      setLoadingRuns(false);
    }
  };

  const connectWebSocket = () => {
    const companyId = localStorage.getItem("companyId");
    if (!companyId || !isMountedRef.current) return;

    const token = localStorage.getItem("token");
    // Use ws relative path with token parameter
    const backendUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
    const wsProtocol = backendUrl.startsWith("https") ? "wss" : "ws";
    const wsHost = backendUrl.replace(/^https?:\/\//, "").replace(/\/$/, "");
    const wsUrl = `${wsProtocol}://${wsHost}/api/v1/ws/${companyId}${token ? `?token=${encodeURIComponent(token)}` : ""}`;
    logger("Establishing WebSocket connection to " + wsUrl);
    
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onmessage = (event) => {
      if (!isMountedRef.current) return;
      try {
        const data = JSON.parse(event.data);
        console.log("WebSocket event received:", data);
        
        // Refresh tasks on state changes
        if (
          data.type === "task_created" || 
          data.type === "run_status" || 
          data.type === "task_status"
        ) {
          refreshTasks();
          // If we currently view the updated task, reload runs
          if (selectedTask && (selectedTask.id === data.task_id || data.type === "run_status")) {
            fetchRuns(selectedTask.id);
          }
        }
      } catch (err) {
        console.error("Failed to parse websocket message:", err);
      }
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
    };

    ws.onclose = () => {
      if (!isMountedRef.current) return;
      console.log("WebSocket disconnected. Retrying in 5s...");
      setTimeout(() => {
        if (isMountedRef.current) connectWebSocket();
      }, 5000);
    };
  };

  const logger = (msg) => {
    console.log(`[WebSocket] ${msg}`);
  };

  const refreshTasks = async () => {
    try {
      const res = await taskAPI.list();
      setTasks(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  const handleCreateTask = async (e) => {
    e.preventDefault();
    if (!title || !description || !assigneeId) return;
    setSubmitting(true);
    try {
      const payload = {
        title,
        description,
        assignee_agent_id: parseInt(assigneeId),
        parent_task_id: null,
        traces_to_goal: true
      };
      const res = await taskAPI.create(payload);
      setTasks(prev => [...prev, res.data]);
      setShowCreateModal(false);
      setTitle("");
      setDescription("");
      setAssigneeId("");
    } catch (err) {
      console.error(err);
      alert("Failed to queue task.");
    } finally {
      setSubmitting(false);
    }
  };

  // Group tasks by status columns
  const getTasksByStatus = (status) => {
    return tasks.filter(t => t.status === status);
  };

  const getAgentName = (agentId) => {
    const agent = agents.find(a => a.id === agentId);
    return agent ? agent.name : "Unassigned";
  };

  const getAgentTitle = (agentId) => {
    const agent = agents.find(a => a.id === agentId);
    return agent ? agent.title : "";
  };

  if (loading) {
    return (
      <div className="h-96 flex flex-col items-center justify-center gap-3 text-dark-muted">
        <Loader2 size={32} className="animate-spin text-brand-primary" />
        <span>Loading ticket register...</span>
      </div>
    );
  }

  // Columns definition
  const columns = [
    { title: "Backlog / Todo", status: "todo", color: "border-t-brand-primary", bg: "bg-brand-primary/5" },
    { title: "Active Execution", status: "in_progress", color: "border-t-brand-accent", bg: "bg-brand-accent/5" },
    { title: "Success / Done", status: "done", color: "border-t-brand-secondary", bg: "bg-brand-secondary/5" },
    { title: "Failed / Paused", status: "failed", color: "border-t-brand-danger", bg: "bg-brand-danger/5" },
    { title: "Approval Gate", status: "paused", color: "border-t-amber-500", bg: "bg-amber-500/5" },
  ];

  return (
    <div className="space-y-8 h-full flex flex-col">
      {/* Top action header */}
      <div className="flex justify-between items-start shrink-0">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white mb-2">Corporate Task Board</h1>
          <p className="text-dark-muted text-sm">
            Kanban tracking of active tasks, assigned processors, subtask nesting, and live audit runs logs.
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="bg-brand-primary hover:bg-brand-primary/95 text-white font-semibold rounded-xl px-5 py-3 text-sm transition-colors shadow-lg shadow-brand-primary/20 flex items-center gap-2"
        >
          <Plus size={16} />
          <span>Queue Task</span>
        </button>
      </div>

      {error && (
        <div className="p-6 bg-brand-danger/10 border border-brand-danger/20 rounded-2xl text-brand-danger flex items-center gap-3 shrink-0">
          <AlertTriangle />
          <span>{error}</span>
        </div>
      )}

      {/* Kanban Board Layout */}
      <div className="flex-1 overflow-x-auto pb-4 flex gap-5 items-stretch min-h-[500px]">
        {columns.map(col => {
          const colTasks = tasks.filter(t => t.status === col.status);
          return (
            <div key={col.status} className="w-80 shrink-0 flex flex-col bg-dark-card border border-dark-border/60 rounded-2xl overflow-hidden shadow-md">
              <div className={`p-4 border-b border-dark-border border-t-4 ${col.color} flex justify-between items-center bg-dark-card/50`}>
                <span className="font-bold text-white text-sm tracking-wide">{col.title}</span>
                <span className="text-xs font-semibold px-2 py-0.5 bg-dark-border text-dark-muted rounded-full">
                  {colTasks.length}
                </span>
              </div>

              {/* Tasks List */}
              <div className="flex-1 p-4 overflow-y-auto space-y-3 max-h-[600px] min-h-[400px]">
                {colTasks.length > 0 ? (
                  colTasks.map(task => (
                    <div
                      key={task.id}
                      onClick={() => setSelectedTask(task)}
                      className={`glass-panel p-4 rounded-xl text-left cursor-pointer transition-all border ${
                        selectedTask?.id === task.id 
                          ? 'border-brand-primary shadow-lg shadow-brand-primary/10' 
                          : 'border-dark-border/40 hover:border-dark-border'
                      }`}
                    >
                      <h4 className="font-bold text-white text-sm mb-1.5 line-clamp-1">{task.title}</h4>
                      <p className="text-xs text-dark-muted line-clamp-2 mb-4 leading-relaxed">{task.description}</p>
                      
                      <div className="flex items-center justify-between border-t border-dark-border/40 pt-3 text-[10px] text-dark-muted">
                        <div className="flex items-center gap-1.5">
                          <User size={12} className="text-brand-primary" />
                          <span className="font-medium text-white">{getAgentName(task.assignee_agent_id)}</span>
                        </div>
                        <span>Task #{task.id}</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-dark-muted italic border-2 border-dashed border-dark-border/20 rounded-xl py-20">
                    No tickets in this state
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Task Trace Details Sidebar Slide-Over */}
      {selectedTask && (
        <div className="fixed inset-y-0 right-0 w-full max-w-3xl bg-dark-card border-l border-dark-border z-40 shadow-2xl flex flex-col animate-slide-in">
          {/* Header */}
          <div className="p-6 border-b border-dark-border flex justify-between items-center bg-dark-card/50">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-brand-primary">Task Trace Inspection</span>
              <h2 className="text-xl font-bold text-white">{selectedTask.title}</h2>
            </div>
            <button 
              onClick={() => setSelectedTask(null)}
              className="text-dark-muted hover:text-white border border-dark-border hover:bg-dark-border/40 px-3 py-1.5 rounded-xl text-xs transition-colors"
            >
              Close inspector
            </button>
          </div>

          {/* Trace body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* Task properties */}
            <div className="glass-panel rounded-2xl p-5 space-y-3">
              <p className="text-sm text-dark-text leading-relaxed">{selectedTask.description}</p>
              
              <div className="grid grid-cols-2 gap-4 border-t border-dark-border/40 pt-4 text-xs text-dark-muted">
                <div>
                  <span className="block mb-1">Assignee Agent</span>
                  <span className="font-bold text-white flex items-center gap-1.5">
                    <Cpu size={14} className="text-brand-primary" />
                    {getAgentName(selectedTask.assignee_agent_id)} ({getAgentTitle(selectedTask.assignee_agent_id)})
                  </span>
                </div>
                <div>
                  <span className="block mb-1">Created At</span>
                  <span className="font-bold text-white flex items-center gap-1.5">
                    <Clock size={14} className="text-brand-primary" />
                    {new Date(selectedTask.created_at).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>

            {/* Hierarchical subtasks trace */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-dark-muted mb-3 flex items-center gap-2">
                <Database size={14} />
                <span>Nesting & Goal Alignment (Subtasks)</span>
              </h3>
              <div className="glass-panel rounded-2xl p-4 space-y-2 text-sm">
                <div className="flex items-center gap-2 text-brand-primary font-semibold">
                  <CheckCircle size={14} />
                  <span>Goal alignment: {selectedTask.traces_to_goal ? "Verified" : "Bypassed"}</span>
                </div>
                <div className="text-xs text-dark-muted">
                  {tasks.filter(t => t.parent_task_id === selectedTask.id).length > 0 ? (
                    <div className="space-y-2 mt-2">
                      <span className="block font-semibold">Delegated subtasks:</span>
                      {tasks.filter(t => t.parent_task_id === selectedTask.id).map(child => (
                        <div key={child.id} className="flex items-center justify-between p-2.5 bg-dark-bg border border-dark-border rounded-xl">
                          <span className="text-white font-medium">{child.title}</span>
                          <span className="text-[10px] uppercase font-bold text-brand-accent">{child.status}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <span>No subtasks delegated by this node.</span>
                  )}
                </div>
              </div>
            </div>

            {/* Execution Runs & Steps Log */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-dark-muted mb-3 flex items-center gap-2">
                <Cpu size={14} />
                <span>Execution runs history</span>
              </h3>

              {loadingRuns ? (
                <div className="py-12 flex justify-center text-dark-muted">
                  <Loader2 className="animate-spin text-brand-primary" />
                </div>
              ) : runs.length > 0 ? (
                <div className="space-y-4">
                  {runs.map((run, idx) => (
                    <div key={run.id} className="glass-panel rounded-2xl p-5 space-y-4 border border-dark-border">
                      <div className="flex items-center justify-between border-b border-dark-border/40 pb-3">
                        <span className="font-bold text-white text-sm">Run #{run.id} (Attempt {runs.length - idx})</span>
                        <div className="flex gap-2">
                          <span className="text-xs font-medium bg-dark-border px-2.5 py-1 rounded-lg text-white flex items-center gap-1">
                            <Coins size={12} className="text-amber-500" />
                            <span>${run.total_cost_usd.toFixed(4)}</span>
                          </span>
                          <span className={`text-xs font-bold uppercase px-2.5 py-1 rounded-lg ${
                            run.status === "success" ? "bg-brand-secondary/15 text-brand-secondary" : run.status === "failed" ? "bg-brand-danger/15 text-brand-danger" : "bg-brand-accent/15 text-brand-accent"
                          }`}>
                            {run.status}
                          </span>
                        </div>
                      </div>

                      {/* Steps chain */}
                      <div className="space-y-3.5 pl-3 border-l-2 border-brand-primary/20">
                        {run.steps.map((step, sIdx) => (
                          <div key={step.id} className="relative pl-5 text-xs text-dark-muted leading-relaxed">
                            {/* Bullet icon */}
                            <div className="absolute -left-6 top-1.5 w-2 h-2 bg-brand-primary rounded-full ring-4 ring-brand-primary/10" />

                            <div className="flex items-center gap-3 mb-1">
                              <span className="font-semibold text-white uppercase tracking-wider text-[10px]">{step.kind}</span>
                              <span>•</span>
                              <span>{step.latency_ms}ms</span>
                              {step.cost_usd > 0 && (
                                <>
                                  <span>•</span>
                                  <span className="text-amber-500 font-medium">${step.cost_usd.toFixed(5)}</span>
                                </>
                              )}
                            </div>

                            {/* Render step specifics */}
                            {step.kind === "llm_call" && (
                              <div className="bg-dark-bg/60 border border-dark-border/50 rounded-xl p-3 mt-1.5 text-white/80 font-mono text-[10px] whitespace-pre-wrap max-h-40 overflow-y-auto">
                                <strong>Prompt Response:</strong><br />
                                {step.output?.content?.map(c => c.text).join("\n") || JSON.stringify(step.output)}
                              </div>
                            )}

                            {step.kind === "tool_call" && (
                              <div className="bg-dark-bg/60 border border-dark-border/50 rounded-xl p-3 mt-1.5 space-y-1 text-white/80 font-mono text-[10px]">
                                <div><strong>Tool used:</strong> <span className="text-brand-primary">{step.input?.tool_name}</span></div>
                                <div><strong>Input:</strong> {JSON.stringify(step.input?.input)}</div>
                                <div><strong>Output:</strong> {JSON.stringify(step.output?.result)}</div>
                              </div>
                            )}

                            {step.kind === "approval" && (
                              <div className="bg-dark-bg/60 border border-dark-border/50 rounded-xl p-3 mt-1.5 space-y-1 text-white/80 font-mono text-[10px]">
                                <div className="text-amber-500 font-bold">BOARD APPROVAL ATTACHED</div>
                                <div><strong>Action Category:</strong> {step.input?.action}</div>
                                <div><strong>Output Result:</strong> {JSON.stringify(step.output?.result)}</div>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-10 bg-dark-bg border border-dark-border/40 rounded-2xl text-dark-muted text-xs italic">
                  No execution runs recorded for this ticket.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal to create task */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-lg glass-panel rounded-2xl p-8 relative shadow-2xl">
            <h2 className="text-2xl font-bold text-white mb-2 flex items-center gap-3">
              <KanbanSquare className="text-brand-primary" />
              <span>Queue Corporate Task</span>
            </h2>
            <p className="text-dark-muted text-sm mb-6">Create a new task, assign it to a node agent, and track completion.</p>

            <form onSubmit={handleCreateTask} className="space-y-5">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Task Title
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors"
                  placeholder="e.g. Set up auth routes"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Task Description
                </label>
                <textarea
                  required
                  rows={4}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none transition-colors resize-none"
                  placeholder="Describe details, specifications, and acceptance criteria..."
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Assignee Agent
                </label>
                <select
                  required
                  value={assigneeId}
                  onChange={(e) => setAssigneeId(e.target.value)}
                  className="w-full bg-dark-bg border border-dark-border focus:border-brand-primary rounded-xl px-4 py-3 text-white text-sm outline-none"
                >
                  <option value="">Select processor agent...</option>
                  {agents.map(a => (
                    <option key={a.id} value={a.id}>{a.name} ({a.title})</option>
                  ))}
                </select>
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
                  <span>Queue Task</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
