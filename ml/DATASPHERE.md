# Обучение в Yandex DataSphere

Краткая инструкция: загрузить датасет, выбрать GPU `g1.1`, запустить `ml/datasphere_train.ipynb`, скачать `best.pt`.

## Что подготовить локально

| Файл | Назначение |
|------|------------|
| `data/processed.zip` | Датасет (`images/`, `labels/`) |
| `ml/datasphere_train.ipynb` | Ноутбук обучения |
| `ml/train.py` | Скрипт обучения |
| `backend/` | Нужен `train.py` (импорт `PROJECT_ROOT`) |

Архив `processed.zip` обычно ~400+ MB — через кнопку Upload в JupyterLab (лимит ~100 MB) его не загрузить. Используйте Object Storage / Dataset / Filestore (см. ниже).

## 1. Создать проект DataSphere

1. Откройте [Yandex DataSphere](https://datasphere.yandex.cloud/).
2. Создайте или выберите сообщество и проект.
3. Нажмите **Открыть проект в JupyterLab**.

## 2. Загрузить код проекта

В File Browser загрузите минимум:

- `ml/datasphere_train.ipynb`
- `ml/train.py`
- `ml/__init__.py`
- каталог `backend/` (`config.py` и `__init__.py`)

Либо клонируйте/залейте весь репозиторий.

Структура в проекте должна позволять найти `ml/train.py` из корня рабочей директории ноутбука.

## 3. Загрузить датасет

### Вариант A — Object Storage (рекомендуется для `processed.zip`)

1. Загрузите `data/processed.zip` в бакет Object Storage (консоль Yandex Cloud или `yc storage`).
2. В проекте DataSphere создайте **S3 Connector** к бакету и активируйте его.
3. Скопируйте архив из смонтированного пути (обычно под `/s3/...`) в корень проекта:

```bash
#!:bash
cp /s3/<mount_name>/processed.zip ./processed.zip
```

Либо укажите путь к архиву в первой ячейке распаковки (ноутбук ищет `./processed.zip` и `./data/processed.zip`).

### Вариант B — Dataset / Filestore

1. Создайте Dataset или Filestore в ресурсах проекта.
2. Загрузите туда `processed.zip`.
3. Активируйте ресурс и скопируйте архив в рабочую директорию ноутбука.

### Вариант C — мелкие файлы через UI

Для файлов **до ~100 MB**: File Browser → **Upload Files**.  
Для `processed.zip` этот способ обычно не подходит.

После загрузки в корне проекта должен лежать `processed.zip` (или уже распакованный `data/processed/{images,labels}`).

## 4. Выбрать конфигурацию GPU (g1.1)

1. Откройте `ml/datasphere_train.ipynb`.
2. При **первом запуске** любой ячейки DataSphere предложит выбрать конфигурацию ВМ.
3. Выберите **g1.1** (1× GPU).
   - Зелёный — можно стартовать сразу.
   - Жёлтый — дольше готовится.
   - Красный — занято, ожидание может быть долгим.
4. Если `g1.1` недоступна (`Access Denied`): нужен платный аккаунт и пополнение баланса (см. [документацию Yandex Cloud](https://yandex.cloud/ru/docs/troubleshooting/datasphere/known-issues/getting-access-go-g1-1-config)). Добавьте конфигурацию в настройки проекта, если её нет в списке.

Проверка GPU — ячейка с `ultralytics.checks()` и `torch.cuda.is_available()` (должно быть `True`).

## 5. Запустить ноутбук

Выполняйте ячейки **по порядку**:

1. `%pip install ultralytics`
2. `ultralytics.checks()` + проверка CUDA
3. Распаковка `processed.zip` и запись `data.yaml`
4. Обучение: `epochs=100`, `batch=16`, `imgsz=640`
5. Печать метрик
6. Копия весов в `outputs/best.pt`

Обучение на `g1.1` обычно занимает порядка 1–3 часов (зависит от очереди и загрузки GPU). Не останавливайте IDE до конца прогона.

## 6. Скачать `best.pt`

После успешного обучения веса будут в двух местах:

| Путь | Описание |
|------|----------|
| `outputs/best.pt` | Удобная копия для скачивания |
| `ml/runs/detect/train_datasphere/weights/best.pt` | Оригинал ultralytics |

Как скачать:

1. В File Browser найдите `outputs/best.pt`.
2. ПКМ → **Download**.
3. Альтернатива: ПКМ по папке проекта → **Download Current Folder as an Archive** (если нужен весь прогон с графиками).

Для выгрузки большого артефакта в облако можно скопировать файл обратно в S3/Filestore и скачать оттуда.

## Типичные проблемы

| Симптом | Что сделать |
|---------|-------------|
| `No module named ultralytics` | Перезапустить ячейку `%pip install ultralytics` |
| `cuda_available=False` | Убедиться, что выбрана **g1.1**, а не CPU-конфиг; перезапустить вычисления |
| `processed.zip` не найден | Проверить путь в File Browser; скопировать архив в корень проекта |
| `Не найден data.yaml` / пустой датасет | Архив должен содержать `images/` и `labels/` (ноутбук сам создаст `data.yaml`) |
| Обучение слишком медленное | Проверить, что в логе ultralytics указан CUDA/GPU, не CPU |

## Полезные ссылки

- [Выбор вычислительных ресурсов](https://yandex.cloud/ru/docs/datasphere/operations/projects/control-compute-resources)
- [Проверка GPU](https://yandex.cloud/ru/docs/datasphere/operations/projects/gpu-performance-check)
- [Файловые хранилища](https://yandex.cloud/ru/docs/datasphere/operations/data/filestores)
- [S3 Connector](https://yandex.cloud/ru/docs/datasphere/operations/data/s3-connectors)
