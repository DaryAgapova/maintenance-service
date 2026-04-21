from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.models import User, Equipment, Ticket, TicketHistory, Comment, Notification
from app.routers import auth, tickets
from app.routers import admin
from app.auth import hash_password
from app.database import SessionLocal

app = FastAPI(title="Сервис учёта заявок на ТО")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(admin.router)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "admin@mail.ru").first():
            db.add(User(
                full_name="Администратор",
                email="admin@mail.ru",
                password_hash=hash_password("admin123"),
                role="admin"
            ))
        if not db.query(User).filter(User.email == "tech@mail.ru").first():
            db.add(User(
                full_name="Иванов Иван (техник)",
                email="tech@mail.ru",
                password_hash=hash_password("tech123"),
                role="technician"
            ))
        if not db.query(User).filter(User.email == "client@mail.ru").first():
            db.add(User(
                full_name="Петрова Мария (клиент)",
                email="client@mail.ru",
                password_hash=hash_password("client123"),
                role="client"
            ))
        db.commit()
    finally:
        db.close()
