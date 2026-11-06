# API Python com CI/CD para Amazon EC2

API de tarefas escrita em Python (FastAPI) usada para demonstrar uma esteira completa de integração e entrega contínua: cada alteração passa por Pull Request e testes automatizados, e cada merge na `main` gera uma nova imagem Docker, publicada no Amazon ECR e implantada automaticamente em uma instância Amazon EC2.

**Fluxo:** alteração no código → branch → Pull Request → testes automatizados → merge na `main` → build Docker → publicação no ECR → deploy na EC2 → aplicação atualizada.

## Tecnologias utilizadas

| Ferramenta | Uso |
|---|---|
| Python 3.13 + FastAPI + Uvicorn | API HTTP |
| pytest, pytest-cov, Ruff | testes, cobertura e análise estática |
| Docker | empacotamento e execução da aplicação |
| GitHub Actions | pipelines de CI (`ci.yml`) e CD (`deploy.yml`) |
| Amazon ECR | registry privado das imagens |
| Amazon EC2 (Ubuntu) | servidor que executa o contêiner |
| AWS IAM (LabInstanceProfile) | permissão da EC2 para ler o ECR |

## Estrutura do repositório

```text
.
├── .github/workflows/
│   ├── ci.yml              # valida Pull Requests para a main
│   └── deploy.yml          # testa, publica no ECR e implanta na EC2 após merge
├── app/
│   ├── __init__.py
│   └── main.py             # API FastAPI
├── scripts/
│   └── deploy-ec2.sh       # comandos executados na EC2 durante o deploy
├── tests/test_api.py       # testes automatizados
├── docs/                   # material de apoio da disciplina
├── .dockerignore
├── .python-version
├── compose.yaml
├── Dockerfile
├── pyproject.toml          # configuração do pytest, cobertura e Ruff
├── requirements.txt        # dependências de execução
└── requirements-dev.txt    # dependências de desenvolvimento e CI
```

## Endpoints

| Método | Caminho | Objetivo | Resposta |
|---|---|---|---|
| GET | `/` | Apresentar a API | `200` |
| GET | `/health` | Saúde, versão e commit implantado | `200` |
| GET | `/tasks` | Listar tarefas | `200` |
| POST | `/tasks` | Criar uma tarefa | `201` |
| PATCH | `/tasks/{id}/done` | Concluir uma tarefa | `200` ou `404` |
| GET | `/docs` | Documentação Swagger | `200` |

## Execução local

Pré-requisitos: Git e Python 3.13.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements-dev.txt
uvicorn app.main:app --reload
```

Acesse <http://localhost:8000/health> e <http://localhost:8000/docs>.

Verificações (as mesmas executadas pelo GitHub Actions):

```bash
ruff check .
ruff format --check .
pytest --cov=app --cov-report=term-missing
```

## Docker

Construir a imagem, informando o commit que será exibido em `/health`:

```bash
docker build --build-arg GIT_SHA=$(git rev-parse HEAD) -t devops-python-api:local .
```

Executar o contêiner e testar:

```bash
docker run --rm -d -p 8000:8000 --name devops-python-api devops-python-api:local
curl http://localhost:8000/health
docker logs devops-python-api
docker rm -f devops-python-api
```

O `Dockerfile` instala as dependências de `requirements.txt` durante o build, roda a aplicação com um usuário sem privilégios, expõe a porta `8000` e define um `HEALTHCHECK` em `/health`.

## Pipeline de integração contínua (`ci.yml`)

Acionada na abertura ou atualização de um Pull Request para a `main` (e manualmente pela aba **Actions**).

1. **Qualidade e testes:** baixa o código, configura o Python, instala as dependências, executa `ruff check`, `ruff format --check` e `pytest` com cobertura mínima de 90%, e guarda os relatórios como artefato.
2. **Build e teste do container:** só roda se o job anterior passou (`needs`). Constrói a imagem, inicia o contêiner e consulta `/health`.

O resultado aparece no próprio Pull Request: verde quando tudo passa, vermelho indicando o step que falhou.

## Pipeline de entrega contínua (`deploy.yml`)

Acionada a cada push na `main`, ou seja, após o merge de um Pull Request. Os jobs são encadeados com `needs`, então **nada é publicado ou implantado se os testes falharem**.

1. **Testes automatizados:** executa novamente o `pytest`.
2. **Build e publicação no ECR:** autentica na AWS com credenciais guardadas em GitHub Secrets, faz login no ECR, constrói a imagem com a tag igual ao SHA do commit e a envia ao repositório `devops-python-api`.
3. **Deploy na EC2:**
   - libera a porta 22 no Security Group **somente para o IP do runner** daquela execução;
   - conecta por SSH na instância e executa [`scripts/deploy-ec2.sh`](scripts/deploy-ec2.sh), que autentica o Docker da EC2 no ECR usando a IAM Role da instância, baixa a imagem do commit, remove o contêiner anterior, inicia o novo e verifica `/health`;
   - consulta `http://<EC2>/health` de fora e confere se o commit publicado é o do merge;
   - remove a liberação da porta 22, mesmo se algum passo falhar.

