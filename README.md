# Kimi Chat CLI

Единый скрипт для общения с Kimi AI через API (Connect Protocol over HTTP/2).

## Установка

```bash
chmod +x kimi_chat.sh
```

## Настройка токена

Откройте `kimi_chat.sh` и вставьте JWT-токен в переменную `TOKEN`:

```bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

Токен можно получить в настройках аккаунта Kimi (DevTools → Network → запрос к kimi.com → Cookie/Authorization).

## Использование

```bash
# Сообщение
./kimi_chat.sh "Текст сообщения"

# Новый чат
./kimi_chat.sh --new "Привет!"

# С файлом
./kimi_chat.sh --file script.py "Аудит кода"
```

## Флаги

| Флаг | Описание |
|------|----------|
| `--new` | Новый чат |
| `--file PATH` | Прикрепить файл |
| `--computer` | SCENARIO_OK_COMPUTER |
| `--no-thinking` | Отключить thinking |
| `--no-plugin` | Отключить плагины |
| `--effort-{low,medium,high}` | Уровень reasoning |

## Публикация на GitHub

**Загрузить:** `kimi_chat.sh`, `README.md`, `.gitignore`

**Исключено (`.gitignore`):** `kimi_state.json`, `__pycache__/`, `pentest_agent/`, `*.pyc`

## ⚠️ Безопасность

Не публикуйте токен в `kimi_chat.sh`. При утечке перегенерируйте его в настройках аккаунта.