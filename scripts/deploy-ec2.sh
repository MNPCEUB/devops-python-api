#!/usr/bin/env bash
# Executado na instância EC2 pelo workflow deploy.yml, via SSH.
# As credenciais do ECR vêm da IAM Role da instância (LabInstanceProfile),
# então nenhuma chave da AWS chega até o servidor.
set -euo pipefail

: "${IMAGE:?informe a imagem completa, com tag}"
: "${REGISTRY:?informe o endereço do registry ECR}"
: "${AWS_REGION:?informe a região da AWS}"
: "${CONTAINER_NAME:?informe o nome do contêiner}"
: "${APP_PORT:?informe a porta HTTP publicada}"

echo "==> Autenticando o Docker da instância no Amazon ECR"
aws ecr get-login-password --region "$AWS_REGION" \
  | sudo docker login --username AWS --password-stdin "$REGISTRY"

echo "==> Baixando a imagem $IMAGE"
sudo docker pull "$IMAGE"

echo "==> Substituindo o contêiner anterior"
sudo docker rm --force "$CONTAINER_NAME" 2>/dev/null || true
sudo docker run \
  --detach \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  --publish "$APP_PORT:8000" \
  "$IMAGE"

echo "==> Verificando se o contêiner está em execução"
for attempt in $(seq 1 20); do
  if curl --fail --silent "http://127.0.0.1:$APP_PORT/health"; then
    echo
    sudo docker ps --filter "name=$CONTAINER_NAME"
    # O disco da instância é pequeno: remove imagens antigas que nenhum contêiner usa.
    sudo docker image prune --all --force >/dev/null
    exit 0
  fi
  echo "Tentativa ${attempt}: API ainda não respondeu"
  sleep 2
done

echo "A API não respondeu a tempo. Logs do contêiner:"
sudo docker logs "$CONTAINER_NAME"
exit 1
