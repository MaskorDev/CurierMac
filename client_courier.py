import socket
import json
import time
import random
import threading
from config import SERVER_HOST, SERVER_PORT


class CourierClient:
    def __init__(self, courier_id, name="", location=None, transport_type="car"):
        self.courier_id = courier_id
        self.name = name or f"Courier_{courier_id}"
        self.location = location or [55.75 + random.uniform(-0.01, 0.01),
                                     37.62 + random.uniform(-0.01, 0.01)]
        self.transport_type = transport_type
        self.socket = None
        self.connected = False
        self.assigned_orders = []

    def connect(self):
        """Подключается к серверу"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)
            self.socket.connect((SERVER_HOST, SERVER_PORT))
            self.connected = True
            print(f"✅ Курьер {self.name} подключен к серверу")

            # Регистрируем курьера на сервере
            self.send_courier_update()

            # Запускаем поток для получения сообщений
            receive_thread = threading.Thread(target=self.receive_messages)
            receive_thread.daemon = True
            receive_thread.start()

            return True
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False

    def send_message(self, message):
        """Отправляет сообщение на сервер"""
        if not self.connected:
            return False

        try:
            data = json.dumps(message, ensure_ascii=False) + "\n"
            self.socket.send(data.encode('utf-8'))
            return True
        except Exception as e:
            print(f"❌ Ошибка отправки сообщения: {e}")
            self.connected = False
            return False

    def send_courier_update(self):
        """Отправляет обновление статуса курьера"""
        message = {
            "type": "courier_update",
            "courier_id": self.courier_id,
            "location": self.location,
            "status": "available",
            "name": self.name,
            "transport_type": self.transport_type
        }

        return self.send_message(message)

    def send_order_delivered(self, order_id):
        """Отправляет уведомление о доставке заказа"""
        message = {
            "type": "order_delivered",
            "courier_id": self.courier_id,
            "order_id": order_id
        }

        if self.send_message(message):
            print(f"✅ Заказ {order_id} отмечен как доставленный")
            return True
        return False

    def receive_messages(self):
        """Получает сообщения от сервера"""
        buffer = ""
        while self.connected:
            try:
                data = self.socket.recv(4096).decode('utf-8')
                if not data:
                    break

                buffer += data

                # Обрабатываем полные сообщения (разделенные \n)
                while '\n' in buffer:
                    message_str, buffer = buffer.split('\n', 1)
                    if message_str.strip():
                        self.handle_server_message(message_str.strip())

            except socket.timeout:
                continue
            except Exception as e:
                print(f"❌ Ошибка получения сообщений: {e}")
                break

        self.connected = False
        print("🔌 Соединение с сервером разорвано")

    def handle_server_message(self, message_str):
        """Обрабатывает сообщения от сервера"""
        try:
            message = json.loads(message_str)
            msg_type = message.get("type")

            if msg_type == "system_status":
                self.handle_system_status(message)
            elif msg_type == "periodic_update":
                self.handle_periodic_update(message)

        except json.JSONDecodeError as e:
            print(f"❌ Ошибка декодирования JSON: {e}")

    def handle_system_status(self, message):
        """Обрабатывает статус системы"""
        # Обновляем список наших заказов
        assignments = message.get("assignments", [])
        my_assignments = [a for a in assignments if a.get("courier_id") == self.courier_id]

        # Находим новые заказы
        new_orders = []
        for assignment in my_assignments:
            order_id = assignment.get("order_id")
            if order_id and order_id not in self.assigned_orders:
                new_orders.append(order_id)
                self.assigned_orders.append(order_id)

        if new_orders:
            print(f"🎯 Получены новые заказы: {new_orders}")

        # Статистика
        stats = message.get("statistics", {})
        pending = stats.get('pending', 0)
        delivered = stats.get('delivered', 0)

        print(f"📊 Статистика: {delivered} доставлено, {pending} ожидает, мои заказы: {len(my_assignments)}")

    def handle_periodic_update(self, message):
        """Обрабатывает периодическое обновление"""
        stats = message.get("statistics", {})
        pending = stats.get('pending', 0)
        delivered = stats.get('delivered', 0)
        print(f"📡 Обновление: {delivered} доставлено, {pending} ожидает")

    def simulate_work(self):
        """Имитирует работу курьера"""
        if not self.connected:
            print("❌ Нет подключения к серверу")
            return

        print(f"🚀 Курьер {self.name} начинает работу...")
        print("💡 Нажмите Ctrl+C для остановки")

        try:
            work_cycle = 0
            while self.connected:
                time.sleep(20)  # Уменьшил интервал для более быстрой реакции
                work_cycle += 1

                # Обновляем местоположение
                self.location[0] += random.uniform(-0.001, 0.001)
                self.location[1] += random.uniform(-0.001, 0.001)

                if self.send_courier_update():
                    if work_cycle % 5 == 0:  # Реже выводим местоположение
                        print(f"📍 Обновлено местоположение")

                # Имитируем доставку заказа (каждые 3 цикла)
                if work_cycle % 3 == 0 and self.assigned_orders:
                    order_id = self.assigned_orders.pop(0)
                    if self.send_order_delivered(order_id):
                        print(f"📦 Заказ {order_id} доставлен. Осталось: {len(self.assigned_orders)}")
                    else:
                        # Если не удалось отправить, возвращаем заказ
                        self.assigned_orders.insert(0, order_id)

                # Случайное событие ЧП (очень малая вероятность)
                if random.random() < 0.01:  # 1% шанс
                    print("🚨 ЧП: курьер сообщает о проблеме!")
                    # Не разрываем соединение, просто сообщаем
                    time.sleep(5)

        except KeyboardInterrupt:
            print("\n🛑 Работа курьера прервана пользователем")
        except Exception as e:
            print(f"❌ Ошибка в работе курьера: {e}")

    def disconnect(self):
        """Отключается от сервера"""
        self.connected = False
        if self.socket:
            self.socket.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Клиент курьера')
    parser.add_argument('--id', type=int, required=True, help='ID курьера')
    parser.add_argument('--name', help='Имя курьера')
    parser.add_argument('--transport', choices=['foot', 'bicycle', 'car', 'motorcycle'],
                        default='car', help='Тип транспорта')

    args = parser.parse_args()

    # Случайное начальное местоположение в Москве
    base_lat, base_lon = 55.751244, 37.618423
    location = [
        base_lat + random.uniform(-0.02, 0.02),
        base_lon + random.uniform(-0.02, 0.02)
    ]

    courier = CourierClient(
        courier_id=args.id,
        name=args.name,
        location=location,
        transport_type=args.transport
    )

    if courier.connect():
        try:
            courier.simulate_work()
        except KeyboardInterrupt:
            print("👋 Завершение работы...")
        finally:
            courier.disconnect()
    else:
        print("❌ Не удалось подключиться к серверу")


if __name__ == "__main__":
    main()