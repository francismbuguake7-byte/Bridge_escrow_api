from extensions import db
from models.notification import Notification

def send_notification(user_id, title, message, link=None):
    try:
        notif = Notification(
            user_id=user_id,
            title=title,
            message=message,
            link=link
        )
        db.session.add(notif)
        db.session.commit()
        return notif
    except Exception as e:
        db.session.rollback()
        return None
