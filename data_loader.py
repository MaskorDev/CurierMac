import json
import os
from typing import Dict, Any
from agents import CourierAgent, OrderAgent


class DataLoader:
    @staticmethod
    def load_input_data(filename: str) -> Dict[str, Any]:
        """Загружает входные данные из JSON файла"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except FileNotFoundError:
            print(f"Файл {filename} не найден. Используются данные по умолчанию.")
            return DataLoader.get_default_data()
        except json.JSONDecodeError as e:
            print(f"Ошибка чтения JSON: {e}")
            return DataLoader.get_default_data()

    @staticmethod
    def get_default_data() -> Dict[str, Any]:
        """Возвращает данные по умолчанию"""
        return {
            "couriers": [
                {
                    "id": 1,
                    "location": [55.751244, 37.618423],
                    "transport_type": "car",
                    "max_capacity": 50.0,
                    "name": "Иван Петров"
                },
                {
                    "id": 2,
                    "location": [55.754407, 37.620223],
                    "transport_type": "bicycle",
                    "max_capacity": 15.0,
                    "name": "Анна Сидорова"
                }
            ],
            "orders": [
                {
                    "id": 101,
                    "destination": [55.753605, 37.621585],
                    "weight": 5.0,
                    "priority": "high",
                    "time_window": "10:00-12:00",
                    "description": "Срочный документ"
                },
                {
                    "id": 102,
                    "destination": [55.749676, 37.623483],
                    "weight": 2.0,
                    "priority": "normal",
                    "time_window": "11:00-14:00",
                    "description": "Посылка с одеждой"
                }
            ]
        }

    @staticmethod
    def initialize_agents_from_data(data: Dict[str, Any]):
        """Создает агентов из загруженных данных"""
        from agents import DispatcherAgent

        dispatcher = DispatcherAgent()

        # Создание агентов курьеров
        for courier_data in data.get("couriers", []):
            courier = CourierAgent(
                agent_id=courier_data["id"],
                location=courier_data["location"],
                transport_type=courier_data["transport_type"],
                max_capacity=courier_data["max_capacity"],
                name=courier_data.get("name", "")
            )
            dispatcher.add_courier(courier)

        # Создание агентов заказов
        for order_data in data.get("orders", []):
            order = OrderAgent(
                order_id=order_data["id"],
                destination=order_data["destination"],
                weight=order_data["weight"],
                priority=order_data["priority"],
                time_window=order_data["time_window"],
                description=order_data.get("description", "")
            )
            dispatcher.add_order(order)

        return dispatcher

    @staticmethod
    def save_output_data(dispatcher, monitor, filename: str = "output_results.json"):
        """Сохраняет результаты работы в JSON файл"""
        output_data = {
            "assignments": dispatcher.assignments,
            "statistics": monitor.statistics,
            "couriers": [courier.to_dict() for courier in dispatcher.couriers.values()],
            "orders": [order.to_dict() for order in dispatcher.orders.values()],
            "timestamp": time.time()
        }

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            print(f"Результаты сохранены в {filename}")
        except Exception as e:
            print(f"Ошибка сохранения результатов: {e}")


import time  # Добавляем импорт для timestamp