Nenhum `docker pull` ou `docker run` é executado manualmente na instância.

## Arquitetura de implantação

```text
 Desenvolvedor ──push──▶ GitHub (branch) ──Pull Request──▶ ci.yml (testes)
                                                │
                                              merge
                                                ▼
                                   GitHub Actions: deploy.yml
                         testes ──▶ docker build ──▶ docker push ──▶ Amazon ECR
                                                                        │
                                  SSH (IP do runner liberado no SG)     │ docker pull
                                                ▼                       │ (IAM Role)
                                  Amazon EC2 (Ubuntu + Docker) ◀────────┘
                                  contêiner devops-python-api  porta 80 → 8000
                                                │
                                                ▼
                                   Usuário: http://<IP-PÚBLICO>/health
```

## Configuração da AWS e do GitHub

### AWS (AWS Academy Learner Lab, região `us-east-1`)

1. **ECR:** repositório privado `devops-python-api`.
2. **EC2:** Ubuntu Server, `t3.micro`, IAM instance profile `LabInstanceProfile` (permite ler o ECR sem guardar chaves na instância).
3. **Security Group da EC2:**
   - SSH (22) apenas para o IP do administrador; o pipeline libera temporariamente o IP do runner;
   - HTTP (80) liberado para acesso à API.
4. **Preparação da instância** (executada uma única vez):

   ```bash
   sudo apt update && sudo apt install -y docker.io curl
   sudo snap install aws-cli --classic
   sudo systemctl enable --now docker
   ```

### GitHub Secrets (Settings → Secrets and variables → Actions)

| Secret | Conteúdo |
|---|---|
| `AWS_ACCESS_KEY_ID` | credencial temporária do Learner Lab |
| `AWS_SECRET_ACCESS_KEY` | credencial temporária do Learner Lab |
| `AWS_SESSION_TOKEN` | token de sessão do Learner Lab |
| `EC2_HOST` | IP público da instância |
| `EC2_SSH_KEY` | conteúdo da chave privada `.pem` da instância |
| `EC2_SECURITY_GROUP_ID` | ID do Security Group da instância |

As credenciais do Learner Lab expiram ao final de cada sessão do laboratório; antes de cada deploy, atualize os três secrets da AWS com os valores de **AWS Details**. Nenhuma credencial é gravada no código ou no README.

## Acesso à API publicada

- Saúde e versão: `http://<IP-PÚBLICO-DA-EC2>/health`
- Swagger: `http://<IP-PÚBLICO-DA-EC2>/docs`

> O IP público muda quando a instância é parada e iniciada novamente.

## Como verificar a versão implantada

```bash
curl http://<IP-PÚBLICO-DA-EC2>/health
```

Resposta esperada:

```json
{"status": "ok", "version": "1.0.0", "commit": "<SHA do último merge na main>"}
```

- `version` muda quando a aplicação é alterada (ex.: `1.0.0` → `1.1.0`).
- `commit` deve ser igual ao SHA do último commit da `main` e à tag da imagem no ECR.
- Na EC2: `sudo docker ps` mostra a imagem `...devops-python-api:<SHA>` em execução.

## Evidências

As capturas de tela ficam em [`docs/evidencias/`](docs/evidencias/).

| Evidência | Arquivo |
|---|---|
| CI executado com sucesso no Pull Request | `docs/evidencias/01-ci-pr.png` |
| Imagem publicada no ECR com a tag do commit | `docs/evidencias/02-ecr.png` |
| Pipeline de deploy concluída | `docs/evidencias/03-deploy.png` |
| Contêiner em execução na EC2 (`docker ps`) | `docs/evidencias/04-docker-ps.png` |
| API acessível no navegador — versão 1 | `docs/evidencias/05-api-v1.png` |
| API acessível no navegador — versão 2 (deploy automático) | `docs/evidencias/06-api-v2.png` |

### Pull Requests

- PR 1 — implementação da esteira CI/CD: _link_
- PR 2 — atualização da versão (demonstração do deploy automático): _link_

## Encerramento dos recursos

Após a avaliação: parar ou encerrar a instância EC2 e excluir as imagens e o repositório do ECR, evitando cobranças.
