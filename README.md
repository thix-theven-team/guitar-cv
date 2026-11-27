## Требования

- Python 3.12
- FFmpeg и FFprobe
- Docker и Docker Compose (для запуска в контейнере)
- Веса обученных YOLO-моделей:
  - `hand_model.pt`
  - `pose_model.pt`
  - `guitar_model.pt`

Веса моделей должны находиться в директории `models/`.

## Установка

После клонирования репозитория:

**Windows (PowerShell):**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

**Linux:**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Убедитесь, что FFmpeg и FFprobe доступны через `PATH`:

```bash
ffmpeg -version
ffprobe -version
```

## Конфигурация

Создайте `config.json` на основе шаблона:

```bash
cp config.json.example config.json
```

В Windows:

```powershell
Copy-Item config.json.example config.json
```

При необходимости отредактируйте пути и остальные параметры в `config.json`.

Основные настройки:

| Параметр | Назначение |
|---|---|
| `app_env` | Окружение приложения |
| `debug` | Включение подробного логирования |
| `data_dir` | Директория данных приложения |
| `sqlite_path` | Путь к базе SQLite |
| `upload_dir` | Загруженные видео |
| `result_dir` | Результирующие MIDI-файлы |
| `metadata_dir` | Метаданные ML-пайплайна |
| `temp_dir` | Временные файлы |
| `models_dir` | Веса YOLO-моделей |
| `ml_mock_mode` | Использование mock-реализации вместо ML-моделей |
| `normalize_videos` | Предварительная нормализация видео через FFmpeg |

Все относительные пути разрешаются относительно директории, содержащей `config.json`.

## Запуск ML-пайплайна отдельно

Для проверки ML-части без запуска REST API:

```bash
python -m guitarcv_restapi.cv_test path/to/video.mp4
```

При необходимости можно указать директорию для результатов:

```bash
python -m guitarcv_restapi.cv_test path/to/video.mp4 --output-dir ./data/tmp/cv-test
```

Результаты обработки:

- `annotated.avi` — видео с визуализацией результатов распознавания.
- `frames.jsonl` — информация об обработанных кадрах.
- `summary.json` — итоговые результаты распознавания, включая обнаруженные ноты и их временные интервалы.

## Запуск REST API

Из корневой директории проекта:

```bash
uvicorn guitarcv_restapi.main:app --reload --host 127.0.0.1 --port 8000
```

После запуска документация API доступна по адресам:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

### Проверка обработки видео

Отправьте видео:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/submit-video \
  -F "video=@./path/to/video.mp4"
```

В ответе будет возвращён `conversion-id`.

Проверьте состояние обработки:

```bash
curl http://127.0.0.1:8000/api/v1/conversions/<conversion-id>
```

Возможные состояния:

- `processing` — обработка выполняется.
- `ready` — обработка завершена успешно.
- `failed` — при обработке произошла ошибка.

После завершения обработки скачайте MIDI-файл:

```bash
curl -L \
  http://127.0.0.1:8000/api/v1/conversions/<conversion-id>/result \
  -o output.mid
```

### Запуск без ML-моделей

Для проверки REST API без загруженных весов моделей установите в `config.json`:

```json
"ml_mock_mode": true
```

В этом режиме используется mock-реализация ML-адаптера, возвращающая заранее определённые тестовые ноты.

После проверки верните значение `false`, чтобы использовать настоящие ML-модели.

## Запуск через Docker Compose

Создайте директорию для постоянного хранения данных:

```bash
mkdir -p data
```

На Linux предоставьте пользователю контейнера (UID/GID `10001`) права на запись:

```bash
sudo chown -R 10001:10001 data
```

Соберите образ и запустите приложение:

```bash
docker compose up -d --build
```

Просмотр логов:

```bash
docker compose logs -f api
```

Остановка:

```bash
docker compose down
```

API доступен на `127.0.0.1:4500`. Для доступа извне предполагается использование reverse proxy, например Caddy.

Пример конфигурации Caddy:

```caddy
your-domain.example {
    reverse_proxy 127.0.0.1:4500
}
```

## Тестирование

Запуск тестов:

```bash
pytest
```

Дополнительные проверки:

```bash
flake8 src tests
mypy src
```

Тесты не требуют весов ML-моделей и используют временные директории и тестовые базы данных SQLite.
