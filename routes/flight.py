from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from database import Session as DatabaseSession
from models import Users, Techniques, TypeTechniques, FlightNums
from pytz import timezone
import gspread
from datetime import datetime
import logging
from typing import List, Union
from babel.dates import format_date
from typing import Optional
from pydantic import BaseModel
import requests
from fastapi import  HTTPException
import json
from sqlalchemy import func
from datetime import date

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")

router = APIRouter()

def get_db():
    db = DatabaseSession()
    try:
        yield db
    finally:
        db.close()


def get_next_flight_number(db: Session):
    today = date.today()

    # Находим максимальный номер рейса за сегодня
    last_flight = db.query(func.max(FlightNums.flight_number)).filter(FlightNums.date == today).scalar()

    if last_flight is None:
        return 1  # Если рейсов за сегодня нет, начинаем с 1
    else:
        return last_flight + 1  # Иначе увеличиваем номер на 1

class EquipmentForm(BaseModel):
    equipment_type: str
    prepayment_amount: float
    prepayment: bool
    payment_type: str
    client_source: str
    hotel_list: Optional[str] = None 
    comment: str
    discount: float
    cost: float  # Добавляем поле для стоимости
    equipment_name: str

class IncomeData(BaseModel):
    user_id: int
    date: str
    flight_number: str
    instructor: str
    route_type: str
    equipment_forms: List[EquipmentForm]

@router.get("/flight", response_class=HTMLResponse)
async def directory(request: Request, user_id: int, db: Session = Depends(get_db)):
    try:
        instructors = db.query(Users).all()
        techniques = db.query(Techniques).all()
        type_techniques = db.query(TypeTechniques).all()

        # Сопоставляем технику с её типом
        techniques_with_types = []
        for technique in techniques:
            type_technique = next((tt for tt in type_techniques if tt.id == technique.type_technique_id), None)
            techniques_with_types.append({
                "id": technique.id,
                "title": technique.title,
                "type_technique_title": type_technique.title if type_technique else "Неизвестный тип"
            })

        # Получаем следующий номер рейса
        next_flight_number = get_next_flight_number(db)

        # Список всех номеров рейсов (от 1 до 20)
        all_flight_numbers = list(range(1, 21))

        return templates.TemplateResponse(
            "flight.html",
            {
                "request": request,
                "instructors": instructors,
                "techniques": techniques_with_types,
                "user_id": user_id,
                "next_flight_number": next_flight_number,  # Следующий номер рейса
                "all_flight_numbers": all_flight_numbers  # Список всех номеров
            },
        )
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных: {str(e)}")
        return JSONResponse(content={"message": "Ошибка сервера"}, status_code=500)


async def send_telegram_message(user_id: int, message: str):
    bot_token = "8125373869:AAFKywhECD_BqwUgaGvsQUpv_zSZeHiWDqI"
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    keyboard = {
        "inline_keyboard": [
            [{"text": "Отправить", "callback_data": "send"}],
            [{"text": "Удалить", "callback_data": "delete"}]
        ]
    }

    payload = {
        "chat_id": user_id,
        "text": message,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(keyboard)  # Преобразуем словарь в JSON строку
    }

    response = requests.post(url, json=payload)
    if response.status_code != 200:
        raise Exception("Ошибка при отправке сообщения в Telegram")

    # Возвращаем данные о сообщении, включая message_id
    return response.json()



@router.post("/submit_income")
async def submit_income(data: IncomeData, db: Session = Depends(get_db)):
    user_id = data.user_id

    # Сохраняем информацию о рейсе
    new_flight = FlightNums(date=date.today(), flight_number=data.flight_number)
    db.add(new_flight)
    db.commit()

    for equipment in data.equipment_forms:
        # Формируем источник клиента
        client_source = equipment.client_source
        if equipment.hotel_list:  # Если есть отель, добавляем его к источнику
            client_source += f" - {equipment.hotel_list}"
        equipment_message = (
            f"Дата: {data.date}\n"
            f"Номер рейса: {data.flight_number}\n"
            f"Инструктор: {data.instructor}\n"
            f"Маршрут: {data.route_type}\n"
            f"<b>Техника:</b>\n"
            f"Машина: {equipment.equipment_name}\n"
            f"Сумма предоплаты: {equipment.prepayment_amount}\n"
            f"Скидка: {equipment.discount}\n"
            f"Предоплата: {'Да' if equipment.prepayment else 'Нет'}\n"
            f"Тип оплаты: {equipment.payment_type}\n"
            f"Источник клиента: {client_source}\n"  
            f"Комментарий: {equipment.comment}\n"
            f"<b>Стоимость: {equipment.cost} руб.</b>\n"
        )
        await send_telegram_message(user_id, equipment_message)

    return JSONResponse(content={"message": "Данные успешно отправлены!"})