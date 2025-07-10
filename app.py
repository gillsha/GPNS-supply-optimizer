from flask import Flask, render_template, request
from models import db, Warehouse, Client
import pulp
import folium
import requests
from geopy.distance import geodesic
import certifi
import ssl

app = Flask(__name__)
app.config.from_object("config.Config")
db.init_app(app)

# API-ключ для Яндекс.Маршрутизации
YANDEX_API_KEY = "тут ключ"

# Грузоподъемности машин (в кг)
VEHICLE_CAPACITY = [1500, 10000, 20000, 45000, 20000, 20000, 20000, 20000, 20000, 20000, 20000, 20000]


def get_yandex_route(start_coords, end_coords):
    """Получение маршрута между двумя точками с использованием Яндекс API."""
    url = "https://api.routing.yandex.net/v2/route"
    params = {
        "apikey": YANDEX_API_KEY,
        "waypoints": f"{start_coords[1]},{start_coords[0]}|{end_coords[1]},{end_coords[0]}",
        "mode": "driving"
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()["routes"][0]["geometry"]["coordinates"]
    else:
        print("Ошибка при получении маршрута:", response.text)
        return None


def solve_transportation_with_vehicles(supply, demand, vehicle_capacity, costs):
    """Решение задачи с ограничениями на грузоподъемность машин."""
    model = pulp.LpProblem("Transport_With_Vehicles", pulp.LpMinimize)

    # Переменные: отгрузка со склада на машине k
    routes = pulp.LpVariable.dicts("Route", [(i, k) for i in supply for k in range(len(vehicle_capacity))],
                                   lowBound=0, cat="Continuous")

    # Целевая функция: минимизация стоимости
    model += pulp.lpSum(routes[(i, k)] * costs[i] for i in supply for k in range(len(vehicle_capacity)))

    # Ограничение: объем с каждого склада <= остатка
    for i in supply:
        model += pulp.lpSum(routes[(i, k)] for k in range(len(vehicle_capacity))) <= supply[i]

    # Ограничение: суммарная поставка клиенту >= его потребности
    model += pulp.lpSum(routes[(i, k)] for i in supply for k in range(len(vehicle_capacity))) >= demand

    # Ограничение: объем каждой машины <= ее грузоподъемности
    for k in range(len(vehicle_capacity)):
        for i in supply:
            model += pulp.lpSum(routes[(i, k)]) <= vehicle_capacity[k]

    # Решаем задачу
    model.solve()

    results = []
    for i in supply:
        for k in range(len(vehicle_capacity)):
            if routes[(i, k)].value() > 0:
                results.append((i, k, routes[(i, k)].value()))
    return results


def generate_map(routes, warehouses, client_coords):
    """Генерация карты с маршрутами на основе Яндекс API."""
    m = folium.Map(location=[client_coords[0], client_coords[1]], zoom_start=4)

    # Добавляем склады
    for w_name, w_coords in warehouses.items():
        folium.Marker(w_coords, popup=w_name, icon=folium.Icon(color="blue")).add_to(m)

    # Добавляем клиента
    folium.Marker(client_coords, popup="Клиент", icon=folium.Icon(color="red")).add_to(m)

    # Добавляем маршруты
    for w_name, vehicle_idx, volume in routes:
        route_coords = get_yandex_route(warehouses[w_name], client_coords)
        if route_coords:
            folium.PolyLine(route_coords, color="green", weight=2.5,
                            popup=f"{w_name} -> Клиент, Машина {vehicle_idx + 1}, Объем: {volume:.0f} кг").add_to(m)
    return m._repr_html_()


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Получаем данные из БД
        warehouses = Warehouse.query.all()
        client = Client.query.first()

        # Формируем данные для задачи
        supply = {w.name: w.supply for w in warehouses}
        demand = client.demand
        warehouse_coords = {w.name: (w.latitude, w.longitude) for w in warehouses}
        client_coords = (client.latitude, client.longitude)

        # Рассчитываем стоимость доставки
        costs = {w.name: geodesic(warehouse_coords[w.name], client_coords).kilometers * 100 for w in warehouses}

        # Решаем транспортную задачу
        routes = solve_transportation_with_vehicles(supply, demand, VEHICLE_CAPACITY, costs)

        # Генерируем карту
        map_html = generate_map(routes, warehouse_coords, client_coords)

        return render_template("map.html", map_html=map_html)

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)