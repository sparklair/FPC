Ты — senior Python/backend engineer и frontend engineer. Создай полностью рабочий демонстрационный проект системы мониторинга и автоматического контроля телеметрии космического аппарата.

Проект должен выглядеть как серьезное программное обеспечение наземного центра управления полетами (Mission Control / Ground Control), но при этом вся телеметрия является искусственно генерируемой симуляцией. Реального подключения к космическому аппарату нет.

Основная идея:

SPACECRAFT SIMULATOR
        ↓
Telemetry Stream
        ↓
Flask Backend
        ↓
Telemetry Analysis / Safety Engine
        ↓
 ┌───────────────┬────────────────┐
 ↓               ↓                ↓
Web Dashboard   Event Log    Autonomous Actions

Система должна непрерывно генерировать телеметрию, отображать ее через WebUI в реальном времени, анализировать параметры, определять опасные состояния и автоматически выполнять имитационные защитные действия.

# 1. Технологии

Backend обязательно:
- Python 3
- Flask
- Flask-SocketIO для real-time обновлений
- SQLAlchemy
- SQLite
- threading / background tasks для симулятора

Frontend:
- HTML5
- CSS3
- JavaScript
- Bootstrap 5 допустим, но интерфейс не должен выглядеть как стандартная Bootstrap-страница
- Chart.js для real-time графиков
- Socket.IO client

Не использовать React/Vue/Angular и не добавлять Node.js build pipeline без необходимости.

Проект должен запускаться локально максимально просто.

# 2. Архитектура

Не помещай всё приложение в один app.py.

Сделай понятную модульную структуру примерно такого типа:

spacecraft_control/
    app.py
    config.py
    requirements.txt
    README.md

    telemetry/
        simulator.py
        models.py
        generator.py

    safety/
        engine.py
        rules.py
        actions.py

    services/
        telemetry_service.py
        event_service.py

    routes/
        api.py
        views.py

    templates/
        base.html
        dashboard.html

    static/
        css/
            style.css
        js/
            dashboard.js

При необходимости архитектуру можно улучшить.

Код должен быть чистым, понятным и расширяемым.

# 3. Модель космического аппарата

Смоделируй небольшой научный спутник на низкой околоземной орбите.

У него должны существовать следующие подсистемы:

EPS — Electrical Power System
THERMAL — Thermal Control
ADCS — Attitude Determination and Control System
COMMS — Communications
PAYLOAD — Scientific Payload
OBC — On-Board Computer

Каждая подсистема имеет собственную телеметрию.

# 4. Телеметрия

Генерируй новые данные примерно раз в 1 секунду.

Значения должны изменяться плавно и реалистично, а не быть полностью случайными на каждом шаге.

Примеры параметров:

EPS:
- battery_voltage
- battery_current
- battery_charge_percent
- solar_array_voltage
- power_consumption

THERMAL:
- obc_temperature
- battery_temperature
- payload_temperature
- external_temperature

ADCS:
- roll
- pitch
- yaw
- angular_velocity
- reaction_wheel_rpm

COMMS:
- signal_strength
- packet_loss
- uplink_status
- downlink_rate

PAYLOAD:
- payload_status
- payload_temperature
- payload_power
- data_buffer_usage

OBC:
- cpu_load
- memory_usage
- storage_usage
- watchdog_status
- uptime

Добавь также общие параметры:
- spacecraft_mode
- mission_elapsed_time
- telemetry_sequence_number
- timestamp
- link_status

# 5. Реалистичность симуляции

Телеметрия должна быть взаимосвязанной.

Например:
- увеличение payload_power постепенно увеличивает payload_temperature;
- высокая нагрузка OBC повышает температуру OBC;
- при включенном payload быстрее расходуется батарея;
- при хорошей генерации солнечных панелей заряд батареи увеличивается;
- отключение payload уменьшает энергопотребление и температуру;
- проблемы связи увеличивают packet_loss;
- высокие обороты reaction wheel могут приводить к предупреждению ADCS.

Используй простую математическую модель состояния аппарата вместо независимого random() для каждого параметра.

Добавь небольшие естественные шумы измерений.

# 6. Орбитальный цикл

Добавь упрощенную симуляцию движения аппарата между солнечной и теневой частью орбиты.

Например, цикл продолжительностью несколько минут для удобства демонстрации.

SUNLIGHT:
солнечные панели генерируют энергию → батарея заряжается.

ECLIPSE:
солнечной генерации нет → аппарат работает от батареи.

Это должно быть видно в WebUI.

Добавь индикатор:

