import { useState } from "react";
import { Clock, FolderTree, BookOpen, Terminal, Code, Info } from "lucide-react";

export default function Changelog() {
  const [activeTab, setActiveTab] = useState("changelog");

  const timelineData = [
    {
      date: "25 de Maio de 2026",
      title: "Responsividade Mobile & Tradução Completa (PT-BR)",
      category: "Frontend",
      details: [
        "Tradução de toda a interface, botões, modais, placeholders e mensagens para o Português.",
        "Componente customizado InfoTooltip com hover interativo e estilo glassmorphic em 11 seções e KPIs do Dashboard.",
        "Menu de navegação lateral retrátil (gaveta mobile) ativado por botão de hambúrguer com backdrop blur animado.",
        "Grid responsivo (grid-cols-1 em viewports pequenas) e tabelas com barra de rolagem horizontal (overflow-x-auto) para evitar quebra de layout.",
      ]
    },
    {
      date: "25 de Maio de 2026",
      title: "Importação de Agentes OpenClaw",
      category: "Integração",
      details: [
        "Rota backend POST /api/v1/agents/import-openclaw para parsear e traduzir arquivos openclaw.json.",
        "Mapeamento automático de ferramentas nativas do OpenClaw para ferramentas do ecossistema local.",
        "Interface com modal de colar-texto e seleção de líder responsável direto na página de Organograma.",
      ]
    },
    {
      date: "24 de Maio de 2026",
      title: "Integração Real com API do Meta Ads (v20.0)",
      category: "Backend & API",
      details: [
        "Busca de dados de campanhas ativas diretamente da API de produção do Meta Graph.",
        "Cálculos de ROAS real, CTR, impressões e classificação de saúde das campanhas (Excelente, Estável, Crítico).",
        "Tratamento dinâmico de estados vazios para contas sem credenciais salvas.",
      ]
    },
    {
      date: "23 de Maio de 2026",
      title: "Suporte Multi-Model & AWS Bedrock",
      category: "LLM Runtime",
      details: [
        "Integração do motor de execução com Anthropic Claude, OpenAI GPTs, Google Gemini e AWS Bedrock.",
        "Sistema de validação e teste de conexão em tempo real de credenciais na página de Configurações.",
        "Cálculo automatizado de custos reais de execução e faturamento com markup ajustável por empresa.",
      ]
    },
    {
      date: "22 de Maio de 2026",
      title: "Habilitação de Contratação Dinâmica (hire_agent)",
      category: "Segurança & Governança",
      details: [
        "Ferramenta hire_agent para permitir contratação de agentes subordinados programáticos por agentes superiores (ex: CEO).",
        "Fluxo de segurança com aprovação obrigatória por supervisor humano (human-in-the-loop) na fila de aprovações.",
        "Atualizações automáticas em tempo real da árvore do organograma usando WebSockets (evento org_updated).",
      ]
    }
  ];

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Title */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white mb-2 flex items-center gap-3">
          <BookOpen className="text-brand-primary" />
          <span>Histórico e Documentação de Manutenção</span>
        </h1>
        <p className="text-dark-muted text-sm">
          Acesse a linha do tempo de modificações, o guia de arquitetura de pastas e os comandos de teste e deploy necessários para a manutenção da aplicação.
        </p>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-dark-border/40 gap-2 overflow-x-auto pb-px">
        <button
          onClick={() => setActiveTab("changelog")}
          className={`flex items-center gap-2 px-6 py-3 text-sm font-medium border-b-2 transition-all shrink-0 ${
            activeTab === "changelog"
              ? "border-brand-primary text-brand-primary bg-brand-primary/5"
              : "border-transparent text-dark-muted hover:text-white hover:bg-dark-border/20"
          }`}
        >
          <Clock size={16} />
          <span>Linha do Tempo (Changelog)</span>
        </button>
        <button
          onClick={() => setActiveTab("structure")}
          className={`flex items-center gap-2 px-6 py-3 text-sm font-medium border-b-2 transition-all shrink-0 ${
            activeTab === "structure"
              ? "border-brand-primary text-brand-primary bg-brand-primary/5"
              : "border-transparent text-dark-muted hover:text-white hover:bg-dark-border/20"
          }`}
        >
          <FolderTree size={16} />
          <span>Arquitetura de Pastas</span>
        </button>
        <button
          onClick={() => setActiveTab("guide")}
          className={`flex items-center gap-2 px-6 py-3 text-sm font-medium border-b-2 transition-all shrink-0 ${
            activeTab === "guide"
              ? "border-brand-primary text-brand-primary bg-brand-primary/5"
              : "border-transparent text-dark-muted hover:text-white hover:bg-dark-border/20"
          }`}
        >
          <Terminal size={16} />
          <span>Manual do Desenvolvedor</span>
        </button>
      </div>

      {/* Tab Contents */}
      {activeTab === "changelog" && (
        <div className="space-y-6">
          <div className="relative border-l border-dark-border/60 ml-4 pl-8 space-y-8">
            {timelineData.map((item, index) => (
              <div key={index} className="relative group">
                {/* Dot */}
                <div className="absolute -left-[41px] top-1.5 w-6 h-6 rounded-full bg-dark-bg border-2 border-brand-primary flex items-center justify-center group-hover:scale-110 transition-transform">
                  <div className="w-2 h-2 bg-brand-primary rounded-full" />
                </div>
                {/* Content Card */}
                <div className="glass-panel p-6 rounded-2xl hover:border-brand-primary/30 transition-all">
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                    <span className="text-xs font-semibold text-brand-primary uppercase tracking-wider bg-brand-primary/10 px-2.5 py-1 rounded-md">
                      {item.category}
                    </span>
                    <span className="text-xs text-dark-muted font-medium">{item.date}</span>
                  </div>
                  <h3 className="text-lg font-bold text-white mb-4">{item.title}</h3>
                  <ul className="space-y-2 text-sm text-dark-muted list-disc list-inside">
                    {item.details.map((detail, idx) => (
                      <li key={idx} className="leading-relaxed">
                        <span className="text-dark-text">{detail}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === "structure" && (
        <div className="space-y-6">
          <div className="glass-panel p-6 rounded-2xl">
            <h3 className="text-base font-bold text-white mb-4 flex items-center gap-2">
              <FolderTree className="text-brand-primary" size={18} />
              <span>Mapeamento do Repositório</span>
            </h3>
            <p className="text-dark-muted text-sm mb-6 leading-relaxed">
              O projeto é dividido em uma arquitetura monorepo simplificada contendo duas pastas principais: <code className="bg-dark-bg border border-dark-border px-1.5 py-0.5 rounded text-white text-xs font-mono">backend</code> e <code className="bg-dark-bg border border-dark-border px-1.5 py-0.5 rounded text-white text-xs font-mono">frontend</code>.
            </p>

            <div className="space-y-6 font-mono text-sm text-dark-text">
              <div className="border border-dark-border/40 rounded-xl overflow-hidden bg-dark-bg/20">
                <div className="bg-dark-border/30 px-4 py-3 border-b border-dark-border/40 font-bold text-white text-xs uppercase tracking-wider flex items-center gap-2">
                  <Terminal size={14} className="text-brand-primary" />
                  <span>Diretório: backend/</span>
                </div>
                <div className="p-4 space-y-3.5">
                  <div className="pl-4 border-l-2 border-brand-primary/30">
                    <span className="text-white font-bold">app/api/</span> — Contém todas as rotas e endpoints REST da API FastAPI (ex: <code className="text-brand-accent">agents.py</code> para gerenciamento, <code className="text-brand-accent">dashboard.py</code> para KPIs agregados, <code className="text-brand-accent">meta.py</code> para Meta Ads).
                  </div>
                  <div className="pl-4 border-l-2 border-brand-primary/30">
                    <span className="text-white font-bold">app/models/</span> — Declarações de esquemas de tabelas do banco de dados (SQLAlchemy) e modelos de entidades.
                  </div>
                  <div className="pl-4 border-l-2 border-brand-primary/30">
                    <span className="text-white font-bold">app/services/</span> — Motores e runtimes lógicos (como o <code className="text-brand-accent">agent_executor.py</code> que gerencia a chamada sequencial das APIs de LLM).
                  </div>
                  <div className="pl-4 border-l-2 border-brand-primary/30">
                    <span className="text-white font-bold">tests/</span> — Coleção de testes automatizados com Pytest simulando requisições, retornos de APIs mockadas e lógica de orçamento.
                  </div>
                </div>
              </div>

              <div className="border border-dark-border/40 rounded-xl overflow-hidden bg-dark-bg/20">
                <div className="bg-dark-border/30 px-4 py-3 border-b border-dark-border/40 font-bold text-white text-xs uppercase tracking-wider flex items-center gap-2">
                  <Code size={14} className="text-brand-primary" />
                  <span>Diretório: frontend/</span>
                </div>
                <div className="p-4 space-y-3.5">
                  <div className="pl-4 border-l-2 border-brand-primary/30">
                    <span className="text-white font-bold">src/components/</span> — Componentes globais e compartilhados da interface de usuário (como o invólucro do menu responsivo <code className="text-brand-accent">Layout.jsx</code>).
                  </div>
                  <div className="pl-4 border-l-2 border-brand-primary/30">
                    <span className="text-white font-bold">src/pages/</span> — Páginas associadas a cada rota do painel (como o Dashboard de estatísticas, fila Kanban de tarefas, organograma, aprovações, configurações e gerenciador de tráfego do Facebook).
                  </div>
                  <div className="pl-4 border-l-2 border-brand-primary/30">
                    <span className="text-white font-bold">src/services/api.js</span> — Cliente de comunicação HTTP via Axios que consome os endpoints expostos pelo backend.
                  </div>
                  <div className="pl-4 border-l-2 border-brand-primary/30">
                    <span className="text-white font-bold">src/index.css</span> — Declarações globais de layout e variáveis do Tailwind v4 para acentuações de cores e glows.
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === "guide" && (
        <div className="space-y-6">
          <div className="glass-panel p-6 rounded-2xl space-y-6">
            <div>
              <h3 className="text-base font-bold text-white mb-2 flex items-center gap-2">
                <Terminal className="text-brand-primary" size={18} />
                <span>Manual Técnico do Desenvolvedor</span>
              </h3>
              <p className="text-dark-muted text-sm leading-relaxed">
                Utilize os comandos a seguir no terminal para realizar testes locais, auditar segurança e compilar arquivos para a implantação em produção.
              </p>
            </div>

            <div className="space-y-5">
              <div>
                <h4 className="text-sm font-semibold text-white mb-2 uppercase tracking-wide">1. Backend (Python/FastAPI)</h4>
                <div className="bg-dark-bg border border-dark-border p-4 rounded-xl font-mono text-xs text-brand-accent space-y-2">
                  <div># Instalação das dependências e drivers do banco de dados:</div>
                  <div className="text-white">pip install -r backend/requirements.txt</div>
                  <div className="pt-2"># Rodar todos os testes automatizados com cobertura:</div>
                  <div className="text-white">pytest backend/tests/</div>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold text-white mb-2 uppercase tracking-wide">2. Frontend (React/Vite)</h4>
                <div className="bg-dark-bg border border-dark-border p-4 rounded-xl font-mono text-xs text-brand-accent space-y-2">
                  <div># Acessar diretório e instalar pacotes do Node:</div>
                  <div className="text-white">cd frontend && npm install</div>
                  <div className="pt-2"># Executar servidor Vite local (desenvolvimento):</div>
                  <div className="text-white">npm run dev</div>
                  <div className="pt-2"># Verificar sintaxe e consistência de hooks (linter):</div>
                  <div className="text-white">npm run lint</div>
                  <div className="pt-2"># Compilar bundle estático otimizado para produção:</div>
                  <div className="text-white">npm run build</div>
                </div>
              </div>

              <div className="p-4 bg-brand-primary/10 border border-brand-primary/20 rounded-xl text-dark-text text-sm flex gap-3">
                <Info className="text-brand-primary shrink-0 mt-0.5" size={18} />
                <div>
                  <strong className="text-white font-semibold block mb-1">Boas Práticas de Design & Código:</strong>
                  <ul className="list-disc list-inside space-y-1 text-xs text-dark-muted">
                    <li>Ao adicionar novas seções no painel, use o componente <code className="text-brand-accent">InfoTooltip</code> para incluir guias rápidos de explicação.</li>
                    <li>Sempre verifique se a rota adicionada está englobada em <code className="text-brand-accent">ProtectedRoute</code> no arquivo <code className="text-brand-accent">App.jsx</code>.</li>
                    <li>Não insira cores hexadecimais avulsas em novos arquivos CSS ou estilos dinâmicos: utilize as variáveis globais configuradas no arquivo <code className="text-brand-accent">index.css</code>.</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
