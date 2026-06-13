# КОРОВАН

Одностраничный мемный сайт: та самая копипаста Кирилла про игру + живой счётчик,
сколько он уже ждёт эту игру (отсчёт с **26 ноября 1999 года**).

Всё в одном файле — `index.html` (стили и скрипт инлайн, без сборки и зависимостей).

- Репозиторий: <https://github.com/ruguevara/korovan>
- GitHub Pages: <https://ruguevara.github.io/korovan/>
- Основной домен: <https://korovan.ru>
- Зеркало (редирект): <https://kopobah.ru> → `korovan.ru`

## Локальный просмотр

Просто откройте `index.html` в браузере, либо:

```sh
python3 -m http.server 8000
# → http://localhost:8000
```

## Деплой

Сайт публикуется через **GitHub Pages** из ветки `main`, папка `/` (root).
Pages уже включены, домен задан в файле `CNAME`. Любой `git push` в `main`
пересобирает и публикует сайт автоматически:

```sh
git add -A && git commit -m "..." && git push
```

## Домены через Cloudflare

GitHub Pages поддерживает только **один** кастомный домен на репозиторий — он
лежит в файле `CNAME` (сейчас `korovan.ru`). Второй домен `kopobah.ru`
(«korovan» в русской раскладке) настроен как редирект на основной.

### korovan.ru — основной сайт (apex)

Cloudflare DNS для **korovan.ru**:

| Тип   | Имя   | Значение               |
|-------|-------|------------------------|
| A     | `@`   | `185.199.108.153`      |
| A     | `@`   | `185.199.109.153`      |
| A     | `@`   | `185.199.110.153`      |
| A     | `@`   | `185.199.111.153`      |
| CNAME | `www` | `ruguevara.github.io`  |

SSL/TLS → **Full** (не Flexible — иначе цикл редиректов с Pages).

### kopobah.ru — редирект на korovan.ru

1. DNS для **kopobah.ru** — проксируемые записи-заглушки (оранжевое облако),
   чтобы Cloudflare перехватывал трафик:

   | Тип | Имя   | Значение      | Proxy     |
   |-----|-------|---------------|-----------|
   | A   | `@`   | `192.0.2.1`   | Proxied   |
   | A   | `www` | `192.0.2.1`   | Proxied   |

2. **Redirect Rule** (Rules → Redirect Rules):
   - When: Hostname `contains` `kopobah.ru`
   - Then: Dynamic redirect, выражение
     `concat("https://korovan.ru", http.request.uri.path)`
   - Код **301**, «Preserve query string» включить.

### После прогона DNS

GitHub сам выпустит TLS-сертификат для `korovan.ru`, затем включаем HTTPS:

```sh
gh api -X PUT repos/ruguevara/korovan/pages -f https_enforced=true
```

> `.nojekyll` отключает обработку Jekyll — статика отдаётся как есть.
