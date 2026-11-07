# Развёртывание SpendyHolik backend

Инструкция по развёртыванию на одном сервере с k3s (облегчённый Kubernetes) и
Helm, с автоматическим обновлением из GitHub. Команды с пометкой
«локально» выполняются на вашем компьютере, остальные — на сервере по SSH.

## Как это устроено

```
git push в main ──▶ GitHub Actions: CI (lint, тесты, helm lint)
                        └─▶ CD: сборка образа ──▶ ghcr.io/<owner>/spendyholik-backend:<sha>
                                └─▶ SSH на сервер ──▶ deploy/server-update.sh
                                                        ├─ git checkout коммита
                                                        └─ helm upgrade --atomic
```

В namespace `spendyholik` работают:

| Компонент | Назначение |
|---|---|
| `api` | Django + Gunicorn, REST API |
| `worker` | Celery, фоновые задачи |
| `beat` | Celery beat, задачи по расписанию |
| `postgres` | PostgreSQL 18 (StatefulSet, данные на PVC) |
| `redis` | Redis 8, брокер задач и кэш |
| Job `migrate` | миграции и расписание задач перед каждым обновлением |

Трафик принимает встроенный в k3s Traefik (порт 80, после настройки TLS — 443).
Секреты хранятся только на сервере; в GitHub — лишь SSH-ключ для деплоя.

Этапы:

1. **Запуск по IP через HTTP** — шаги 1–8.
2. **Автообновление** — шаг 9.
3. **Домен и HTTPS** — шаг 12.

## Требования

- Сервер: Ubuntu 22.04/24.04, amd64 или arm64, от 2 vCPU / 4 ГБ RAM / 30 ГБ диска,
  SSH-доступ под пользователем с `sudo`.
- Репозиторий на GitHub (форк этого или свой) с включёнными Actions.

Обозначения: `<server-ip>` — IP сервера, `<user>` — пользователь на сервере,
`<owner>/<repo>` — ваш репозиторий, `<owner>` в адресе образа — владелец
репозитория **в нижнем регистре**.

---

## 1. Первая сборка образа

Сделайте push в ветку `main` своего репозитория (или запустите
**Actions → CD → Run workflow**). После зелёного **CI** workflow **CD** соберёт
образ и опубликует его в GitHub Container Registry. Шаг `deploy` будет
пропущен, пока не настроен сервер (шаг 9).

Сделайте образ публичным, чтобы кластер мог скачать его без авторизации:
**профиль/организация → Packages → `spendyholik-backend` → Package settings →
Change visibility → Public**.

> Сервер на arm64: **Settings → Secrets and variables → Actions → Variables** —
> добавьте `IMAGE_PLATFORMS` = `linux/arm64` (или `linux/amd64,linux/arm64`) и
> перезапустите CD.

---

## 2. Подготовка сервера

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git ufw
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

Порт 6443 (Kubernetes API) наружу не открывайте.

---

## 3. k3s и Helm

```bash
curl -sfL https://get.k3s.io | sh -
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER:$USER ~/.kube/config
echo 'export KUBECONFIG=~/.kube/config' >> ~/.bashrc
source ~/.bashrc
kubectl get nodes
```

```bash
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

---

## 4. Код и настройки сервера

Скрипт обновления ожидает репозиторий в `~/spendyholik_backend`:

```bash
git clone https://github.com/<owner>/<repo>.git ~/spendyholik_backend
cd ~/spendyholik_backend/deploy/charts/spendyholik-backend
cp values-server.example.yaml values-server.yaml
```

В `values-server.yaml` укажите адрес образа и IP сервера:

```yaml
image:
  repository: ghcr.io/<owner>/spendyholik-backend

env:
  ALLOWED_HOSTS: "<server-ip>"
