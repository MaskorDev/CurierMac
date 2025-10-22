import json
import time
import threading
from typing import List, Dict, Any
import math
from config import *


class CourierAgent:
    def __init__(self, agent_id: int, location: List[float], transport_type: str,
                 max_capacity: float, name: str = ""):
        self.id = agent_id
        self.location = location  # [lat, lon]
        self.transport_type = transport_type
        self.max_capacity = max_capacity
        self.current_capacity = 0.0
        self.current_orders = []
        self.status = "available"  # available, busy, offline, emergency
        self.speed = TRANSPORT_SPEEDS.get(transport_type, 10)
        self.name = name or f"Courier_{agent_id}"
        self.last_update = time.time()

    def can_accept_order(self, order) -> bool:
        """Проверяет, может ли курьер принять заказ"""
        if self.status != "available":
            return False
        if self.current_capacity + order.weight > self.max_capacity:
            return False
        if len(self.current_orders) >= MAX_ORDERS_PER_COURIER:
            return False
        return True

    def accept_order(self, order):
        """Добавляет заказ курьеру"""
        self.current_orders.append(order)
        self.current_capacity += order.weight
        if len(self.current_orders) >= MAX_ORDERS_PER_COURIER:
            self.status = "busy"
        order.status = "assigned"
        order.assigned_courier = self.id

    def complete_order(self, order_id):
        """Отмечает заказ как выполненный"""
        for order in self.current_orders:
            if order.id == order_id:
                self.current_orders.remove(order)
                self.current_capacity -= order.weight
                order.status = "delivered"
                break

        if len(self.current_orders) < MAX_ORDERS_PER_COURIER and self.status != "emergency":
            self.status = "available"

    def to_dict(self):
        return {
            "id": self.id,
            "location": self.location,
            "transport_type": self.transport_type,
            "max_capacity": self.max_capacity,
            "current_capacity": self.current_capacity,
            "current_orders": [order.id for order in self.current_orders],
            "status": self.status,
            "name": self.name
        }


class OrderAgent:
    def __init__(self, order_id: int, destination: List[float], weight: float,
                 priority: str, time_window: str, description: str = ""):
        self.id = order_id
        self.destination = destination  # [lat, lon]
        self.weight = weight
        self.priority = priority  # high, normal, low
        self.time_window = time_window  # "HH:MM-HH:MM"
        self.description = description
        self.status = "pending"  # pending, assigned, in_progress, delivered, cancelled
        self.assigned_courier = None
        self.created_time = time.time()

    def to_dict(self):
        return {
            "id": self.id,
            "destination": self.destination,
            "weight": self.weight,
            "priority": self.priority,
            "time_window": self.time_window,
            "description": self.description,
            "status": self.status,
            "assigned_courier": self.assigned_courier,
            "created_time": self.created_time
        }


