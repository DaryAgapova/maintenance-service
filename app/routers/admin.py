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
    workload_raw = db.query(User.id, User.full_name, func.count(Ticket.id)).join(
        Ticket, Ticket.assignee_id == User.id
    ).filter(Ticket.status.in_(["new", "in_progress"])).group_by(User.id).all()
    workload = [(name, count) for _, name, count in workload_raw]
    workload_ids = [uid for uid, _, _ in workload_raw]
    return templates.TemplateResponse(request, "admin/index.html", {
        "current_user": current_user,
        "users": users,
        "equipment_list": equipment_list,
        "total_tickets": total_tickets,
        "open_tickets": open_tickets,
        "workload": workload,
        "workload_ids": workload_ids,
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

@router.get("/technician/{user_id}", response_class=HTMLResponse)
def technician_detail(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    technician = db.query(User).filter(User.id == user_id).first()
    if not technician:
        raise HTTPException(status_code=404)
    
    tickets = db.query(Ticket).filter(Ticket.assignee_id == user_id).order_by(Ticket.created_at.desc()).all()
    
    total = len(tickets)
    active = len([t for t in tickets if t.status in ["new", "in_progress"]])
    done = len([t for t in tickets if t.status == "done"])
    closed = len([t for t in tickets if t.status == "closed"])
    
    # Среднее время закрытия в часах
    closed_tickets = [t for t in tickets if t.closed_at]
    if closed_tickets:
        avg_hours = sum(
            (t.closed_at - t.created_at).total_seconds() / 3600
            for t in closed_tickets
        ) / len(closed_tickets)
    else:
        avg_hours = None

    return templates.TemplateResponse(request, "admin/technician.html", {
        "current_user": current_user,
        "technician": technician,
        "tickets": tickets,
        "total": total,
        "active": active,
        "done": done,
        "closed": closed,
        "avg_hours": avg_hours,
        "status_labels": {"new": "Новая", "in_progress": "В работе", "done": "Выполнена", "closed": "Закрыта"},
        "status_colors": {"new": "secondary", "in_progress": "primary", "done": "success", "closed": "dark"},
        "priority_labels": {"low": "Низкий", "medium": "Средний", "high": "Высокий", "critical": "Критический"},
        "priority_colors": {"low": "success", "medium": "warning", "high": "danger", "critical": "danger"},
    })
@router.get("/equipment/{equipment_id}", response_class=HTMLResponse)
def equipment_detail(
    equipment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(status_code=404)
    
    tickets = db.query(Ticket).filter(Ticket.equipment_id == equipment_id).order_by(Ticket.created_at.desc()).all()
    
    total = len(tickets)
    active = len([t for t in tickets if t.status in ["new", "in_progress"]])
    done = len([t for t in tickets if t.status == "done"])
    closed = len([t for t in tickets if t.status == "closed"])
    
    # Среднее время закрытия
    closed_tickets = [t for t in tickets if t.closed_at]
    if closed_tickets:
        avg_hours = sum(
            (t.closed_at - t.created_at).total_seconds() / 3600
            for t in closed_tickets
        ) / len(closed_tickets)
    else:
        avg_hours = None

    return templates.TemplateResponse(request, "admin/equipment.html", {
        "current_user": current_user,
        "equipment": equipment,
        "tickets": tickets,
        "total": total,
        "active": active,
        "done": done,
        "closed": closed,
        "avg_hours": avg_hours,
        "status_labels": {"new": "Новая", "in_progress": "В работе", "done": "Выполнена", "closed": "Закрыта"},
        "status_colors": {"new": "secondary", "in_progress": "primary", "done": "success", "closed": "dark"},
        "priority_labels": {"low": "Низкий", "medium": "Средний", "high": "Высокий", "critical": "Критический"},
        "priority_colors": {"low": "success", "medium": "warning", "high": "danger", "critical": "danger"},
    })