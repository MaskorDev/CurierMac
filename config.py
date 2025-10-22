# Конфигурационные параметры системы
SERVER_HOST = "localhost"  # Для локального запуска
SERVER_PORT = 8000
BUFFER_SIZE = 4096

# Параметры алгоритма распределения
MAX_ORDERS_PER_COURIER = 5
TIME_WINDOW_PENALTY = 1000
PRIORITY_WEIGHT = 2.0

# Типы транспорта и их скорости (км/ч)
TRANSPORT_SPEEDS = {
    "foot": 5,
    "bicycle": 15,
    "car": 30,
    "motorcycle": 40
}

# Максимальная грузоподъемность по типам транспорта
MAX_CAPACITIES = {
    "foot": 10.0,
    "bicycle": 20.0,
    "car": 100.0,
    "motorcycle": 30.0
}