class DispatcherAgent:
    def __init__(self):
        self.couriers = {}
        self.orders = {}
        self.assignments = []
        self.traffic_data = {}  # Имитация данных о трафике

    def add_courier(self, courier: CourierAgent):
        self.couriers[courier.id] = courier

    def add_order(self, order: OrderAgent):
        self.orders[order.id] = order

    def calculate_distance(self, point1, point2):
        """Рассчитывает расстояние между двумя точками (упрощенная формула)"""
        lat1, lon1 = point1
        lat2, lon2 = point2
        return math.sqrt((lat2 - lat1) ** 2 + (lon2 - lon1) ** 2) * 111  # Примерно км

    def estimate_delivery_time(self, courier, order):
        """Оценивает время доставки с учетом трафика"""
        distance = self.calculate_distance(courier.location, order.destination)
        base_time = (distance / courier.speed) * 60  # в минутах

        # Учет трафика (упрощенно)
        traffic_factor = self.traffic_data.get("factor", 1.0)
        return base_time * traffic_factor

    def assign_orders(self):
        """Основной алгоритм распределения заказов"""
        pending_orders = [order for order in self.orders.values() if order.status == "pending"]
        available_couriers = [courier for courier in self.couriers.values()
                              if courier.status == "available"]

        if not pending_orders or not available_couriers:
            return

        # Сортируем заказы по приоритету и времени создания
        pending_orders.sort(key=lambda x: (x.priority != "high", x.created_time))

        for order in pending_orders:
            best_courier = None
            best_score = float('inf')

            for courier in available_couriers:
                if not courier.can_accept_order(order):
                    continue

                # Расчет оценки для этого курьера и заказа
                delivery_time = self.estimate_delivery_time(courier, order)

                # Приоритетные заказы получают бонус
                priority_bonus = 0
                if order.priority == "high":
                    priority_bonus = -50  # Уменьшаем оценку для приоритетных
                elif order.priority == "low":
                    priority_bonus = 20  # Увеличиваем для низкоприоритетных

                # Учет загруженности курьера
                load_penalty = courier.current_capacity * 0.1

                score = delivery_time + priority_bonus + load_penalty

                if score < best_score:
                    best_score = score
                    best_courier = courier

            if best_courier:
                best_courier.accept_order(order)
                assignment = {
                    "courier_id": best_courier.id,
                    "order_id": order.id,
                    "estimated_time": f"{delivery_time:.1f} мин",
                    "score": best_score
                }
                self.assignments.append(assignment)
                print(f"Заказ {order.id} назначен курьеру {best_courier.id} (оценка: {best_score:.2f})")

    def handle_emergency(self, courier_id):
        """Обработка чрезвычайной ситуации с курьером"""
        if courier_id not in self.couriers:
            return False

        courier = self.couriers[courier_id]
        courier.status = "emergency"

        # Перераспределение заказов
        orders_to_redistribute = courier.current_orders.copy()
        for order in orders_to_redistribute:
            courier.complete_order(order.id)
            order.status = "pending"  # Возвращаем в ожидание
            order.assigned_courier = None

        print(f"ЧП: Курьер {courier_id} снят с маршрута. Заказы перераспределяются.")
        self.assign_orders()
        return True


class MonitorAgent:
    def __init__(self):
        self.statistics = {
            "total_orders": 0,
            "delivered": 0,
            "in_progress": 0,
            "pending": 0,
            "cancelled": 0,
            "avg_delivery_time": 0,
            "courier_utilization": 0
        }

    def update_statistics(self, dispatcher: DispatcherAgent):
        orders = list(dispatcher.orders.values())
        couriers = list(dispatcher.couriers.values())

        self.statistics["total_orders"] = len(orders)
        self.statistics["delivered"] = len([o for o in orders if o.status == "delivered"])
        self.statistics["in_progress"] = len([o for o in orders if o.status == "assigned"])
        self.statistics["pending"] = len([o for o in orders if o.status == "pending"])
        self.statistics["cancelled"] = len([o for o in orders if o.status == "cancelled"])

        # Расчет утилизации курьеров
        busy_couriers = len([c for c in couriers if c.status in ["busy", "emergency"]])
        total_active = len([c for c in couriers if c.status != "offline"])
        if total_active > 0:
            self.statistics["courier_utilization"] = (busy_couriers / total_active) * 100


class TrafficAgent:
    def __init__(self):
        self.traffic_conditions = {
            "normal": {"factor": 1.0, "description": "Нормальное движение"},
            "busy": {"factor": 1.3, "description": "Нагруженное движение"},
            "heavy": {"factor": 1.7, "description": "Пробки"},
            "blocked": {"factor": 3.0, "description": "Дорога перекрыта"}
        }
        self.current_condition = "normal"

    def update_traffic(self, condition):
        if condition in self.traffic_conditions:
            self.current_condition = condition
            return self.traffic_conditions[condition]
        return None

    def get_traffic_factor(self):
        return self.traffic_conditions[self.current_condition]["factor"]