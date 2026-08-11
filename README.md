# Kimi Chat CLI

Единый Python-скрипт для общения с Kimi AI через API (Connect Protocol over HTTP/2).

## Установка

```bash
chmod +x kimi_chat.py
```

## Настройка токена

Откройте `kimi_chat.py` и вставьте JWT-токен в переменную `TOKEN`:

```python
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

Токен можно получить в настройках аккаунта Kimi (DevTools → Network → Cookie/Authorization).

## Использование

```bash
# Сообщение
python3 kimi_chat.py "Текст сообщения"

# Новый чат
python3 kimi_chat.py --new "Привет!"

# С файлом
python3 kimi_chat.py --file script.py "Аудит кода"
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

## ⚠️ Безопасность

Не публикуйте токен в `kimi_chat.py`. При утечке перегенерируйте его в настройках аккаунта.