```

`values-server.yaml` в `.gitignore`: обновления кода его не затрагивают.
Остальные параметры по умолчанию — в `values.yaml` и `values-prod.yaml`.

> **Ubuntu 26.04 и новее.** Стандартный AppArmor-профиль containerd там
> запрещает процессам одного контейнера посылать друг другу сигналы:
> PostgreSQL зависает на старте (в `journalctl -k` — `apparmor="DENIED"
> operation="signal"`). Загрузите профиль из репозитория:
>
> ```bash
> sudo install -m 644 ~/spendyholik_backend/deploy/apparmor/spendyholik-container /etc/apparmor.d/
> sudo apparmor_parser -r /etc/apparmor.d/spendyholik-container
> ```
>
> и добавьте в `values-server.yaml` строку `appArmorProfile: spendyholik-container`.
> Файл в `/etc/apparmor.d/` загружается автоматически после перезагрузки.

---

## 5. Секреты

```bash
cd ~/spendyholik_backend/deploy/charts/spendyholik-backend
cat > secrets.yaml <<EOF
secrets:
  SECRET_KEY: "$(openssl rand -hex 50)"
  POSTGRES_PASSWORD: "$(openssl rand -hex 24)"
  REDIS_PASSWORD: "$(openssl rand -hex 24)"
EOF
chmod 600 secrets.yaml
```

- Сохраните файл в надёжном месте. PostgreSQL инициализирует базу с этим
  паролем при первом запуске; при смене пароля приложение не подключится к
  существующей базе.
- Пароли должны состоять из букв и цифр (они подставляются в `DATABASE_URL`).
- `secrets.yaml` в `.gitignore`, не добавляйте его в репозиторий.

---

## 6. Установка

```bash
~/spendyholik_backend/deploy/server-update.sh
```

Скрипт переключает код на последний коммит `main`, ставит чарт с образом
`<sha>` этого коммита и показывает поды. При первой установке создаются база,
таблицы и расписание фоновых задач; это занимает несколько минут.

---

## 7. Проверка

```bash
curl http://<server-ip>/health/
curl http://<server-ip>/ready/
```

Ожидаемые ответы: `{"status":"ok"}` и
`{"status":"ready","checks":{"database":true,"cache":true}}`.
Swagger UI: `http://<server-ip>/api/docs/`.

```bash
curl -X POST http://<server-ip>/api/v1/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"test@example.com","password":"Str0ng-Passw0rd"}'
```

---

## 8. Администратор

```bash
kubectl -n spendyholik exec -it deploy/spendyholik-backend-api -- python manage.py createsuperuser
```

Админка: `http://<server-ip>/admin/`.

---

## 9. Автообновление

Локально создайте отдельный ключ для деплоя и добавьте его на сервер:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/spendyholik_deploy -N "" -C "spendyholik-deploy"
ssh-copy-id -i ~/.ssh/spendyholik_deploy.pub <user>@<server-ip>
ssh -i ~/.ssh/spendyholik_deploy <user>@<server-ip> 'echo ok'
```

В репозитории: **Settings → Secrets and variables → Actions**

| Тип | Имя | Значение |
|---|---|---|
| Secret | `VPS_SSH_KEY` | содержимое приватного ключа `~/.ssh/spendyholik_deploy` целиком |
| Variable | `VPS_HOST` | IP или домен сервера |
| Variable | `VPS_USER` | пользователь на сервере |
| Variable (опц.) | `IMAGE_PLATFORMS` | `linux/arm64` для ARM-серверов |

Проверка: **Actions → CD → Run workflow**, шаг `deploy` должен завершиться успешно.

---

## 10. Обновления и откат

Каждый push в `main` с зелёным CI выкатывается автоматически. Если новая
версия не становится готовой, Helm возвращает предыдущий релиз (`--atomic`), а
workflow CD завершается ошибкой.

Вручную на сервере:

```bash
~/spendyholik_backend/deploy/server-update.sh            # последний main
~/spendyholik_backend/deploy/server-update.sh <sha>      # конкретный коммит
helm -n spendyholik history spendyholik-backend          # история релизов
helm -n spendyholik rollback spendyholik-backend         # предыдущий релиз
```

Откат релиза не отменяет миграции базы: изменения схемы с удалением данных
выкатывайте после резервной копии.

---

## 11. Резервные копии

```bash
mkdir -p ~/backups
kubectl -n spendyholik exec spendyholik-backend-postgres-0 -- pg_dump -U spendyholik -Fc spendyholik \
  > ~/backups/spendyholik-$(date +%F).dump
