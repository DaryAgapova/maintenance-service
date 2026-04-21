from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from ..database import get_db
from ..models import Ticket, User, Equipment, TicketHistory, Comment, Notification
from ..auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

ALLOWED_TRANSITIONS = {
    "new": ["in_progress"],
    "in_progress": ["done"],
    "done": ["closed", "in_progress"],
    "closed": []
}

STATUS_LABELS = {
    "new": "Новая",
    "in_progress": "В работе",
    "done": "Выполнена",
    "closed": "Закрыта"
}

STATUS_COLORS = {
    "new": "secondary",
    "in_progress": "primary",
    "done": "success",
    "closed": "dark"
}

PRIORITY_LABELS = {
    "low": "Низкий",
    "medium": "Средний",
    "high": "Высокий",
    "critical": "Критический"
}

PRIORITY_COLORS = {
    "low": "success",
    "medium": "warning",
    "high": "danger",
    "critical": "danger"
}


@router.get("/", response_class=HTMLResponse)
def ticket_list(
    request: Request,
    status: str = None,
    priority: str = None,
    search: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Ticket)
    if current_user.role == "client":
        query = query.filter(Ticket.client_id == current_user.id)
    elif current_user.role == "technician":
        query = query.filter(Ticket.assignee_id == current_user.id)
    if status:
        query = query.filter(Ticket.status == status)
    if priority:
        query = query.filter(Ticket.priority == priority)
    if search:
        query = query.filter(Ticket.title.contains(search))
    tickets = query.order_by(Ticket.created_at.desc()).all()
    return templates.TemplateResponse(request, "tickets/list.html", {
        "tickets": tickets,
        "current_user": current_user,
        "status_labels": STATUS_LABELS,
        "status_colors": STATUS_COLORS,
        "priority_labels": PRIORITY_LABELS,
        "priority_colors": PRIORITY_COLORS,
        "filter_status": status,
        "filter_priority": priority,
        "search": search or "",
    })


@router.get("/tickets/new", response_class=HTMLResponse)
def new_ticket_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    equipment_list = db.query(Equipment).all()
    return templates.TemplateResponse(request, "tickets/new.html", {
        "equipment_list": equipment_list,
        "current_user": current_user,
    })


@router.post("/tickets/new")
def create_ticket(
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("medium"),
    equipment_id: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ticket = Ticket(
        title=title,
        description=description,
        priority=priority,
        equipment_id=int(equipment_id) if equipment_id else None,
        client_id=current_user.id,
        status="new"
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return RedirectResponse(url=f"/tickets/{ticket.id}", status_code=302)


@router.get("/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_detail(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    technicians = db.query(User).filter(User.role == "technician", User.is_active == True).all()
    workload = dict(
        db.query(Ticket.assignee_id, func.count(Ticket.id))
        .filter(Ticket.status.in_(["new", "in_progress"]), Ticket.assignee_id != None)
        .group_by(Ticket.assignee_id).all()
    )
    allowed_statuses = ALLOWED_TRANSITIONS.get(ticket.status, [])
    return templates.TemplateResponse(request, "tickets/detail.html", {
        "ticket": ticket,
        "current_user": current_user,
        "technicians": technicians,
        "workload": workload,
        "allowed_statuses": allowed_statuses,
        "status_labels": STATUS_LABELS,
        "status_colors": STATUS_COLORS,
        "priority_labels": PRIORITY_LABELS,
        "priority_colors": PRIORITY_COLORS,
    })


@router.post("/tickets/{ticket_id}/status")
def change_status(
    ticket_id: int,
    new_status: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404)
    if new_status not in ALLOWED_TRANSITIONS.get(ticket.status, []):
        raise HTTPException(status_code=400, detail="Недопустимый переход статуса")
    old_status = ticket.status
    ticket.status = new_status
    if new_status == "closed":
        ticket.closed_at = datetime.utcnow()
    db.add(TicketHistory(
        ticket_id=ticket.id,
        changed_by=current_user.id,
        field_name="status",
        old_value=old_status,
        new_value=new_status
    ))
    db.add(Notification(
        user_id=ticket.client_id,
        ticket_id=ticket.id,
        message=f"Статус заявки #{ticket.id} изменён на: {STATUS_LABELS.get(new_status, new_status)}"
    ))
    db.commit()
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=302)


@router.post("/tickets/{ticket_id}/assign")
def assign_ticket(
    ticket_id: int,
    assignee_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Нет доступа")
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404)
    old_assignee = str(ticket.assignee_id) if ticket.assignee_id else "—"
    ticket.assignee_id = assignee_id
    db.add(TicketHistory(
        ticket_id=ticket.id,
        changed_by=current_user.id,
        field_name="assignee",
        old_value=old_assignee,
        new_value=str(assignee_id)
    ))
    db.add(Notification(
        user_id=assignee_id,
        ticket_id=ticket.id,
        message=f"Вам назначена заявка #{ticket.id}: {ticket.title}"
    ))
    db.commit()
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=302)


@router.post("/tickets/{ticket_id}/comment")
def add_comment(
    ticket_id: int,
    body: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404)
    db.add(Comment(ticket_id=ticket_id, author_id=current_user.id, body=body))
    if ticket.client_id != current_user.id:
        db.add(Notification(
            user_id=ticket.client_id,
            ticket_id=ticket_id,
            message=f"Новый комментарий к заявке #{ticket_id} от {current_user.full_name}"
        ))
    if ticket.assignee_id and ticket.assignee_id != current_user.id:
        db.add(Notification(
            user_id=ticket.assignee_id,
            ticket_id=ticket_id,
            message=f"Новый комментарий к заявке #{ticket_id} от {current_user.full_name}"
        ))
    db.commit()
    return RedirectResponse(url=f"/tickets/{ticket_id}", status_code=302)


@router.get("/api/notifications/count")
def notifications_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).count()
    return JSONResponse({"count": count})

@router.post("/tickets/{ticket_id}/delete")
def delete_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Нет доступа")
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404)
    db.query(TicketHistory).filter(TicketHistory.ticket_id == ticket_id).delete()
    db.query(Comment).filter(Comment.ticket_id == ticket_id).delete()
    db.query(Notification).filter(Notification.ticket_id == ticket_id).delete()
    db.delete(ticket)
    db.commit()
    return RedirectResponse(url="/", status_code=302)

@router.get("/notifications", response_class=HTMLResponse)
def notifications_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notifs = db.query(Notification).filter(
        Notification.user_id == current_user.id
    ).order_by(Notification.created_at.desc()).all()
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
    return templates.TemplateResponse(request, "notifications.html", {
        "current_user": current_user,
        "notifications": notifs,
        "unread_count": 0,
    })