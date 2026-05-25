# Registro de Alterações e Guia de Manutenção (Changelog & Maintenance Guide)

Este documento detalha o histórico de alterações, a arquitetura do projeto por diretórios e as diretrizes de manutenção do sistema **Antigravity**. Use este guia para facilitar a integração de novos desenvolvedores e guiar futuras manutenções.

---

## 📅 Histórico de Alterações (Changelog)

### **25 de Maio de 2026**
#### **1. Responsividade Mobile & Tradução Completa (PT-BR)**
* **Tradução Geral**: Traduzidos todos os botões, mensagens de erro, placeholders de formulários, colunas de tabelas, tags e modais de todas as páginas do frontend para o Português.
* **Componente de Tooltip Interativo**: Criação do componente `InfoTooltip` em [Dashboard.jsx](file:///C:/Users/Caio.Vicente/scratch/busy-hopper/frontend/src/pages/Dashboard.jsx) usando classes nativas do Tailwind para exibir explicações explicativas do que cada seção ou KPI faz ao passar o mouse (*hover*).
* **Responsividade Mobile**:
  * O menu lateral em [Layout.jsx](file:///C:/Users/Caio.Vicente/scratch/busy-hopper/frontend/src/components/Layout.jsx) agora se contrai e vira uma gaveta mobile acessível por um botão de hambúrguer com efeito de desfoque de fundo (*backdrop blur*).
  * Todos os grids e containers gráficos do Recharts adaptam-se dinamicamente ao tamanho da tela (`grid-cols-1`).
  * As tabelas foram envolvidas em classes `overflow-x-auto` para evitar quebras em telas estreitas.

#### **2. Importação de Agentes OpenClaw**
* **Funcionalidade**: Integração da capacidade de importar configurações no formato `openclaw.json` diretamente para a árvore corporativa da empresa.
* **Backend**: Criação da rota `POST /api/v1/agents/import-openclaw` em [agents.py](file:///C:/Users/Caio.Vicente/scratch/busy-hopper/backend/app/api/agents.py) mapeando prompts, modelos, limites de orçamento e traduzindo ferramentas do OpenClaw (`shell`, `web`, `file`, etc.) para as ferramentas do sistema local.
* **Frontend**: Adicionado o modal de importação com colar-texto em [OrgChart.jsx](file:///C:/Users/Caio.Vicente/scratch/busy-hopper/frontend/src/pages/OrgChart.jsx).

#### **3. Integração Real com a API do Meta Ads**
* **Funcionalidade**: Substituição das simulações de campanhas por chamadas reais à Graph API do Meta (v20.0).
* **Backend**: Modificado o módulo [meta.py](file:///C:/Users/Caio.Vicente/scratch/busy-hopper/backend/app/api/meta.py) para buscar dados dinâmicos (`GET /act_{ad_account_id}/campaigns`) direto do Meta Graph SDK/HTTP Client, calculando ROAS real, CTR, impressões e saúde de forma dinâmica.
* **Executor de Agentes**: O executor [agent_executor.py](file:///C:/Users/Caio.Vicente/scratch/busy-hopper/backend/app/services/agent_executor.py) agora cria campanhas reais de anúncios caso as credenciais estejam ativas.

#### **4. Auditoria de Código e Correções ESLint**
* **Correções**: Varredura completa para eliminar variáveis não utilizadas, imports duplicados, e reordenamento de funções e efeitos (`useEffect` e `useCallback`) para prevenir avisos de hoisting e mutabilidade de estados de efeito no React.
* **Resultados**: 0 avisos e 0 erros no comando `npm run lint`.

---

### **Alterações Anteriores**
* **Suporte Multi-Model & AWS Bedrock**: Integração da compatibilidade do backend com OpenAI, Google Gemini, OpenRouter e AWS Bedrock. Criação de endpoint para teste dinâmico de conexões de chaves de API em `/api/v1/credentials/validate`.
* **Redesenho Visual Premium (Black & Orange)**: Redesenho total do layout do frontend utilizando paleta de cores HSL escuras (charcoal/deep space) e acentuações em laranja neon com brilhos interativos (*neon glow*).
* **Tabela de Consumo de Tokens por Tarefa**: Agregação de custos e consumo total de tokens das LLMs diretamente na tabela principal do Dashboard.
* **Habilitação de Contratação Dinâmica (`hire_agent`)**: Criação da ferramenta delegada a agentes gestores (ex: CEO) para contratarem subordinados programáticos sob aprovação humana (*human-in-the-loop*).

---

## 📂 Estrutura de Pastas e Componentes (Arquitetura)

```text
busy-hopper/
├── backend/
│   ├── app/
│   │   ├── api/            # Endpoints HTTP da API (FastAPI)
│   │   │   ├── agents.py       # Gerenciamento e importação de Agentes
│   │   │   ├── dashboard.py    # Agregações de KPIs, custos e tokens
│   │   │   └── meta.py         # Integrações de APIs do Meta Ads
│   │   ├── core/           # Configurações globais e schemas Pydantic
│   │   ├── models/         # Modelos SQLAlchemy de banco de dados
│   │   └── services/       # Motores de execução de Agentes e utilitários
│   │       └── agent_executor.py # Runtime de execução e chamada de LLMs
│   └── tests/              # Testes unitários automatizados (pytest)
│
└── frontend/
    ├── src/
    │   ├── components/     # Componentes React globais
    │   │   └── Layout.jsx      # Layout do app (Sidebar, Header, Gaveta Mobile)
    │   ├── pages/          # Páginas principais da Aplicação
    │   │   ├── Dashboard.jsx   # Gráficos, KPIs, tooltips e consumo
    │   │   ├── OrgChart.jsx    # Árvore da organização e modal OpenClaw
    │   │   ├── Tasks.jsx       # Fila de tarefas kanban
    │   │   ├── Approvals.jsx   # Gestão de aprovações (Contratos/Meta Ads)
    │   │   ├── MetaAds.jsx     # Gestor de campanhas reais do Facebook
    │   │   └── Settings.jsx    # Credenciais das APIs (OpenAI/AWS Bedrock)
    │   ├── services/       # Métodos de integração com o Backend (Axios)
    │   └── index.css       # Folha de estilo global e variáveis Tailwind v4
```

---

## 🔧 Guia de Manutenção e Testes

### **Requisitos do Sistema**
* **Node.js**: >= 18.0
* **Python**: >= 3.10
* **PostgreSQL** ou SQLite local (conforme ambiente configurado no `.env`).

---

### **1. Backend (Python/FastAPI)**

#### **Instalar dependências**
```bash
pip install -r backend/requirements.txt
```

#### **Executar Testes Unitários**
Todos os fluxos cruciais (como a importação de agentes OpenClaw e a lógica de validação de credenciais) possuem testes unitários mockados.
```bash
pytest backend/tests/
```
> 💡 **Nota**: Certifique-se de rodar este comando antes de enviar novas modificações de rotas.

---

### **2. Frontend (React/Vite/Tailwind v4)**

#### **Instalar dependências**
```bash
cd frontend
npm install
```

#### **Executar em modo de Desenvolvimento**
Inicia o servidor Vite local:
```bash
npm run dev
```

#### **Auditar Linter (ESLint)**
Utilize para garantir a conformidade de imports e evitar avisos de tags:
```bash
npm run lint
```

#### **Compilar para Produção**
Gera os arquivos estáticos minificados na pasta `dist/`:
```bash
npm run build
```

---

## 💡 Diretrizes para Futuras Alterações

1. **Novos Tooltips**:
   Sempre que adicionar uma nova seção com dados estatísticos ou controle de formulário complexo, utilize o componente `<InfoTooltip text="descrição clara do comportamento" />` importado de `Dashboard.jsx` ou recrie-o para manter a consistência de design (borda laranja neon, fundo carvão e comportamento com hover).
2. **Estilização e Cores**:
   Evite utilizar cores inline ad-hoc. Toda a paleta premium do projeto está mapeada no [index.css](file:///C:/Users/Caio.Vicente/scratch/busy-hopper/frontend/src/index.css) (ex: `text-brand-primary`, `bg-dark-card`, `border-dark-border`).
3. **Internacionalização (Idiomas)**:
   Mantenha todos os novos botões, alertas e modais escritos em **Português**, seguindo a padronização implementada nas telas de login e organização.
