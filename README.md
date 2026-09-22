# Build Watch — мониторинг стройплощадки (ТЗ ДГП Москвы)

Прототип: детекция строительной техники на снимках с камер → сопоставление с календарным планом СМР → выявление отклонений.

## Обязательные функции (ТЗ)

1. Обнаружение и классификация техники (YOLO, до 12 классов).
2. Сопоставление с графиком по методике «этап → необходимая техника».
3. Визуализация в веб-интерфейсе.
4. Отклонения: нет нужной техники, неполное звено, техника не под этап — с привязкой к снимкам и зоне.

## Структура

```
backend/     FastAPI: detect, sites, timeline, /api/demo/analyze
frontend/    Vite + React: Демо, карта, объект, снимок
ml/          инференс + classes (12)
data/        store.json, photos/ (рабочие данные рантайма)
Демо/        материалы для демо: Excel/CSV плана, test_photos/
```

## Запуск

### Backend (порт 8000)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend (порт 5173)

```powershell
cd frontend
npm install
npm run dev
```

Открыть: http://127.0.0.1:5173 → страница **Демо**.

## Демо-сценарий

1. Загрузить календарный план (`Демо/demo_schedule_timelapse.xlsx` или `Демо/schedule_example.csv`).
2. Загрузить снимки, задать базовую дату и шаг.
3. «Запустить анализ» → детекции, таймлайн план/факт, предупреждения со ссылками на снимки.

## Методика этапов

| Этап | Маркеры | Звено |
|------|---------|-------|
| Земляные / котлован | excavator, bulldozer | dump_truck или truck |
| Свайный фундамент | pile_driver | autocrane / crane_manipulator |
| Монолит | concrete_mixer, concrete_pump | оба |
| Надземная / монтаж | tower_crane, autocrane, crane_manipulator | — |

## Классы модели (12)

Порядок id для дообучения:  
0 excavator, 1 bulldozer, 2 loader, 3 dump_truck, 4 concrete_mixer, 5 concrete_pump,  
6 tower_crane, 7 autocrane, 8 pile_driver, **9 truck, 10 crane_manipulator, 11 roller**.

Положите `best.pt` в `ml/weights/best.pt` (или пути из `ml/infer.py`).

## API (кратко)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/health` | статус модели |
| GET | `/api/classes` | классы |
| GET | `/api/stages` | методика этапов |
| POST | `/api/detect` | детекция кадра |
| POST | `/api/demo/analyze` | план + фото → timeline + отклонения |
| GET | `/api/sites` | объекты на карте |
| GET | `/api/sites/{id}/timeline` | план/факт по дням |
| GET | `/api/photos/{id}` | снимок + вывод алгоритма |
