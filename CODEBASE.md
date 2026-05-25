# Mapa Geral da Base de Código (Codebase Blueprint) - Antigravity

Este documento serve como um mapa de arquitetura detalhado da base de código do **Antigravity**. Ele explica a integração de fluxo de dados, a modelagem de banco de dados, a lógica do motor de agentes e as diretrizes de manutenção estrutural.

---

## 🗺️ 1. Visão Geral da Arquitetura & Fluxo de Dados

O projeto está estruturado em duas partes principais conectadas de forma assíncrona:
1. **Frontend (React + Vite + Tailwind v4 + Recharts)**: Painel administrativo de controle do usuário, com atualização em tempo real via WebSockets.
2. **Backend (FastAPI + SQLAlchemy + Pytest + Alembic)**: API REST, persistência e motor de orquestração de LLMs e ferramentas.

### 🔄 Fluxo de Execução de Tarefas de Agentes
Abaixo está o ciclo de vida de uma tarefa delegada aos agentes programáticos:

```mermaid
graph TD
    A[Usuário cria Tarefa no Frontend] --> B[Backend cria Registro de Task & inicia Run]
    B --> C[agent_executor.py assume a execução]
    C --> D{Precisa chamar LLM?}
    D -- Sim --> E[Valida credenciais da API salvas e chama API da LLM]
    D -- Não --> F[Executa ferramenta ou finaliza]
    E --> G{LLM solicita chamada de ferramenta?}
    G -- Sim: Ferramenta Crítica (Ex: Meta Ads, Hire, Bash) --> H[Gera pendência na Fila de Aprovações]
    G -- Sim: Ferramenta Livre --> I[Executa ferramenta diretamente]
    G -- Não --> J[Retorna resposta da LLM]
    H --> K[Usuário clica em 'Aprovar' no Frontend]
    K --> L[agent_executor.py executa a ferramenta pendente e resume fluxo]
    I --> C
    L --> C
    J --> M[Tarefa concluída: Deliverables salvos no banco]
```

### 📡 Sincronização em Tempo Real (WebSockets)
* O módulo `websocket_manager.py` mantém conexões ativas com o frontend.
* Sempre que um agente é contratado ou a estrutura organizacional muda, o backend emite o evento `"org_updated"`.
* O frontend escuta esse evento em `OrgChart.jsx` e re-renderiza o gráfico de hierarquia instantaneamente sem recarregar a página.

---

## 🗄️ 2. Estrutura do Banco de Dados (Modelos)

O banco de dados utiliza relacionamento relacional gerenciado por SQLAlchemy. Abaixo estão as principais entidades e seus propósitos:

| Modelo | Arquivo | Propósito / Responsabilidade |
| :--- | :--- | :--- |
| **User** | `models/user.py` | Usuários do sistema (emails e senhas criptografadas por bcrypt) com controle de acesso. |
| **Company** | `models/company.py` | Empresas/Tenants do sistema. Cada empresa possui seu próprio orçamento mensal e margem de markup. |
| **Agent** | `models/agent.py` | Cadastro de Agentes (Nome, Cargo, Prompt de Instruções, Modelo associado, Temperatura e ID do Líder Superior). |
| **ApiCredential** | `models/api_credential.py` | Armazena chaves de API criptografadas por empresa (OpenAI, Anthropic, Gemini, AWS Bedrock, Meta Ads). |
| **Task** | `models/task.py` | Tarefa criada (Título, descrição, status, agente responsável, contagem total de tokens consumidos e custos gerados). |
| **Run** | `models/run.py` | Sessão ativa de execução de uma tarefa, contendo múltiplos passos (*steps*). |
| **Approval** | `models/approval.py` | Fila de auditoria humana (*human-in-the-loop*). Trava a execução de ferramentas críticas até aprovação manual. |
| **Audit** | `models/audit.py` | Histórico permanente de auditoria de operações críticas efetuadas na plataforma. |

---

## ⚙️ 3. Mapeamento Lógico do Backend (`backend/`)

### **Pontos de Entrada e Rotas (`app/api/`)**
* **`agents.py`**: Controle da árvore de agentes. Possui o endpoint `/import-openclaw` para decodificar arquivos de configuração do OpenClaw, mapeando as permissões das ferramentas e convertendo-as para o formato local.
* **`dashboard.py`**: Realiza queries agregadas no banco para retornar os KPIs financeiros. Agrupa tokens consumidos por tarefa no banco para compor o painel de despesas do dashboard.
* **`meta.py`**: Integração direta com a API Graph do Meta Ads. Lê credenciais ativas da empresa e realiza chamadas reais de listagem e criação de campanhas de anúncios.
* **`api_credentials.py`**: Valida credenciais (OpenAI, Anthropic, Gemini, Bedrock, Meta) em tempo real enviando requisições leves de 1 token para testar a conectividade antes de salvá-las.

### **Runtimes e Motores (`app/services/`)**
* **`agent_executor.py`**:
  * **Motor Unificado**: Contém o parser de mensagens e mapeamento de ferramentas para todas as LLMs integradas.
  * **AWS Bedrock**: Suporte à API Converse do Bedrock usando `boto3` para orquestração.
  * **Intercepção de Ações**: Detecta se um agente quer chamar `publish_meta_campaign`, `run_bash_command` ou `hire_agent`, pausando a thread de execução e inserindo uma solicitação pendente no banco de dados (`Approval`).

---

## 🎨 4. Mapeamento de Interface do Frontend (`frontend/`)

### **Páginas Principais (`src/pages/`)**
* **`Dashboard.jsx`**: Renderiza os KPIs agregados em HSL Glassmorphic e contém os gráficos Recharts com tooltips acoplados para transparência de gastos das LLMs.
* **`OrgChart.jsx`**: Árvore hierárquica dinâmica. Inclui o painel de contratação manual de agentes e importação rápida de arquivos de configuração OpenClaw.
* **`Tasks.jsx`**: Quadro Kanban de tarefas da organização. Permite criar tarefas, inspecionar logs passo a passo das execuções em tempo real e ver os arquivos entregáveis na galeria.
* **`Approvals.jsx`**: Fila de aprovações. Permite aprovar/rejeitar chamadas de comandos bash, criação de campanhas de anúncios ou criação de novos agentes subordinados.
* **`MetaAds.jsx`**: Monitoramento de campanhas de anúncios reais no Meta. Exibe orçamento, impressões, cliques, CTR, ROAS e classificação de saúde da campanha.
* **`Settings.jsx`**: Configuração financeira da empresa (orçamento limite e markup) e chaves das APIs com botão de teste dinâmico.
* **`Changelog.jsx`**: Página interna de ajuda que expõe este mapa de código e o histórico de atualizações no próprio painel.

---

## 🔑 5. Configuração do Ambiente (.env)

Para rodar o projeto localmente, crie um arquivo `.env` dentro da pasta `backend/` contendo:

```env
# Configurações do Banco de Dados
DATABASE_URL=sqlite:///./test.db # ou postgresql://user:pass@host/db

# Chaves Internas do Sistema
JWT_SECRET=sua_chave_secreta_jwt_para_tokens_usuario
ENCRYPTION_KEY=chave_de_criptografia_para_salvar_as_chaves_no_banco

# Configurações de Servidor
PORT=8000
HOST=0.0.5.0
```

E no `frontend/`, configure se necessário as URLs de comunicação das APIs criando um arquivo `.env`:

```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```
