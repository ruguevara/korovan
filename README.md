# КОРОВАН 🐄

Одностраничный мемный сайт: та самая копипаста Кирилла про игру + живой счётчик,
сколько он уже ждёт эту игру (отсчёт с **26 ноября 1999 года**).

Всё в одном файле — `index.html` (стили и скрипт инлайн, без сборки и зависимостей).

## Локальный просмотр

Просто откройте `index.html` в браузере, либо:

```sh
python3 -m http.server 8000
# → http://localhost:8000
```

## Деплой на GitHub Pages

1. Создать репозиторий и запушить файлы:
   ```sh
   git init && git add -A && git commit -m "КОРОВАН"
   git branch -M main
   git remote add origin git@github.com:<USER>/<REPO>.git
   git push -u origin main
   ```
2. В репозитории: **Settings → Pages → Build and deployment → Source: Deploy from a branch**,
   ветка `main`, папка `/ (root)`.

## Свой домен через Cloudflare

1. Указать домен в файле `CNAME` (одна строка, например `korovan.example.com`).
2. В GitHub **Settings → Pages → Custom domain** ввести тот же домен.
3. В Cloudflare DNS:
   - **Apex-домен** (`example.com`): `A`-записи на IP GitHub Pages —
     `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`.
   - **Поддомен** (`korovan.example.com`): `CNAME` → `<USER>.github.io`.
   - Proxy (оранжевое облако) можно оставить включённым; SSL/TLS → **Full**.
4. В GitHub Pages дождаться выдачи сертификата и включить **Enforce HTTPS**.

> `.nojekyll` отключает обработку Jekyll — статика отдаётся как есть.