```

Ежедневный дамп в 04:00 с хранением 14 дней (`crontab -e`):

```
0 4 * * * KUBECONFIG=$HOME/.kube/config /usr/local/bin/kubectl -n spendyholik exec spendyholik-backend-postgres-0 -- pg_dump -U spendyholik -Fc spendyholik > $HOME/backups/spendyholik-$(date +\%F).dump && find $HOME/backups -name '*.dump' -mtime +14 -delete
```

Восстановление:

```bash
kubectl -n spendyholik exec -i spendyholik-backend-postgres-0 -- pg_restore -U spendyholik -d spendyholik --clean --if-exists < ~/backups/<file>.dump
```

Храните копии и вне сервера.

---

## 12. Домен и HTTPS

1. Создайте DNS-запись **A** `api.<domain>` → `<server-ip>`.

2. Установите cert-manager:

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo update
helm install cert-manager jetstack/cert-manager -n cert-manager --create-namespace \
  --set crds.enabled=true --wait
```

3. Создайте ClusterIssuer для Let's Encrypt (укажите свой email):

```bash
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            ingressClassName: traefik
EOF
```

4. Обновите `values-server.yaml`:

```yaml
image:
  repository: ghcr.io/<owner>/spendyholik-backend

ingress:
  host: "api.<domain>"
  tls:
    enabled: true

env:
  ALLOWED_HOSTS: "api.<domain>"
  CSRF_TRUSTED_ORIGINS: "https://api.<domain>"
  CORS_ALLOWED_ORIGINS: "https://app.<domain>"
  SECURE_SSL_REDIRECT: "true"
  SECURE_COOKIES: "true"
  SECURE_HSTS_SECONDS: "31536000"
```

5. Примените и дождитесь сертификата (`READY` = `True`):

```bash
~/spendyholik_backend/deploy/server-update.sh
kubectl -n spendyholik get certificate
```

Включайте HSTS только после того, как HTTPS заработал: браузеры его запоминают.

---

## Параметры чарта

Основное в `deploy/charts/spendyholik-backend/values.yaml`:

| Параметр | По умолчанию | Описание |
|---|---|---|
| `replicaCount` | `1` | реплики api (если `autoscaling.enabled=false`) |
| `autoscaling.enabled` | `false` | HPA для api |
| `postgresql.enabled` | `true` | встроенный PostgreSQL; `false` + `secrets.DATABASE_URL` — внешняя БД |
| `redis.enabled` | `true` | встроенный Redis; `false` + `secrets.REDIS_URL` — внешний Redis |
| `persistence.media.size` | `5Gi` | том для загружаемых файлов |
| `ingress.host` | `""` | домен; пусто — ответ на любой хост/IP |
| `ingress.tls.enabled` | `false` | TLS через cert-manager |
| `env.EMAIL_BACKEND` | console | для отправки почты — `django.core.mail.backends.smtp.EmailBackend` + `EMAIL_HOST`, `EMAIL_HOST_USER`, `secrets.EMAIL_HOST_PASSWORD` |

---

## Диагностика

| Что | Команда |
|---|---|
| Поды | `kubectl -n spendyholik get pods` |
| Логи API | `kubectl -n spendyholik logs deploy/spendyholik-backend-api --tail=100` |
| Логи Celery | `kubectl -n spendyholik logs deploy/spendyholik-backend-worker --tail=100` |
| Логи миграций | `kubectl -n spendyholik logs job/spendyholik-backend-migrate` |
| Причина ошибки пода | `kubectl -n spendyholik describe pod <pod>` |
| События | `kubectl -n spendyholik get events --sort-by=.lastTimestamp` |
| Django shell | `kubectl -n spendyholik exec -it deploy/spendyholik-backend-api -- python manage.py shell` |

| Симптом | Причина |
|---|---|
| `ImagePullBackOff` | образ не публичный, неверный `image.repository` (регистр букв) или CD ещё не собрал образ этого коммита |
| `exec format error` | архитектура образа не совпадает с сервером — задайте `IMAGE_PLATFORMS` |
| CD: `ssh: handshake failed` | неверные `VPS_SSH_KEY` / `VPS_USER` или ключ не добавлен на сервер |
| `Missing .../values-server.yaml`, `secrets.SECRET_KEY is required` | не выполнены шаги 4–5 |
| `/ready/` → 400 | хост запроса не входит в `ALLOWED_HOSTS` |
| Письма не приходят | по умолчанию почта пишется в логи API (`EMAIL_BACKEND` = console) |