ORBIT PHASE
SUNLIGHT / ECLIPSE

# 7. Safety Engine

Это ключевая часть проекта.

Создай отдельный движок правил, который анализирует каждый новый telemetry frame.

У каждого параметра могут быть уровни:

NORMAL
WARNING
CRITICAL

Например:

battery_charge:
> 30% NORMAL
15–30% WARNING
< 15% CRITICAL

OBC temperature:
< 70°C NORMAL
70–80°C WARNING
> 80°C CRITICAL

packet_loss:
< 5% NORMAL
5–20% WARNING
> 20% CRITICAL

reaction_wheel_rpm:
NORMAL / WARNING / CRITICAL по заданным порогам.

Пороговые значения вынеси в отдельную конфигурацию, чтобы их было легко менять.

Не ограничивайся этими примерами — создай разумные демонстрационные пределы для основных параметров.

# 8. Автоматические защитные действия

При CRITICAL состоянии система должна не только показывать тревогу, но и автоматически имитировать реакцию аппарата.

Реализуй несколько сценариев.

SCENARIO 1 — LOW BATTERY

Если заряд батареи критически низкий:

1. создать CRITICAL event;
2. отключить PAYLOAD;
3. уменьшить энергопотребление;
4. перевести аппарат в POWER_SAVE;
5. записать автоматическую команду:
   AUTO ACTION: PAYLOAD_OFF
6. после восстановления заряда автоматически разрешить возврат в NOMINAL.

SCENARIO 2 — PAYLOAD OVERHEAT

Если payload_temperature превышает критическое значение:

1. CRITICAL alarm;
2. PAYLOAD_OFF;
3. payload_power → 0;
4. температура начинает постепенно снижаться;
5. зарегистрировать причину и действие.

SCENARIO 3 — OBC OVERHEAT

При критической температуре OBC:

1. снизить simulated CPU load;
2. отключить второстепенные процессы;
3. перевести аппарат в SAFE_MODE при дальнейшем росте температуры.

SCENARIO 4 — COMMUNICATION LOSS

При критическом packet_loss / потере связи:

1. создать alarm;
2. инициировать simulated antenna reacquisition;
3. переключить состояние COMMS в REACQUIRING;
4. через некоторое время попытаться восстановить соединение;
5. записать результат операции.

SCENARIO 5 — ADCS ANOMALY

При слишком больших reaction wheel RPM или angular velocity:

1. WARNING/CRITICAL;
2. выполнить simulated reaction wheel desaturation;
3. снизить RPM;
4. при серьезной ошибке перейти в SAFE_MODE.

Очень важно:
автоматические действия должны реально изменять дальнейшую симуляцию телеметрии.

Это должна быть closed-loop simulation:

ANOMALY
↓
DETECTION
↓
AUTOMATIC ACTION
↓
SPACECRAFT STATE CHANGES
↓
TELEMETRY CHANGES
↓
RECOVERY

# 9. Инъекция неисправностей

Для демонстрации обязательно сделай Fault Injection Panel.

Пользователь должен иметь возможность вручную вызвать неисправность через WebUI.

Кнопки:

INJECT BATTERY DRAIN
INJECT PAYLOAD OVERHEAT
INJECT OBC OVERHEAT
INJECT COMMUNICATION LOSS
INJECT ADCS INSTABILITY
RESET / CLEAR FAULTS

После нажатия неисправность должна не просто мгновенно менять одно число, а запускать сценарий деградации.

Например:

INJECT PAYLOAD OVERHEAT

payload_temperature начинает постепенно увеличиваться.

Safety Engine сначала обнаруживает WARNING, затем CRITICAL, после чего автоматически отключает payload.

Это позволит наглядно демонстрировать работу системы.

# 10. WebUI

Интерфейс должен напоминать современный Mission Control Dashboard.

Стиль:
- dark theme;
- профессиональный;
- минималистичный;
- технический;
- без детского sci-fi дизайна;
- без чрезмерных neon/glow эффектов;
- аккуратные тонкие границы;
- высокая плотность полезной информации;
- хорошая типографика.

Цветовые состояния:
NORMAL — спокойный зеленый
WARNING — amber/yellow
CRITICAL — red
OFFLINE — gray
INFORMATION — blue

Цвета использовать умеренно — преимущественно для статусов и тревог.

# 11. Главный Dashboard

В верхней части:

SPACECRAFT TELEMETRY CONTROL SYSTEM

и глобальный статус:

SPACECRAFT: ONLINE
MODE: NOMINAL
LINK: CONNECTED
ORBIT PHASE: SUNLIGHT
MISSION TIME: ...
LAST TELEMETRY: ...

