import socket
import json
import time
import threading
from datetime import datetime
from config import SERVER_HOST, SERVER_PORT


class MonitorClient:
    def __init__(self, server_host=SERVER_HOST, server_port=SERVER_PORT):
        self.server_host = server_host
        self.server_port = server_port
        self.socket = None
        self.connected = False
        self.buffer = ""
        self.auto_refresh = False
        self.last_status = None

    def connect(self):
        """Подключается к серверу"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)
            self.socket.connect((self.server_host, self.server_port))
            self.connected = True
            print(f"✅ Монитор подключен к серверу {self.server_host}:{self.server_port}")

            # Запускаем поток для получения сообщений
            receive_thread = threading.Thread(target=self.receive_messages)
            receive_thread.daemon = True
            receive_thread.start()

            return True
        except Exception as e:
            print(f"❌ Ошибка подключения к {self.server_host}:{self.server_port}: {e}")
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
            return False

    def request_status(self):
        """Запрашивает статус системы"""
        message = {
            "type": "get_status"
        }

        if self.send_message(message):
            # Ждем ответ в основном потоке
            time.sleep(0.5)
            return self.last_status
        return None

    def receive_messages(self):
        """Получает сообщения от сервера"""
        buffer = ""
        while self.connected:
            try:
                data = self.socket.recv(8192).decode('utf-8')
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
                self.last_status = message
                if self.auto_refresh:
                    self.display_status(message)
            elif msg_type == "periodic_update":
                # Автообновление статистики
                stats = message.get("statistics", {})
                if self.auto_refresh:
                    print(f"📡 Автообновление: {stats.get('delivered', 0)} доставлено, "
                          f"{stats.get('pending', 0)} ожидает")

        except json.JSONDecodeError as e:
            print(f"❌ Ошибка декодирования JSON: {e}")

    def display_status(self, status_data):
        """Отображает статус системы"""
        if not status_data:
            print("❌ Нет данных от сервера")
            return False

        print("\n" + "=" * 70)
        print(f"📊 СИСТЕМА ДОСТАВКИ - {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 70)

        # Статистика
        stats = status_data.get("statistics", {})
        delivered = stats.get('delivered', 0)
        total = stats.get('total_orders', 0)
        in_progress = stats.get('in_progress', 0)
        pending = stats.get('pending', 0)
        progress = (delivered / total * 100) if total > 0 else 0

        print(f"📈 СТАТИСТИКА:")
        print(f"   Всего заказов: {total} | ✅ Доставлено: {delivered} | "
              f"🚚 В работе: {in_progress} | ⏳ Ожидает: {pending}")
        print(f"   Прогресс: {progress:.1f}%")
        print(f"   Утилизация курьеров: {stats.get('courier_utilization', 0):.1f}%")

        # Трафик
        traffic = status_data.get("traffic", "normal")
        traffic_icons = {"normal": "🟢", "busy": "🟡", "heavy": "🟠", "blocked": "🔴"}
        traffic_icon = traffic_icons.get(traffic, "⚪")
        print(f"   {traffic_icon} Состояние трафика: {traffic.upper()}")

        # Курьеры
        couriers = status_data.get("couriers", [])
        active_couriers = [c for c in couriers if c.get('status') == 'available']
        busy_couriers = [c for c in couriers if c.get('status') == 'busy']

        print(f"\n🚚 КУРЬЕРЫ ({len(active_couriers) + len(busy_couriers)} всего):")
        print(f"   🟢 Активны: {len(active_couriers)} | 🟡 Заняты: {len(busy_couriers)}")

        if couriers:
            for courier in couriers:
                orders_count = len(courier.get('current_orders', []))
                status = courier.get('status', 'unknown')

                if status == 'available':
                    status_icon = "🟢"
                elif status == 'busy':
                    status_icon = "🟡"
                else:
                    status_icon = "🔴"

                transport_icons = {
                    "car": "🚗", "bicycle": "🚲", "foot": "🚶", "motorcycle": "🏍️"
                }
                transport_icon = transport_icons.get(courier.get('transport_type', ''), '📦')

                print(f"   {status_icon} {transport_icon} {courier['name']}: "
                      f"{orders_count} заказов | {status}")
        else:
            print("   ❌ Нет подключенных курьеров")

        # Активные назначения
        assignments = status_data.get("assignments", [])
        if assignments:
            print(f"\n📋 АКТИВНЫЕ НАЗНАЧЕНИЯ ({len(assignments)}):")
            for assignment in assignments[-8:]:  # Последние 8 назначений
                courier_id = assignment.get('courier_id')
                order_id = assignment.get('order_id')
                estimated_time = assignment.get('estimated_time', '?')

                # Находим имя курьера
                courier_name = f"Курьер {courier_id}"
                for c in couriers:
                    if c.get('id') == courier_id:
                        courier_name = c.get('name', courier_name)
                        break

                print(f"   🚀 {courier_name} → Заказ #{order_id} ({estimated_time})")
        else:
            print(f"\n📋 АКТИВНЫЕ НАЗНАЧЕНИЯ: нет")

        # Ожидающие заказы
        orders = status_data.get("orders", [])
        pending_orders = [o for o in orders if o.get('status') == 'pending']
        if pending_orders:
            print(f"\n⏳ ОЖИДАЮЩИЕ ЗАКАЗЫ ({len(pending_orders)}):")
            for order in pending_orders[:5]:  # Первые 5 заказов
                priority = order.get('priority', 'normal')
                priority_icons = {"high": "🔴", "normal": "🟡", "low": "🔵"}
                priority_icon = priority_icons.get(priority, "⚪")

                print(f"   {priority_icon} #{order['id']}: {order['description']} "
                      f"({order['weight']}кг, {order['time_window']})")

        # Недавно доставленные заказы
        delivered_orders = [o for o in orders if o.get('status') == 'delivered']
        recent_delivered = sorted(delivered_orders,
                                  key=lambda x: x.get('created_time', 0),
                                  reverse=True)[:3]

        if recent_delivered:
            print(f"\n✅ НЕДАВНО ДОСТАВЛЕННЫЕ ({len(recent_delivered)}):")
            for order in recent_delivered:
                print(f"   ✅ #{order['id']}: {order['description']}")

        print("=" * 70)
        return True

    def start_auto_refresh(self, interval=5):
        """Запускает автоматическое обновление статуса"""
        if not self.connected:
            print("❌ Нет подключения к серверу")
            return

        print(f"🔄 Запуск автообновления (каждые {interval} сек)...")
        self.auto_refresh = True

        try:
            while self.connected and self.auto_refresh:
                # Запрашиваем статус
                self.send_message({"type": "get_status"})
                time.sleep(interval)

        except KeyboardInterrupt:
            print("⏹️ Автообновление прервано")
        except Exception as e:
            print(f"❌ Ошибка автообновления: {e}")

    def stop_auto_refresh(self):
        """Останавливает автоматическое обновление"""
        self.auto_refresh = False
        print("⏹️ Автообновление остановлено")

    def interactive_mode(self):
        """Интерактивный режим управления"""
        if not self.connected:
            return

        print("\n🎮 ИНТЕРАКТИВНЫЙ РЕЖИМ УПРАВЛЕНИЯ")
        self.show_help()

        # Показываем начальный статус
        print("\n🔄 Получаем текущий статус...")
        self.send_message({"type": "get_status"})
        time.sleep(1)
        if self.last_status:
            self.display_status(self.last_status)

        while self.connected:
            try:
                command = input("\n💻 Введите команду: ").strip().lower()

                if command in ["quit", "exit", "q"]:
                    break
                elif command == "status":
                    print("🔄 Обновление статуса...")
                    self.send_message({"type": "get_status"})
                    time.sleep(0.5)
                    if self.last_status:
                        self.display_status(self.last_status)
                    else:
                        print("❌ Не удалось получить статус")
                elif command == "traffic":
                    self.handle_traffic_command()
                elif command == "emergency":
                    self.handle_emergency_command()
                elif command == "add_order":
                    self.add_test_order()
                elif command == "auto_on":
                    self.start_auto_refresh_in_thread()
                elif command == "auto_off":
                    self.stop_auto_refresh()
                elif command == "help":
                    self.show_help()
                elif command == "":
                    continue
                else:
                    print(f"❌ Неизвестная команда: '{command}'")
                    print("   Введите 'help' для списка команд")

            except KeyboardInterrupt:
                print("\n🛑 Завершение работы...")
                break
            except Exception as e:
                print(f"❌ Ошибка: {e}")

    def show_help(self):
        """Показывает справку по командам"""
        print("\n📋 ДОСТУПНЫЕ КОМАНДЫ:")
        print("  status    - показать текущий статус системы")
        print("  traffic   - изменить состояние трафика")
        print("  emergency - сообщить о ЧП")
        print("  add_order - добавить тестовый заказ")
        print("  auto_on   - включить автообновление (каждые 5 сек)")
        print("  auto_off  - выключить автообновление")
        print("  help      - показать эту справку")
        print("  quit      - выйти из программы")

    def handle_traffic_command(self):
        """Обрабатывает команду изменения трафика"""
        print("🚦 ДОСТУПНЫЕ СОСТОЯНИЯ ТРАФИКА:")
        print("  normal  - 🟢 Нормальное движение")
        print("  busy    - 🟡 Нагруженное движение")
        print("  heavy   - 🟠 Пробки")
        print("  blocked - 🔴 Дорога перекрыта")

        condition = input("📝 Введите состояние: ").strip().lower()
        if condition in ["normal", "busy", "heavy", "blocked"]:
            if self.send_message({
                "type": "traffic_update",
                "condition": condition
            }):
                print(f"✅ Отправлено обновление трафика: {condition}")
            else:
                print("❌ Ошибка отправки обновления трафика")
        else:
            print("❌ Неверное состояние. Используйте: normal, busy, heavy, blocked")

    def handle_emergency_command(self):
        """Обрабатывает команду ЧП"""
        print("🚨 ТИПЫ ЧРЕЗВЫЧАЙНЫХ СИТУАЦИЙ:")
        print("  courier_unavailable - 📦 Курьер недоступен")
        print("  traffic_accident    - 🚗 Дорожная авария")

        emergency_type = input("📝 Введите тип ЧП: ").strip().lower()
        description = input("📄 Описание: ").strip()

        if emergency_type in ["courier_unavailable", "traffic_accident"]:
            if self.send_message({
                "type": "emergency",
                "emergency_type": emergency_type,
                "description": description
            }):
                print(f"✅ Отправлено сообщение о ЧП: {emergency_type}")
            else:
                print("❌ Ошибка отправки сообщения о ЧП")
        else:
            print("❌ Неверный тип ЧП. Используйте: courier_unavailable, traffic_accident")

    def add_test_order(self):
        """Добавляет тестовый заказ"""
        import random

        order_id = random.randint(1000, 9999)
        order_data = {
            "type": "new_order",
            "order": {
                "id": order_id,
                "destination": [
                    55.75 + random.uniform(-0.02, 0.02),
                    37.62 + random.uniform(-0.02, 0.02)
                ],
                "weight": round(random.uniform(1, 15), 1),
                "priority": random.choice(["high", "normal", "normal", "low"]),
                "time_window": f"{random.randint(10, 16)}:00-{random.randint(17, 20)}:00",
                "description": f"Тестовый заказ #{order_id}"
            }
        }

        if self.send_message(order_data):
            print(f"✅ Добавлен тестовый заказ #{order_id}")
            # Запрашиваем обновленный статус
            self.send_message({"type": "get_status"})
        else:
            print("❌ Ошибка добавления заказа")

    def start_auto_refresh_in_thread(self):
        """Запускает автообновление в отдельном потоке"""
        import threading
        if not self.auto_refresh:
            refresh_thread = threading.Thread(target=self.start_auto_refresh)
            refresh_thread.daemon = True
            refresh_thread.start()
            print("✅ Автообновление включено (обновление каждые 5 сек)")
        else:
            print("ℹ️ Автообновление уже запущено")

    def disconnect(self):
        """Отключается от сервера"""
        self.auto_refresh = False
        self.connected = False
        if self.socket:
            self.socket.close()
        print("🔌 Отключено от сервера")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Клиент мониторинга системы доставки')
    parser.add_argument('--host', default=SERVER_HOST, help='Адрес сервера')
    parser.add_argument('--port', type=int, default=SERVER_PORT, help='Порт сервера')

    args = parser.parse_args()

    monitor = MonitorClient(server_host=args.host, server_port=args.port)

    if monitor.connect():
        try:
            monitor.interactive_mode()
        except KeyboardInterrupt:
            print("\n🛑 Завершение работы монитора...")
        finally:
            monitor.disconnect()
    else:
        print("❌ Не удалось подключиться к серверу")


if __name__ == "__main__":
    main()