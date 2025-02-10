import io
import logging.config
import os
import re
import zipfile
from environs import Env

import pandas as pd
import requests

logger = logging.getLogger(__file__)


def get_product_list(last_id, client_id, seller_token):
    """Получить список товаров магазина озон.

    Args:
        last_id (str): Идентификатор последнего значения на странице.
        client_id (str): Идентификатор клиента.
        seller_token (str): Токен продавца.

    Returns:
        list: Список товаров.

    Example:
        "items": [
            {
                "product_id": 223681945,
                "offer_id": "136748"
            }
        ],
        "total": 1,
        "last_id": "bnVсbA=="

    """
    url = "https://api-seller.ozon.ru/v2/product/list"
    headers = {
        "Client-Id": client_id,
        "Api-Key": seller_token,
    }
    payload = {
        "filter": {
            "visibility": "ALL",
        },
        "last_id": last_id,
        "limit": 1000,
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    response_object = response.json()
    return response_object.get("result")


def get_offer_ids(client_id, seller_token):
    """Получить артикулы товаров магазина озон.

    Args:
        client_id (str): Идентификатор клиента.
        seller_token (str): Токен продавца.

    Returns:
        list: Список с ids товаров.

    Example:
        ["136834","164834", "136534"]

    """
    last_id = ""
    product_list = []
    while True:
        some_prod = get_product_list(last_id, client_id, seller_token)
        product_list.extend(some_prod.get("items"))
        total = some_prod.get("total")
        last_id = some_prod.get("last_id")
        if total == len(product_list):
            break
    offer_ids = []
    for product in product_list:
        offer_ids.append(product.get("offer_id"))
    return offer_ids


def update_price(prices: list, client_id, seller_token):
    """Обновить цены товаров.

    Args:
        client_id (str): Идентификатор клиента.
        seller_token (str): Токен продавца.
        prices (list): Информация о ценах товаров.

    Returns:
        dict: Статус запроса. Ответ от API.

    Example:
        {
            "result":
            [
                {
                    "product_id": 1386,
                    "offer_id": "PH8865",
                    "updated": true,
                    "errors": [ ]
                }
            ]
        }

    """
    url = "https://api-seller.ozon.ru/v1/product/import/prices"
    headers = {
        "Client-Id": client_id,
        "Api-Key": seller_token,
    }
    payload = {"prices": prices}
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def update_stocks(stocks: list, client_id, seller_token):
    """Обновить остатки.

    Args:
        client_id (str): Идентификатор клиента.
        seller_token (str): Токен продавца.
        stocks (list): Информация о товарах на складах.

    Returns:
        dict: Статус запроса. Ответ от API.

    Example:
        {
            "result":
            [
                {
                    "warehouse_id": 22142605386000,
                    "product_id": 118597312,
                    "quant_size": 1,
                    "offer_id": "PH11042",
                    "updated": true,
                    "errors": [ ]
                }
            ]
        }

    """
    url = "https://api-seller.ozon.ru/v1/product/import/stocks"
    headers = {
        "Client-Id": client_id,
        "Api-Key": seller_token,
    }
    payload = {"stocks": stocks}
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def download_stock():
    """Скачать файл ostatki с сайта casio и сделать список с остатками часов.

    Returns:
        list: Остатки часов.

    Example:
        При корректном скачивании файла, функция возвратит содержание exel документа.
        [
            {
                "Код": "1",
                "Наименование товара": "cas",
                "Изображение": "link",
                "Цена": "123",
                "Количество" : "12",
                "Заказ", None,
            },
        ]

    """
    # Скачать остатки с сайта
    casio_url = "https://timeworld.ru/upload/files/ostatki.zip"
    session = requests.Session()
    response = session.get(casio_url)
    response.raise_for_status()
    with response, zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        archive.extractall(".")
    # Создаем список остатков часов:
    excel_file = "ostatki.xls"
    watch_remnants = pd.read_excel(
        io=excel_file,
        na_values=None,
        keep_default_na=False,
        header=17,
    ).to_dict(orient="records")
    os.remove("./ostatki.xls")  # Удалить файл
    return watch_remnants


def create_stocks(watch_remnants, offer_ids):
    """Составление наличия товаров на основе имеющихся на озоне.

    Если каких либо товаров не было на озоне, то их наличие равно нулю.

    Args:
        watch_remnants (list): Остатки часов.
        offer_ids (str): Идентификатор в системе продавца - артикул.

    Returns:
        list: Наличие товара.

    Example:
        [
            {
                "offer_id": "143210608",
                "stock": 15,
            },
        ]

    """
    # Уберем то, что не загружено в seller
    stocks = []
    for watch in watch_remnants:
        if str(watch.get("Код")) in offer_ids:
            count = str(watch.get("Количество"))
            if count == ">10":
                stock = 100
            elif count == "1":
                stock = 0
            else:
                stock = int(watch.get("Количество"))
            stocks.append({"offer_id": str(watch.get("Код")), "stock": stock})
            offer_ids.remove(str(watch.get("Код")))
    # Добавим недостающее из загруженного:
    for offer_id in offer_ids:
        stocks.append({"offer_id": offer_id, "stock": 0})
    return stocks


def create_prices(watch_remnants, offer_ids):
    """Составление цен на товары для Озона.

    Цена соответствует цене магазина Casio.

    Args:
        watch_remnants (list): Остатки часов.
        offer_ids (str): Идентификатор в системе продавца - артикул.

    Returns:
        list: Список цен на товары.

    Example:
        [
            {
                "auto_action_enabled": "UNKNOWN",
                "currency_code": "RUB",
                "offer_id": "087987",
                "old_price": "0",
                "price": "5990",
            }
        ]

    """
    prices = []
    for watch in watch_remnants:
        if str(watch.get("Код")) in offer_ids:
            price = {
                "auto_action_enabled": "UNKNOWN",
                "currency_code": "RUB",
                "offer_id": str(watch.get("Код")),
                "old_price": "0",
                "price": price_conversion(watch.get("Цена")),
            }
            prices.append(price)
    return prices


def price_conversion(price: str) -> str:
    """Преобразовать цену.

    Расширенное описание функции.

    Args:
        price (str): Стоимость товара.

    Returns:
        str: Преобразованное значние стоимости.

    Example:

        >>> price="5'990.00"
        >>> price_conversion(price)
        5990

    Incorrect example:
        >>> price=123
        >>> price_conversion(price)
        Traceback (most recent call last):
        AttributeError: 'int' object has no attribute 'split'

    """
    return re.sub("[^0-9]", "", price.split(".")[0])


def divide(lst: list, n: int):
    """Разделить список lst на части по n элементов.

    Args:
        list (str): Список
        n (int): Количество элементов в одной части.

    Returns:
        list: Список состоящий из частей по n элементов.

    Example:
        Для списка, который состоит из последовательности чисел от 10 до 75 включительно при n=10:
        [[10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
        [20, 21, 22, 23, 24, 25, 26, 27, 28, 29],
        [30, 31, 32, 33, 34, 35, 36, 37, 38, 39],
        [40, 41, 42, 43, 44, 45, 46, 47, 48, 49],
        [50, 51, 52, 53, 54, 55, 56, 57, 58, 59],
        [60, 61, 62, 63, 64, 65, 66, 67, 68, 69],
        [70, 71, 72, 73, 74]]

    """
    for i in range(0, len(lst), n):
        yield lst[i: i + n]


async def upload_prices(watch_remnants, client_id, seller_token):
    """Обновление цен товаров в магазине Озон.

    Args:
        watch_remnants (list): Остатки часов.
        client_id (str): Идентификатор клиента.
        seller_token (str): Токен продавца.

    Returns:
        list: Список цен на товары.

    Example:
        [
            {
                "auto_action_enabled": "UNKNOWN",
                "currency_code": "RUB",
                "offer_id": "087987",
                "old_price": "0",
                "price": "5990",
            }
        ]

    """
    offer_ids = get_offer_ids(client_id, seller_token)
    prices = create_prices(watch_remnants, offer_ids)
    for some_price in list(divide(prices, 1000)):
        update_price(some_price, client_id, seller_token)
    return prices


async def upload_stocks(watch_remnants, client_id, seller_token):
    """Обновление наличия товаров в магазине Озон.

    Args:
        watch_remnants (list): Остатки часов.
        client_id (str): Идентификатор клиента.
        seller_token (str): Токен продавца.

    Returns:
        list: Наличие товара.
        list: Товары, которых нет в наличии.

    Example:
        [
            {
                "offer_id": "143210608",
                "stock": 15,
            },
        ]

        [
            {
                "offer_id": "1432=43608",
                "stock": 0,
            },
        ]

    """
    offer_ids = get_offer_ids(client_id, seller_token)
    stocks = create_stocks(watch_remnants, offer_ids)
    for some_stock in list(divide(stocks, 100)):
        update_stocks(some_stock, client_id, seller_token)
    not_empty = list(filter(lambda stock: (stock.get("stock") != 0), stocks))
    return not_empty, stocks


def main():
    env = Env()
    seller_token = env.str("SELLER_TOKEN")
    client_id = env.str("CLIENT_ID")
    try:
        offer_ids = get_offer_ids(client_id, seller_token)
        watch_remnants = download_stock()
        # Обновить остатки
        stocks = create_stocks(watch_remnants, offer_ids)
        for some_stock in list(divide(stocks, 100)):
            update_stocks(some_stock, client_id, seller_token)
        # Поменять цены
        prices = create_prices(watch_remnants, offer_ids)
        for some_price in list(divide(prices, 900)):
            update_price(some_price, client_id, seller_token)
    except requests.exceptions.ReadTimeout:
        print("Превышено время ожидания...")
    except requests.exceptions.ConnectionError as error:
        print(error, "Ошибка соединения")
    except Exception as error:
        print(error, "ERROR_2")


if __name__ == "__main__":
    main()