Ниже разместить карточки подсистем:

EPS
THERMAL
ADCS
COMMS
PAYLOAD
OBC

Каждая карточка должна показывать наиболее важные параметры и состояние:

NOMINAL
WARNING
CRITICAL
OFFLINE

# 12. Real-time графики

Добавь несколько графиков Chart.js.

Например:

Battery Charge
Battery Voltage
Power Generation / Consumption
OBC Temperature
Payload Temperature
Reaction Wheel RPM
Signal Strength
Packet Loss
CPU Load

Не нужно показывать все графики одновременно огромной стеной.

Организуй интерфейс логично.

Хранить на графике последние ~60–120 точек.

Графики обновлять через WebSocket без перезагрузки страницы.

# 13. Alarm / Event Log

В интерфейсе должен существовать real-time журнал событий.

Пример:

22:41:03 INFO      Telemetry link established
22:41:16 WARNING   Payload temperature above nominal range
22:41:24 CRITICAL  Payload temperature exceeded 85°C
22:41:24 AUTO      Command PAYLOAD_OFF issued
22:41:25 INFO      Payload power consumption decreased
22:41:47 RECOVERY  Payload temperature returning to nominal range

Типы событий:

INFO
WARNING
CRITICAL
AUTO_ACTION
RECOVERY
COMMAND

Для каждого события сохранять:
- timestamp;
- severity;
- subsystem;
- message;
- parameter;
- measured value;
- threshold;
- automatic action, если оно было.

События сохранять в SQLite.

# 14. Active Alarms

Отдельно от Event Log сделай ACTIVE ALARMS.

Там должны отображаться только текущие нерешенные проблемы.

Например:

CRITICAL
THERMAL
Payload temperature
87.4°C
LIMIT: 85°C

Когда параметр возвращается в безопасный диапазон, alarm автоматически становится CLEARED.

Нужна небольшая защита от постоянного переключения состояния около порога — hysteresis/debounce.

# 15. Command Log

Добавь отдельный журнал команд:

COMMAND HISTORY

Например:

PAYLOAD_OFF
ENTER_POWER_SAVE
ENTER_SAFE_MODE
COMMS_REACQUIRE
ADCS_DESATURATION
RETURN_NOMINAL

Для каждой команды:
- timestamp;
- source: AUTO или OPERATOR;
- command;
- subsystem;
- reason;
- result.

# 16. Ручное управление

Добавь небольшой Operator Control Panel.

Допустимые демонстрационные команды:

PAYLOAD ON/OFF
ENTER POWER SAVE
ENTER SAFE MODE
RETURN TO NOMINAL
COMMS REACQUIRE
ADCS DESATURATION

Перед потенциально важными действиями показывать confirmation dialog.

Команды должны проходить через backend, регистрироваться и изменять состояние симуляции.

# 17. Incident Timeline

При возникновении критической аварии желательно автоматически объединять связанные события в incident.

Например:

INCIDENT #0042
PAYLOAD THERMAL EXCURSION

22:41:16 WARNING detected
22:41:24 CRITICAL threshold exceeded
22:41:24 PAYLOAD_OFF issued
22:41:47 Temperature decreasing
22:42:13 Parameter returned to nominal
22:42:13 INCIDENT RESOLVED

Это сделает демонстрацию значительно интереснее.

# 18. API

Создай REST API минимум для:

GET /api/telemetry/current
GET /api/events
GET /api/alarms
GET /api/commands
GET /api/status

POST /api/command
POST /api/fault/inject
POST /api/fault/reset

Проводи базовую валидацию входящих данных.

# 19. WebSocket

Через Socket.IO отправляй события вроде:

telemetry_update
alarm_update
event_update
command_update
spacecraft_status_update

Frontend не должен опрашивать backend каждую секунду через REST, если информацию можно получать через WebSocket.

# 20. История телеметрии

Хранить небольшую историю телеметрии.

Не обязательно записывать абсолютно каждый параметр бесконечно.

Можно использовать:
- ring buffer в памяти для быстрых графиков;
- SQLite для событий, alarms/incidents и command history.

Архитектурно раздели оперативную telemetry history и постоянный event history.

# 21. Демонстрационный режим

Добавь режим DEMO/AUTO DEMO.

После включения система сама через разумные интервалы запускает заранее подготовленный сценарий:

Nominal operation
→ небольшое отклонение
→ WARNING
→ развитие аварии
→ CRITICAL
→ automatic safety action
→ изменение телеметрии
→ recovery
→ возвращение NOMINAL

