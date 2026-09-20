# Развёртывание расписания EdVille

Коротко: проект готов к публикации. Ниже — что запустить локально и как
выложить сайт в интернет. Подробности о самом расписании — в `README.md`.

## Что уже проверено

- 49 учителей, 14 классов, 596 уроков, 38 предметов, 11 звонков;
- все 49 страниц учителей и все 14 страниц классов открываются (код 200);
- редактор и админка закрыты логином, публичные страницы — открыты;
- `python manage.py check --deploy` — без замечаний;
- 16 автотестов проходят;
- телефон: расписание складывается в карточки, горизонтальной прокрутки нет.

## Локальный запуск

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export DJANGO_SECRET_KEY="$(python -c 'from django.core.management.utils import get_random_secret_key as g; print(g())')"
export DJANGO_DEBUG=True
python manage.py migrate
python manage.py seed_if_empty      # наполнит базу, если она пустая
python manage.py runserver          # только для разработки!
```

## Публикация

Нужен хостинг с **постоянным диском** — иначе база (SQLite) сотрётся при
первом же перезапуске. Готовые конфиги лежат в репозитории.

### Вариант A — Render (`render.yaml`)

Диск доступен на платном плане Starter; на free-плане диска нет и
расписание будет пропадать.

1. Render → New → Blueprint → указать этот репозиторий.
2. Render прочитает `render.yaml` и создаст сервис с диском на `/app/data`.
3. После первого деплоя вписать в Environment:
   - `DJANGO_ALLOWED_HOSTS` = `edville-timetable.onrender.com`
   - `DJANGO_CSRF_TRUSTED_ORIGINS` = `https://edville-timetable.onrender.com`
4. Redeploy. HTTPS Render выдаёт сам.

### Вариант B — Fly.io (`fly.toml`)

```bash
fly launch --no-deploy --copy-config
fly volumes create timetable_data --size 1 --region fra
fly secrets set DJANGO_SECRET_KEY="$(python -c 'from django.core.management.utils import get_random_secret_key as g; print(g())')" \
                DJANGO_ALLOWED_HOSTS=<app>.fly.dev \
                DJANGO_CSRF_TRUSTED_ORIGINS=https://<app>.fly.dev
fly deploy
```

### Учётная запись завуча

Создаётся один раз, уже после деплоя, и только через консоль хостинга:

```bash
python manage.py createsuperuser
```

Пароли в коде и в репозитории не хранятся — никогда не добавляй их в файлы.

## Проверка после деплоя

```bash
curl -I https://<домен>/                      # 200
curl -I https://<домен>/class/9a/             # 200
curl -I https://<домен>/teacher/nurgaisha-kalikova/   # 200
curl -I https://<домен>/editor/               # 302 -> /login/
```

Затем перезапустить сервис и снова открыть страницу учителя — расписание
должно остаться на месте. Это и есть проверка постоянного диска.

## Резервная копия расписания

```bash
python manage.py dumpdata schedule --indent 1 --output backup-$(date +%F).json
```

Файл сохранится вне репозитория (папка `backups/` и `*.json`-дампы в
`.gitignore` не попадают в git — храни копию отдельно).

Восстановление:

```bash
python manage.py loaddata backup-2026-09-20.json
```

## Обновление сайта

```bash
git add -A && git commit -m "..." && git push
```

Render и Fly пересобирают приложение сами. При старте выполняется
`migrate` → `seed_if_empty` → `collectstatic`. `seed_if_empty` наполняет
**только пустую** базу, поэтому редеплой не затирает расписание.

## Чего делать нельзя

- запускать `runserver` как публичный сервер;
- разворачивать SQLite на диске без постоянного тома;
- коммитить `.env`, `db.sqlite3` и файлы `*.xlsx` (они в `.gitignore`);
- запускать `generate_schedule` / `import_*` на боевой базе без бэкапа —
  эти команды пересобирают расписание.
