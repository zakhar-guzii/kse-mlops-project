# Proposal

## Why

Погоджений навчальний проєкт має допомагати GIS-фахівцю отримувати багатокласову карту покриття території зі знімка та з часом донавчати модель на нових партіях даних. Репозиторій наразі містить умови Lab 1 і початкове Python-середовище, але не має документа дизайну, README зі scorecard або відтворюваного lint-каркаса, необхідних для здачі.

## What Changes

- Підготувати `docs/design.md` з точною структурою Lab 1, трьома узгодженими схемами, джерелами та явно відокремленими фактами, погодженими рішеннями, новими припущеннями й невиміряними характеристиками.
- Описати OEM taxonomy, NAIP Utah 2018/2021 та фінальну перевірку 2024, незалежність контролю, походження псевдомасок, freshness/idempotency, train/serve-контракти та відтворюване донавчання з ручним запуском Colab.
- Зафіксувати локальний inference, мінімальний вебінтерфейс, DVC/S3-сумісне сховище, Airflow, MLflow, PostgreSQL, GIS-помічника, email-моніторинг і roadmap Labs 2–5.
- Надати конкретний retrieval-корпус, managed cloud equivalents, параметричну модель вартості й попередній числовий сценарій; окремо позначити незавершену перевірку provider calculator.
- Підготувати README з п'ятьма реченнями про проблему та двома Lab 1 scorecard rows; pinned dev environment, Makefile `setup`/`lint`, pre-commit із тим самим linter та lint CI.
- Передбачити перевірку clean-clone setup/lint, узгодженості документа й схем, підготовку до захисту та checklist здачі.

Цей change охоплює документацію та tooling Lab 1. Навчання, завантаження великих датасетів, inference/UI, Airflow DAG, corpus ingestion, контейнери, Minikube, email і LLM/agent описуються як наступні етапи та не реалізуються ним. Фактичний бюджет залишається $0; платні ресурси не створюються.

## Capabilities

### New Capabilities

Немає змін runtime-поведінки: це документація та інструменти репозиторію. У `.openspec.yaml` встановлено `skip_specs: true`; поведінкові specs майбутніх сервісів мають з'являтися разом із відповідними changes Labs 2–5.

### Modified Capabilities

Немає. Перевірка `openspec list --specs --json` не виявила наявних capability specs.

## Impact

- Поточний propose створює лише planning artifacts усередині `openspec/changes/prepare-lab1-landcover-foundation/`.
- Майбутній apply змінює `README.md`, створює `docs/design.md`, `Makefile`, `.pre-commit-config.yaml`, `.github/workflows/lint.yml`, `.python-version` та оновлює `pyproject.toml`/`uv.lock` лише для мінімального dev tooling. Розрахунок калькулятора фіксується в design як посилання з датою та вхідними параметрами; окремі research-файли не відновлюються.
- Runtime ML/MLOps-залежності не встановлюються на етапі Lab 1. Системні Python, Docker, Minikube та конфігурація машини цим change не змінюються.
- Git commit/push, отримання green CI на default branch і submission tag `lab-1` є окремими кроками здачі; поточний propose їх не виконує.
- Ризики: непідтверджене походження готового annotator, відсутність незалежної temporal NAIP ground truth, неперевірені конкретні tiles, сумісність майбутніх ML-залежностей та незавершений cloud calculator estimate.
