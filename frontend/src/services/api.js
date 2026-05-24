import axios from "axios";

const rawApiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
const formattedApiUrl = (rawApiUrl.startsWith("http://") && !rawApiUrl.includes("localhost") && !rawApiUrl.includes("127.0.0.1"))
  ? rawApiUrl.replace("http://", "https://")
  : rawApiUrl;

const API_URL = `${formattedApiUrl.replace(/\/$/, "")}/api/v1`;

const api = axios.create({
  baseURL: API_URL,
});

// Request interceptor to attach JWT token and Company ID
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers["Authorization"] = `Bearer ${token}`;
    }
    const companyId = localStorage.getItem("companyId");
    if (companyId) {
      config.headers["X-Company-ID"] = companyId;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle session timeouts
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      // Clear credentials and force reload
      localStorage.removeItem("token");
      if (!window.location.pathname.includes("/login") && !window.location.pathname.includes("/register")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export const authAPI = {
  register: (email, password) => api.post("/auth/register", { email, password }),
  login: (email, password) => {
    const params = new URLSearchParams();
    params.append("username", email);
    params.append("password", password);
    return api.post("/auth/login", params, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" }
    });
  },
  me: () => api.get("/companies"), // Simple fallback to verify token
};

export const companyAPI = {
  list: () => api.get("/companies"),
  create: (name, mission) => api.post("/companies", { name, mission }),
  update: (id, data) => api.put(`/companies/${id}`, data),
  get: (id) => api.get(`/companies/${id}`),
};

export const credentialAPI = {
  list: () => api.get("/credentials"),
  create: (provider, apiKey) => api.post("/credentials", { provider, api_key: apiKey }),
  delete: (id) => api.delete(`/credentials/${id}`),
};

export const agentAPI = {
  list: () => api.get("/agents"),
  create: (data) => api.post("/agents", data),
  update: (id, data) => api.put(`/agents/${id}`, data),
  delete: (id) => api.delete(`/agents/${id}`),
  getArtifacts: (agentId) => api.get(`/agents/${agentId}/artifacts`),
  getArtifactContent: (agentId, filename, type = 'text') => api.get(`/agents/${agentId}/artifacts/${filename}`, { responseType: type }),
};

export const taskAPI = {
  list: () => api.get("/tasks"),
  create: (data) => api.post("/tasks", data),
  get: (id) => api.get(`/tasks/${id}`),
  getRuns: (id) => api.get(`/tasks/${id}/runs`),
};

export const approvalAPI = {
  list: () => api.get("/approvals"),
  decide: (id, decision) => api.post(`/approvals/${id}/decide`, { decision }),
};

export const dashboardAPI = {
  getMetrics: () => api.get("/dashboard/metrics"),
};

export const auditAPI = {
  listLogs: () => api.get("/audit"),
};

export const metaAPI = {
  getConfig: () => api.get("/meta/config"),
  saveConfig: (data) => api.post("/meta/config", data),
  deployCampaign: (data) => api.post("/meta/campaign", data),
  listCampaigns: () => api.get("/meta/campaigns"),
};

export default api;
