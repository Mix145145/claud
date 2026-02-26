# Claud / Tuposcan

## Что это за проект
`claud` — это модульный Python-проект для автоматизированной съёмки области по сетке (grid scan) с помощью камеры и перемещаемого механизма (Marlin/CNC), с последующей подготовкой данных для сшивки панорамы. Центральный объект — `TuposcanEngine`, который объединяет:

- камеру (Picamera2 / V4L2 / GStreamer / Stub),
- последовательное подключение к Marlin (реальное или stub),
- калибровку поля зрения (FOV) по маркерам,
- расчёт сетки кадров и управление сканированием,
- оценку времени выполнения,
- публикацию событий через EventBus для GUI/Web-слоя.

Проект **не требует `.env` или переменных окружения для запуска**. Наоборот, для корректной работы камеры на Raspberry Pi важно запускать приложение в обычной системе с доступом к устройствам (`/dev/video*`, libcamera/picamera2), а не через изолированный сценарий с “ENV-only” конфигурацией.

---

## Ключевые возможности

- **Автовыбор backend камеры**: при `AUTO` используется цепочка `Picamera2 → V4L2 → GStreamer → Stub`.
- **Работа с Marlin**:
  - реальное подключение через `pyserial`,
  - fallback в `StubMarlinConnection`, если реальный порт недоступен.
- **Безопасность движения** (`SafetyGuard`):
  - проверка диапазонов X/Y/Z,
  - обязательный home перед движением,
  - emergency stop.
- **Калибровка FOV**:
  - поиск ArUco/AprilTag маркеров,
  - вычисление `mm_per_px`, `fov_x_mm`, `fov_y_mm`,
  - сохранение профилей в JSON.
- **Сканирование по сетке**:
  - расчёт покрытия с учётом overlap,
  - snake-паттерн обхода для сокращения перемещений,
  - пауза/продолжение/остановка,
  - возобновление незавершённого проекта.
- **Артефакты сканирования**:
  - структура проекта `frames/`, `stitched/`, `logs/`,
  - `shots.json` со статусами кадров,
  - `config_snapshot.json`.
- **Сшивка (готовые backend'ы)**:
  - feather blend,
  - multiband blend,
  - ECC refinement,
  - OpenCV fallback.
- **Поток превью MJPEG** для UI.

---

## Архитектура проекта

```text
config/       -> схема и менеджер конфигурации
engine/       -> основной оркестратор (TuposcanEngine), state machine, события
camera/       -> backend'ы камеры + MJPEG stream
serial_com/   -> абстракция и реализации связи с Marlin + safety
calibration/  -> детектор маркеров, калибровка FOV, хранилище профилей
scanner/      -> расчёт сетки, сессия съёмки, проект и манифест
stitcher/     -> алгоритмы сшивки
utils/        -> логирование, обработка изображений, вспомогательные утилиты
```

---

## Как это работает (поток выполнения)

1. Загружается конфиг (`ConfigManager`), при отсутствии файла используются defaults.
2. `TuposcanEngine.initialize()`:
   - поднимает камеру,
   - подключает serial,
   - инициализирует safety,
   - загружает FOV profiles,
   - готовит калибратор.
3. Перед сканированием выполняется (или заранее должна быть выполнена) калибровка для нужных `Z + resolution`.
4. При старте скана:
   - берётся профиль FOV,
   - рассчитывается grid,
   - создаётся папка проекта,
   - запускается поток сессии `move -> settle -> capture -> save`.
5. Состояние и прогресс транслируются в `EventBus`.
6. По завершении — можно запускать алгоритм сшивки по сохранённым кадрам.

---

## Требования для Raspberry Pi

Рекомендуется:

- Raspberry Pi 4/5,
- Raspberry Pi OS Bookworm (64-bit),
- Python 3.11+,
- подключённая камера (CSI через libcamera/picamera2 или UVC /dev/video0),
- доступ к контроллеру Marlin по USB (опционально; можно использовать `stub`).

---

## Пошаговая установка и запуск на Raspberry Pi

> Важно: **не используйте `.env` для камеры и не стройте запуск вокруг переменных окружения**. В этом проекте всё задаётся через JSON-конфиг, а доступ к камере должен идти напрямую через системные драйверы.

### 1) Обновите систему

```bash
sudo apt update
sudo apt upgrade -y
```

### 2) Установите системные зависимости

```bash
sudo apt install -y \
  git python3 python3-pip python3-venv \
  python3-opencv python3-numpy python3-serial \
  python3-picamera2 v4l-utils
```

> Если используете только USB-камеру, `python3-picamera2` можно оставить, но он не обязателен.

### 3) Клонируйте репозиторий

```bash
git clone https://github.com/Mix145145/claud
cd claud
```

### 4) Создайте виртуальное окружение (опционально, но рекомендуется)

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 5) Установите Python-пакеты (если нужны версии из pip)

Если в вашей среде не хватает модулей, установите:

```bash
pip install --upgrade pip
pip install numpy opencv-python pyserial
```

> Для Raspberry Pi-камеры обычно лучше использовать пакет `python3-picamera2` из apt.

### 6) Создайте конфиг

