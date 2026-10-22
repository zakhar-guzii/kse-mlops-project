# Tasks

Це implementation checklist **лише для Lab 1**. Усі пункти нижче ще не виконані. Поточний propose не є дозволом почати apply. Runtime-компоненти Labs 2–5 описуються в design, але не будуються цим change; capability specs пропущено через `skip_specs: true`.

## 1. Документ дизайну та покриття Lab 1

- [ ] 1.1 Створити `docs/design.md` зі змісту 1–7.4 planning design: overview 3–5 речень, motivation, три рівні success metrics, усі сім категорій NFR, scope/out-of-scope; перевірити точну нумерацію за PDF, наявність явних assumptions і відсутність вигаданих benchmark results.
- [ ] 1.2 Перенести data checklist, часові поля/freshness/replay policy, формати raw/clean/features, taxonomy mapping, train/serve features, незалежність OEM-контролю, NAIP agreement, Colab bundle та promotion/rollback; перевірити сценарії expected-new зі старими bytes, intentional replay, NAIP без masks і teacher train+val без заяви про незалежність.
- [ ] 1.3 Додати три Mermaid-схеми та узгоджену таблицю local/cloud components; перевірити syntax/render доступним засобом і вручну звірити 7 layers, raw/derived version points, conditional raw gate, annotation+mask gate, training/serving divergence, Colab і два application services. Якщо renderer недоступний, явно позначити render check як невиконаний.
- [ ] 1.4 Заповнити security/privacy, monitoring, upstream/downstream contracts та конкретний corpus manifest plan з назвами/версіями/посиланнями; перевірити 24h expiry для queued/running jobs, proposed 30-day log retention, ignore-vs-NoData, RGB-only serving, secrets поза Git і відсутність фальшивих snapshot hashes.
- [ ] 1.5 Додати ≥2 alternatives із pros/cons/reason, risk→mitigation, placeholders 7.2/7.3 і по реченню на Labs 2–5; звірити документ із PDF с. 2–4 та покриттям 20 питань додатка 2. Відсутні повні умови майбутніх labs і невирішені data/teacher gates мають залишитися явно позначеними; окремий конспект або research-файл не створювати.

## 2. Cloud estimate як конкретний delivery gate

- [ ] 2.1 Відтворити в AWS Pricing Calculator наведений у design сценарій us-east-1/730h з EKS, EC2, EBS, MWAA, managed MLflow, RDS jobs/index, S3, ECR, CloudWatch, network і SES; перевірити регіональні EC2/RDS/MLflow/NAT rates, обґрунтувати NAT/endpoints/egress і вибір dashboard/alarms. Доказ виконання — estimate ID/URL, дата та вхідні параметри; без створення платних cloud resources. Якщо інтерактивний calculator недоступний, залишити пункт невиконаним і повідомити конкретний blocker.
- [ ] 2.2 Оновити 6.7 та відповідні cloud labels за фактичним calculator estimate, перерахувати total і розділити verified rates, capacity assumptions та виключені GPU/LLM/training costs; перевірити відсутність double counting managed MLflow/RDS/shared worker і збереження фактичного бюджету $0. Ручну попередню суму $1109.94 не називати calculator output.

## 3. Pinned dev environment і локальні команди

- [ ] 3.1 Додати `.python-version` з 3.12.13 та dev dependencies Ruff 0.17.2/pre-commit 4.7.0 у `pyproject.toml`, оновити `uv.lock`; перевірити `uv lock --check` та `uv sync --locked` на обраному Python. Якщо саме ці pins несумісні/недоступні, зафіксувати причину й перевірений мінімальний сумісний pin, не додаючи ML/runtime stack.
- [ ] 3.2 Створити `Makefile` з `setup` → `uv sync --locked` та `lint` → `uv run --locked ruff check .`; перевірити обидві команди й те, що lint не змінює source автоматично. Не створювати штучний Python app заради наявності lint inputs.
- [ ] 3.3 Створити `.pre-commit-config.yaml` з local hook, який використовує той самий locked Ruff і правила; перевірити `uv run --locked pre-commit validate-config` та `uv run --locked pre-commit run --all-files`. Не встановлювати глобальні hooks або tooling поза потрібним середовищем автоматично.

## 4. README та lint CI

- [ ] 4.1 Заповнити `README.md` п'ятьма реченнями про проблему, командами setup/lint, посиланням на design і двома початковими maturity rows; перевірити кількість речень, коректність локальних посилань і те, що CI/clean-clone evidence описане без неправдивого статусу green.
- [ ] 4.2 Створити `.github/workflows/lint.yml` на push і pull_request, із зафіксованим Python/uv та викликами `make setup` і `make lint`; перевірити workflow структуру та відповідність локальним командам, без training/container/deploy/test jobs поза scope Lab 1. Задокументувати prerequisites uv/Python у README.

## 5. Інтеграційна перевірка перед review

- [ ] 5.1 У чистій тимчасовій копії фінального дерева виконати documented setup/lint і pre-commit, перевірити locked environment та читабельність схем/посилань; записати реальні результати в README/design, не видаючи копію непублікованих змін за вже перевірений remote clean clone.
- [ ] 5.2 Перевірити повний diff на дозволений file scope, відсутність datasets/checkpoints/secrets/runtime code та відповідність документа трьом схемам; виконати `git diff --check` і `openspec validate prepare-lab1-landcover-foundation --strict`. Звірити всі невиконані delivery gates перед заявою про готовність Lab 1.

## Workflow follow-up

- Після окремої явної команди виконати commit/push; перевірити green lint CI саме на default branch.
- Після публікації виконати `make setup` і `make lint` у справжньому чистому clone commit, який здається, та оновити evidence за потреби.
- Лише після виконання submission acceptance створити tag `lab-1` і надати repository link.
- Archive change після виконання tracked tasks і review; незавершений calculator/render gate не приховувати як виконаний.
- Повні умови Labs 2–5 прочитати перед їхніми окремими implementation changes.