Это должно позволять запустить приложение и показать всю работу системы без ручного нажатия Fault Injection.

Добавь возможность включить/выключить AUTO DEMO.

# 22. Важные детали логики

Не генерируй тревогу каждую секунду, пока параметр находится выше порога.

Например:

при первом переходе NORMAL → WARNING:
создать событие один раз.

WARNING → CRITICAL:
создать новое событие.

CRITICAL → WARNING:
создать recovery/update.

WARNING → NORMAL:
закрыть alarm и создать RECOVERY.

Используй state tracking.

Добавь hysteresis, чтобы значение около 80°C не создавало десятки переходов:

79.9
80.1
79.8
80.2

Также защити автоматические действия от многократного выполнения одной команды каждую секунду.

# 23. UI animations

Использовать только аккуратные анимации:

- плавное обновление чисел;
- небольшое изменение цвета status badge;
- мягкое появление нового alarm;
- красный indicator для CRITICAL;
- connection indicator.

Не использовать чрезмерные flashing/blinking эффекты.

Для критического состояния допустима небольшая ненавязчивая pulse-анимация.

# 24. Simulation Controls

Добавь небольшую панель:

SIMULATION
RUNNING / PAUSED

Speed:
0.5x
1x
2x
5x

Controls:
PAUSE
RESUME
RESET SIMULATION

Также отображать:

SIMULATION TIME
TELEMETRY FRAMES
UPTIME

# 25. Начальные условия

При запуске аппарат должен находиться в нормальном состоянии:

MODE: NOMINAL
LINK: CONNECTED
PAYLOAD: ON
ADCS: STABLE
BATTERY: примерно 75–90%
OBC TEMP: normal
PAYLOAD TEMP: normal
ACTIVE ALARMS: 0

Значения слегка колеблются естественным образом.

# 26. UX

Dashboard должен хорошо выглядеть на обычном мониторе 1920×1080.

Главная информация должна помещаться без необходимости бесконечного вертикального скролла.

Используй CSS Grid/Flexbox.

Сделай responsive layout, но desktop является главным вариантом.

# 27. Надежность

Backend не должен падать из-за:
- отключившегося WebSocket клиента;
- неправильной команды;
- неизвестного fault;
- отсутствующих данных;
- перезапуска симулятора.

Добавь нормальное логирование Python.

# 28. README

Создай подробный README.md:

- описание проекта;
- архитектура;
- возможности;
- структура директорий;
- установка;
- создание venv;
- установка requirements;
- запуск;
- используемые порты;
- описание Fault Injection;
- описание Safety Engine;
- список автоматических защитных действий;
- REST API;
- WebSocket events.

Добавь пример запуска:

python -m venv .venv

Linux/macOS:
source .venv/bin/activate

Windows:
.venv\Scripts\activate

pip install -r requirements.txt
python app.py

После запуска интерфейс должен быть доступен локально.

# 29. Требования к реализации

Это должен быть действительно запускаемый проект, а не mockup.

Не оставляй:
TODO
pass
"implement later"
пустые функции
фиктивные API endpoints.

Frontend должен быть полностью связан с backend.

Fault Injection должен реально воздействовать на simulator.

Safety Engine должен реально реагировать на изменение telemetry.

Automatic Actions должны реально менять состояние spacecraft simulator.

Chart.js должен получать реальные данные симулятора через Socket.IO.

Event Log должен реально обновляться.

Команды оператора должны реально выполняться.

# 30. Приоритеты

Если необходимо выбирать между визуальными украшениями и архитектурой/функциональностью, приоритет:

1. корректная simulation model;
2. Safety Engine;
3. closed-loop automatic actions;
4. real-time WebSocket;
5. Fault Injection;
6. alarms/events/commands;
7. хороший WebUI;
8. дополнительные декоративные элементы.

# 31. Финальная проверка

Перед завершением самостоятельно проверь проект.

Убедись, что:

- приложение запускается;
- нет import errors;
- requirements.txt содержит зависимости;
- Flask server стартует;
- главная страница открывается;
- Socket.IO подключается;
- telemetry обновляется;
- графики получают новые точки;
- fault injection работает;
- WARNING и CRITICAL действительно возникают;
- automatic actions выполняются;
- состояние аппарата меняется после automatic actions;
- alarms очищаются после recovery;
- события сохраняются;
- simulation reset работает.

Исправь обнаруженные ошибки до завершения работы.

Не ограничивайся описанием того, как это реализовать. Создай все необходимые файлы и полностью реализуй проект.