По умолчанию движок читает `config/tuposcan_config.json`.

Минимальный пример:

```json
{
  "camera": {
    "backend": "auto",
    "resolution": "1920x1080",
    "device_path": "/dev/video0",
    "preview_fps": 15
  },
  "serial": {
    "port": "stub",
    "baudrate": 250000,
    "timeout_s": 10.0,
    "feed_rate_xy": 3000,
    "feed_rate_z": 600,
    "settle_delay_s": 0.3
  },
  "scan": {
    "overlap_pct": 20.0,
    "z_height_mm": 50.0,
    "area_width_mm": 200.0,
    "area_height_mm": 200.0,
    "origin_x_mm": 0.0,
    "origin_y_mm": 0.0,
    "stitch_algorithm": "feather_blend",
    "auto_stitch": true
  },
  "paths": {
    "scans_dir": "scans",
    "config_dir": "config",
    "fov_profiles_file": "config/fov_profiles.json"
  }
}
```

### 7) Проверка камеры в системе

Для CSI-камеры (libcamera):

```bash
libcamera-hello -t 3000
```

Для USB-камеры:

```bash
v4l2-ctl --list-devices
```

### 8) Запуск

Из корня пакета (одним уровнем выше директории `claud` как Python package) обычно запускают так:

```bash
python -m claud
```

Если вы запускаете иначе, убедитесь, что package-импорт резолвится корректно (в проекте используются относительные импорты вида `from .config...`).

---

## Настройка без `.env` (критично)

- Не задавайте backend/port через ENV.
- Не помещайте запуск в окружение, где нет доступа к `/dev/video0` или libcamera.
- Все параметры меняйте только в `config/tuposcan_config.json`.

Почему это важно:

- backend камеры выбирается внутри кода (`create_camera`) и зависит от доступности библиотек/устройств;
- при запуске “через ENV-only” часто теряется прямой доступ к камере, и вы падаете в `stub`;
- для реального захвата кадров нужна полноценная системная среда Raspberry Pi OS с установленными драйверами/библиотеками.

---

## Конфигурация: что можно настраивать

- `camera.backend`: `auto | picamera2 | v4l2 | gstreamer | stub`
- `camera.resolution`: `1920x1080 | 2560x1440 | 3840x2160`
- `serial.port`: `auto | stub | /dev/ttyUSB0 ...`
- `scan.overlap_pct`: процент перекрытия кадров
- `scan.area_width_mm/area_height_mm`: габариты зоны сканирования
- `scan.z_height_mm`: высота камеры
- `scan.stitch_algorithm`: `feather_blend | multiband_blend | ecc_refinement | opencv_fallback`

---

## Выходные данные сканирования

В каталоге `scans/<scan_YYYYMMDD_HHMMSS>/`:

- `frames/` — исходные кадры,
- `stitched/` — результаты сшивки,
- `logs/` — логи,
- `shots.json` — манифест кадров (pending/captured/failed),
- `config_snapshot.json` — снимок конфига на момент старта.

---

## Режимы работы serial

- **Реальный Marlin**: укажите порт (`/dev/ttyUSB0`, `/dev/ttyACM0` и т.п.) или `auto`.
- **Stub**: укажите `serial.port = "stub"`, если хотите отладить без станка.

---

## Типовой сценарий первого запуска

1. Запустить в `stub`-режиме serial и убедиться, что код стартует.
2. Проверить определение камеры (`auto` или принудительно `picamera2`/`v4l2`).
3. Выполнить калибровку на рабочей высоте `z_height_mm`.
4. Запустить скан небольшой области (например 40x40 мм).
5. Проверить, что `shots.json` обновляется и файлы кадров сохраняются.
6. Перейти на реальные размеры и реальный serial-порт.

---

## Диагностика проблем

### Камера не открывается

- Проверьте, что устройство видно в системе (`libcamera-hello`, `v4l2-ctl --list-devices`).
- Проверьте права пользователя на видеоустройства.
- Проверьте, что не используете изолированный runtime без доступа к устройствам.
- Временно поставьте `camera.backend = "stub"` для проверки остального пайплайна.

### Нет связи с Marlin

- Проверьте порт (`/dev/ttyUSB0`, `/dev/ttyACM0`).
- Проверьте baudrate (обычно `250000`).
- На время отладки используйте `serial.port = "stub"`.

### Скан не стартует

- Частая причина: нет FOV-профиля для текущих `z_height_mm + resolution`.
- Запустите калибровку и убедитесь, что обновился `config/fov_profiles.json`.

---

## Примечания по развитию проекта

Проект уже содержит задел под:

- GUI/Web-клиенты (через EventBus + MJPEG streamer),
- разные алгоритмы сшивки,
- восстановление после прерванных сканов,
- расширение поддерживаемых backend'ов камеры и motion-контроллеров.

Если нужно, можно добавить:

- полноценный CLI (argparse/typer),
- unit/integration тесты,
- `requirements.txt` или `pyproject.toml` для воспроизводимой установки,
- systemd unit для автозапуска на Raspberry Pi.

---

## Лицензия

В репозитории пока не указан отдельный файл лицензии. При публикации/коммерческом использовании рекомендуется добавить `LICENSE`.
