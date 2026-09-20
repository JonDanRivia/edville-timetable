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

### Вариант C — PythonAnywhere (бесплатный план Beginner)

Диск на бесплатном плане PythonAnywhere — постоянный (в отличие от Render
free), поэтому SQLite не нужен отдельный платный том. Подходит, если нужен
нулевой бюджет без карты.

1. Зарегистрироваться на www.pythonanywhere.com (план **Beginner**, бесплатно).
2. Открыть вкладку **Consoles** → **Bash** и выполнить:
   ```bash
   git clone https://github.com/JonDanRivia/edville-timetable.git
   cd edville-timetable
   git checkout claude/wonderful-franklin-0mqynu
   mkvirtualenv --python=/usr/bin/python3.12 edville-venv
   pip install -r requirements.txt
   python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
   ```
   Скопировать сгенерированный ключ — он понадобится в WSGI-файле (шаг 5).
3. Вкладка **Web** → **Add a new web app** → **Manual configuration** →
   выбрать ту же версию Python, что и в virtualenv (3.12).
4. В разделе **Virtualenv** указать путь: `/home/<username>/.virtualenvs/edville-venv`
5. Открыть **WSGI configuration file** (ссылка в разделе Code) и заменить
   содержимое на:
   ```python
   import os
   import sys

   path = '/home/<username>/edville-timetable'
   if path not in sys.path:
       sys.path.insert(0, path)

   os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
   os.environ['DJANGO_SECRET_KEY'] = '<ключ из шага 2>'
   os.environ['DJANGO_DEBUG'] = 'False'
   os.environ['DJANGO_ALLOWED_HOSTS'] = '<username>.pythonanywhere.com'
   os.environ['DJANGO_CSRF_TRUSTED_ORIGINS'] = 'https://<username>.pythonanywhere.com'

   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```
   (заменить `<username>` везде на реальный логин PythonAnywhere).
6. В разделе **Static files** вкладки Web добавить: URL `/static/`,
   Directory `/home/<username>/edville-timetable/staticfiles`.
7. Вернуться в Bash-консоль и выполнить:
   ```bash
   python manage.py migrate --noinput
   python manage.py seed_if_empty
   python manage.py collectstatic --noinput
   ```
8. Нажать зелёную кнопку **Reload** на вкладке Web.
9. Сайт будет доступен по адресу `https://<username>.pythonanywhere.com/` —
   HTTPS уже включён.

Обновление после `git push`: в Bash-консоли `git pull`, затем при
необходимости повторить `migrate`/`collectstatic`, и снова **Reload**
(seed_if_empty существующие данные не тронет).

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
