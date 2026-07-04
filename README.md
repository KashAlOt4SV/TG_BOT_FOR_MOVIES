# Бот «Что посмотреть»

Telegram-бот для совместного выбора фильмов, сериалов и аниме с друзьями и близкими.

## Возможности

- **Группы** — объединение по @username с подтверждением приглашений
- **Предложения** — добавление названий с голосованием всех участников
- **Случайный выбор** — «Что посмотреть сегодня» из очереди
- **Текущий просмотр** — что смотрим сейчас
- **Завершение** — отметка просмотренного (исключается из рандома)
- **Списки** — очередь, текущий, просмотренное

## Быстрый старт (локально)

### 1. Создайте бота в Telegram

1. Откройте [@BotFather](https://t.me/BotFather)
2. Отправьте `/newbot` и следуйте инструкциям
3. Скопируйте токен

### 2. Настройка

```bash
cd tg_for_movie
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # Linux
```

Отредактируйте `.env`:

```env
BOT_TOKEN=123456:ABC-DEF...
DATABASE_PATH=data/bot.db
```

### 3. Запуск

```bash
python -m bot.main
```

Или:

```bash
python run.py
```

## Деплой на VPS

Ниже — пошаговая инструкция для Ubuntu/Debian VPS.

### Вариант A: Docker (рекомендуется)

**На VPS:**

```bash
# Установка Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Перелогиньтесь или: newgrp docker

# Клонирование проекта
git clone <ваш-репозиторий> tg_for_movie
cd tg_for_movie

# Настройка
cp .env.example .env
nano .env   # вставьте BOT_TOKEN

# Запуск
docker compose up -d --build

# Логи
docker compose logs -f bot
```

База SQLite сохраняется в папке `./data` на хосте.

**Обновление:**

```bash
git pull
docker compose up -d --build
```

### Вариант B: systemd без Docker

```bash
sudo apt update && sudo apt install -y python3 python3-venv git

git clone <ваш-репозиторий> /opt/tg_for_movie
cd /opt/tg_for_movie

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env   # BOT_TOKEN=...

mkdir -p data
```

Создайте сервис `/etc/systemd/system/tg-movie-bot.service`:

```ini
[Unit]
Description=Telegram Movie Bot
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/tg_for_movie
EnvironmentFile=/opt/tg_for_movie/.env
ExecStart=/opt/tg_for_movie/.venv/bin/python -m bot.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo chown -R www-data:www-data /opt/tg_for_movie
sudo systemctl daemon-reload
sudo systemctl enable tg-movie-bot
sudo systemctl start tg-movie-bot
sudo systemctl status tg-movie-bot
```

## Как пользоваться

1. Все участники пишут боту `/start`
2. Один создаёт группу: «🤝 Создать группу» → `@wife @friend`
3. Остальные принимают приглашение
4. «➕ Предложить фильм» → название → все соглашаются
5. «🎬 Что посмотреть сегодня» → случайный выбор
6. «✅ Отметить просмотренным» → после просмотра

## Структура проекта

```
tg_for_movie/
├── bot/
│   ├── main.py           # Точка входа
│   ├── config.py         # Конфигурация
│   ├── database.py       # Схема SQLite
│   ├── keyboards.py      # Клавиатуры
│   ├── handlers/         # Обработчики команд
│   └── services/         # Работа с БД
├── data/                 # База данных (создаётся автоматически)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Переменные окружения

| Переменная       | Описание                          |
|------------------|-----------------------------------|
| `BOT_TOKEN`      | Токен от @BotFather (обязательно) |
| `DATABASE_PATH`  | Путь к SQLite (по умолчанию `data/bot.db`) |

## Примечания

- Бот находит пользователей только по @username после их `/start`
- Группа создаётся, когда **все** приглашённые принимают приглашение
- Фильм добавляется, когда **все остальные** участники согласны с предложением
- Одновременно может быть только один «текущий» фильм в группе
