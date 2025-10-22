import socket
import json
import time
import threading
from datetime import datetime
from data_loader import DataLoader
from agents import DispatcherAgent, MonitorAgent, TrafficAgent, OrderAgent, CourierAgent
from config import SERVER_HOST, SERVER_PORT, BUFFER_SIZE


class CourierServer:
    def __init__(self):
        # Загружаем только заказы из файла, курьеров создаем динамически
        data = DataLoader.load_input_data("input_data.json")
        self.dispatcher = DispatcherAgent()
        self.monitor = MonitorAgent()
        self.traffic_agent = TrafficAgent()

        # Создаем заказы из файла
        for order_data in data.get("orders", []):
            order = OrderAgent(
                order_id=order_data["id"],
                destination=order_data["destination"],
                weight=order_data["weight"],
                priority=order_data["priority"],
                time_window=order_data["time_window"],
                description=order_data.get("description", "")
            )
            self.dispatcher.add_order(order)

        self.clients = {}  # {client_socket: {"address": address, "courier_id": id}}
        self.running = True
        self.dispatcher.traffic_data["factor"] = self.traffic_agent.get_traffic_factor()

        print(f"Сервер инициализирован. Заказов: {len(self.dispatcher.orders)}")

    def handle_client(self, client_socket, address):
        """Обрабатывает подключения клиентов"""
        print(f"🔗 Подключен клиент: {address}")
        self.clients[client_socket] = {"address": address, "courier_id": None}

        try:
            buffer = ""
            while self.running:
                try:
                    data = client_socket.recv(BUFFER_SIZE).decode('utf-8')
                    if not data:
                        break

                    buffer += data

                    # Обрабатываем полные сообщения (разделенные \n)
                    while '\n' in buffer:
                        message_str, buffer = buffer.split('\n', 1)
                        if message_str.strip():
                            self.process_message(message_str.strip(), client_socket)

                except socket.timeout:
                    continue
                except ConnectionResetError:
                    break
                except Exception as e:
                    print(f"❌ Ошибка чтения данных от {address}: {e}")
                    break

        except Exception as e:
            print(f"❌ Ошибка с клиентом {address}: {e}")
        finally:
            # Удаляем курьера при отключении
            if client_socket in self.clients:
                courier_id = self.clients[client_socket].get("courier_id")
                if courier_id and courier_id in self.dispatcher.couriers:
                    print(f"🚫 Курьер {courier_id} отключен")
                    # Можно пометить курьера как offline или удалить
                    # self.dispatcher.couriers[courier_id].status = "offline"

                del self.clients[client_socket]
            client_socket.close()
            print(f"🔌 Клиент {address} отключен")

    def process_message(self, message, client_socket):
        """Обрабатывает сообщения от клиентов"""
        try:
            data = json.loads(message)
            message_type = data.get("type")

            print(f"📨 Получено сообщение типа: {message_type} от {self.clients[client_socket]['address']}")

            if message_type == "courier_update":
                self.handle_courier_update(data, client_socket)
            elif message_type == "new_order":
                self.handle_new_order(data)
            elif message_type == "order_delivered":
                self.handle_order_delivered(data)
            elif message_type == "emergency":
                self.handle_emergency(data)
            elif message_type == "traffic_update":
                self.handle_traffic_update(data)
            elif message_type == "get_status":
                self.send_status(client_socket)
            else:
                print(f"❓ Неизвестный тип сообщения: {message_type}")

        except json.JSONDecodeError as e:
            print(f"❌ Ошибка декодирования JSON: {e}")
            print(f"📄 Полученное сообщение: {message}")

    def handle_courier_update(self, data, client_socket):
        """Обновляет данные курьера"""
        courier_id = data["courier_id"]

        # Создаем или обновляем курьера
        if courier_id not in self.dispatcher.couriers:
            # Создаем нового курьера
            courier = CourierAgent(
                agent_id=courier_id,
                location=data["location"],
                transport_type=data["transport_type"],
                max_capacity=50.0,
                name=data.get("name", f"Courier_{courier_id}")
            )
            self.dispatcher.add_courier(courier)
            print(f"👤 Зарегистрирован новый курьер: {courier.name} (ID: {courier_id})")
        else:
            # Обновляем существующего курьера
            courier = self.dispatcher.couriers[courier_id]

        # Обновляем данные
        courier.location = data.get("location", courier.location)
        courier.status = data.get("status", "available")
        courier.transport_type = data.get("transport_type", courier.transport_type)
        courier.name = data.get("name", courier.name)
        courier.last_update = time.time()

        # Сохраняем ID курьера для клиента
        self.clients[client_socket]["courier_id"] = courier_id

        print(f"🔄 Обновлен курьер {courier_id}: {courier.status} в {courier.location}")

        # Автоматически распределяем заказы при подключении курьера
        pending_orders = [o for o in self.dispatcher.orders.values() if o.status == "pending"]
        if pending_orders and courier.status == "available":
            print(f"📦 Автораспределение заказов для курьера {courier_id}...")
            self.dispatcher.assign_orders()
            self.monitor.update_statistics(self.dispatcher)

            # ✅ ВАЖНО: Рассылаем обновленный статус всем клиентам
            self.broadcast_system_status()

    def handle_new_order(self, data):
        """Добавляет новый заказ"""
        order_data = data["order"]
        order_id = order_data["id"]

        if order_id not in self.dispatcher.orders:
            order = OrderAgent(
                order_id=order_data["id"],
                destination=order_data["destination"],
                weight=order_data["weight"],
                priority=order_data["priority"],
                time_window=order_data["time_window"],
                description=order_data.get("description", "")
            )
            self.dispatcher.add_order(order)
            print(f"📝 Добавлен новый заказ: {order_id} - {order.description}")

            # Распределяем заказ
            self.dispatcher.assign_orders()
            self.monitor.update_statistics(self.dispatcher)
            print(f"✅ Заказ {order_id} распределен")

            # ✅ Рассылаем обновленный статус
            self.broadcast_system_status()
        else:
            print(f"⚠️ Заказ {order_id} уже существует")

    def handle_order_delivered(self, data):
        """Отмечает заказ как доставленный"""
        order_id = data["order_id"]
        courier_id = data["courier_id"]

        print(f"🎯 Обработка доставки: заказ {order_id}, курьер {courier_id}")

        if (courier_id in self.dispatcher.couriers and
                order_id in self.dispatcher.orders):

            courier = self.dispatcher.couriers[courier_id]
            order = self.dispatcher.orders[order_id]

            # Помечаем заказ как доставленный
            order.status = "delivered"
            courier.complete_order(order_id)

            print(f"✅ Заказ {order_id} доставлен курьером {courier_id}")

            # Обновляем статистику
            self.monitor.update_statistics(self.dispatcher)

            # Рассылаем обновление статуса
            self.broadcast_system_status()
        else:
            print(f"❌ Ошибка доставки: курьер {courier_id} или заказ {order_id} не найден")

    def handle_emergency(self, data):
        """Обрабатывает чрезвычайную ситуацию"""
        emergency_type = data["emergency_type"]

        if emergency_type == "courier_unavailable":
            courier_id = data["courier_id"]
            self.dispatcher.handle_emergency(courier_id)
            print(f"🚨 Обработана ЧП с курьером {courier_id}")
        elif emergency_type == "traffic_accident":
            self.traffic_agent.update_traffic("heavy")
            self.dispatcher.traffic_data["factor"] = self.traffic_agent.get_traffic_factor()
            print("🚦 Обновлены данные о трафике: пробки из-за аварии")

        self.monitor.update_statistics(self.dispatcher)
        self.broadcast_system_status()

    def handle_traffic_update(self, data):
        """Обновляет данные о трафике"""
        condition = data["condition"]
        result = self.traffic_agent.update_traffic(condition)
        if result:
            self.dispatcher.traffic_data["factor"] = result["factor"]
            print(f"🚦 Обновлено состояние трафика: {result['description']}")
            self.broadcast_system_status()

    def send_status(self, client_socket):
        """Отправляет текущий статус системы клиенту"""
        status_data = self._prepare_status_data()

        try:
            response = json.dumps(status_data, ensure_ascii=False) + "\n"
            client_socket.send(response.encode('utf-8'))
        except Exception as e:
            print(f"❌ Ошибка отправки статуса: {e}")

    def _prepare_status_data(self):
        """Подготавливает данные статуса"""
        # Только активные курьеры (обновленные за последние 5 минут)
        active_couriers = []
        current_time = time.time()
        for courier in self.dispatcher.couriers.values():
            if current_time - courier.last_update < 300:  # 5 минут
                active_couriers.append(courier)

        # Активные назначения
        active_assignments = []
        for assignment in self.dispatcher.assignments:
            courier_id = assignment.get('courier_id')
            if courier_id in [c.id for c in active_couriers]:
                # Проверяем, существует ли еще заказ и он не доставлен
                order_id = assignment.get('order_id')
                if (order_id in self.dispatcher.orders and
                        self.dispatcher.orders[order_id].status != "delivered"):
                    active_assignments.append(assignment)

        # Корректная статистика
        orders_list = list(self.dispatcher.orders.values())
        total_orders = len(orders_list)
        delivered_orders = len([o for o in orders_list if o.status == "delivered"])
        in_progress_orders = len([o for o in orders_list if o.status == "assigned"])
        pending_orders = len([o for o in orders_list if o.status == "pending"])

        # Обновляем статистику монитора
        self.monitor.statistics.update({
            "total_orders": total_orders,
            "delivered": delivered_orders,
            "in_progress": in_progress_orders,
            "pending": pending_orders,
            "courier_utilization": (len([c for c in active_couriers if c.current_orders]) / len(
                active_couriers) * 100) if active_couriers else 0
        })

        return {
            "type": "system_status",
            "couriers": [c.to_dict() for c in active_couriers],
            "orders": [o.to_dict() for o in self.dispatcher.orders.values()],
            "assignments": active_assignments,
            "statistics": self.monitor.statistics,
            "traffic": self.traffic_agent.current_condition,
            "timestamp": datetime.now().isoformat()
        }

    def broadcast_system_status(self):
        """Рассылает статус системы всем клиентам"""
        status_data = self._prepare_status_data()
        self.broadcast_message(status_data)

    def broadcast_message(self, message):
        """Отправляет сообщение всем подключенным клиентам"""
        disconnected_clients = []
        for client_socket in list(self.clients.keys()):
            try:
                response = json.dumps(message, ensure_ascii=False) + "\n"
                client_socket.send(response.encode('utf-8'))
            except:
                disconnected_clients.append(client_socket)

        # Удаляем отключенных клиентов
        for client_socket in disconnected_clients:
            if client_socket in self.clients:
                courier_id = self.clients[client_socket].get("courier_id")
                print(f"🗑️ Удален отключенный клиент (курьер {courier_id})")
                del self.clients[client_socket]

    def periodic_tasks(self):
        """Периодические задачи сервера"""
        while self.running:
            time.sleep(10)

            # Обновляем статистику
            self.monitor.update_statistics(self.dispatcher)

            # Автоматически распределяем заказы
            pending_orders = [o for o in self.dispatcher.orders.values() if o.status == "pending"]
            active_couriers = [c for c in self.dispatcher.couriers.values()
                               if time.time() - c.last_update < 300 and c.status == "available"]

            if pending_orders and active_couriers:
                print(f"🔄 Автораспределение: {len(pending_orders)} заказов, {len(active_couriers)} курьеров")
                self.dispatcher.assign_orders()
                self.monitor.update_statistics(self.dispatcher)
                # ✅ Рассылаем обновление после автораспределения
                self.broadcast_system_status()

            # Рассылаем обновление статуса
            update_msg = {
                "type": "periodic_update",
                "statistics": self.monitor.statistics,
                "timestamp": datetime.now().isoformat()
            }
            self.broadcast_message(update_msg)

            print(f"📊 Сервер: {len(self.clients)} клиентов, {len(self.dispatcher.orders)} заказов, "
                  f"{self.monitor.statistics['delivered']} доставлено")

    def start_server(self):
        """Запускает сервер"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.settimeout(1.0)

        try:
            server_socket.bind((SERVER_HOST, SERVER_PORT))
            server_socket.listen(5)
            print(f"🚀 Сервер запущен на {SERVER_HOST}:{SERVER_PORT}")
            print("⏳ Ожидание подключений...")

            # Запускаем периодические задачи в отдельном потоке
            periodic_thread = threading.Thread(target=self.periodic_tasks)
            periodic_thread.daemon = True
            periodic_thread.start()

            while self.running:
                try:
                    client_socket, address = server_socket.accept()
                    client_socket.settimeout(1.0)
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, address)
                    )
                    client_thread.daemon = True
                    client_thread.start()

                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"❌ Ошибка accept: {e}")

        except KeyboardInterrupt:
            print("\n🛑 Остановка сервера...")
        except Exception as e:
            print(f"❌ Ошибка сервера: {e}")
        finally:
            self.running = False
            server_socket.close()
            # Сохраняем результаты перед выходом
            from data_loader import DataLoader
            DataLoader.save_output_data(self.dispatcher, self.monitor)
            print("🔴 Сервер остановлен")


if __name__ == "__main__":
    server = CourierServer()
    server.start_server()