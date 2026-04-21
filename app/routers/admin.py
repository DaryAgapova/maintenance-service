from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db
from ..models import User, Equipment, Ticket
from ..auth import get_current_user, hash_password, require_admin

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def admin_index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    users = db.query(User).all()
    equipment_list = db.query(Equipment).all()
    total_tickets = db.query(func.count(Ticket.id)).scalar()
    open_tickets = db.query(func.count(Ticket.id)).filter(
        Ticket.status.in_(["new", "in_progress"])
    ).scalar()
    workload = db.query(User.full_name, func.count(Ticket.id)).join(
        Ticket, Ticket.assignee_id == User.id
    ).filter(Ticket.status.in_(["new", "in_progress"])).group_by(User.id).all()
    return templates.TemplateResponse(request, "admin/index.html", {
        "current_user": current_user,
        "users": users,
        "equipment_list": equipment_list,
        "total_tickets": total_tickets,
        "open_tickets": open_tickets,
        "workload": workload,
    })


@router.post("/users/add")
def add_user(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email уже занят")
    db.add(User(
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
        role=role
    ))
    db.commit()
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/equipment/add")
def add_equipment(
    name: str = Form(...),
    inventory_number: str = Form(""),
    location: str = Form(""),
    category: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    db.add(Equipment(
        name=name,
        inventory_number=inventory_number or None,
        location=location or None,
        category=category or None
    ))
    db.commit()
    return RedirectResponse(url="/admin", status_code=302)
